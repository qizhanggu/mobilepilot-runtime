"""在仓库自带离线截图上选择唯一网格配置，不接触公共测试集。"""

from __future__ import annotations

from dataclasses import asdict
import argparse
import hashlib
import json
from pathlib import Path
import statistics
from typing import Any

from PIL import Image

from mobile_pilot.evaluation.screenspot.evaluator import normalized_to_pixel, point_in_bbox_xywh
from mobile_pilot.evaluation.screenspot.preprocess import ImageVariant, apply_image_variant
from mobile_pilot.evaluation.screenspot.reporting import append_jsonl, read_jsonl
from mobile_pilot.policy import GuiPlusRequest, GuiPlusVisionPolicy


DEV_CASES = (
    "step_baidumap_onekey_0008",
    "step_bilibili_onekey_0008",
    "step_douyin_onekey_0008",
    "step_kuaishou_onekey_0003",
    "step_mangguo_onekey_0008",
    "step_meituan_onekey_0001",
    "step_tengxunshipin_onekey_0005",
    "step_ximalaya_onekey_0001",
)
GRID_VARIANTS = (
    ImageVariant.GRID_10X10,
    ImageVariant.GRID_8X16,
    ImageVariant.GRID_10X20,
)
GRID_DENSITY = {
    ImageVariant.GRID_10X10.value: 100,
    ImageVariant.GRID_8X16.value: 128,
    ImageVariant.GRID_10X20.value: 200,
}


def load_dev_cases(root: Path) -> list[dict[str, Any]]:
    cases = []
    for case_id in DEV_CASES:
        case_dir = root / case_id
        reference = json.loads((case_dir / "ref.json").read_text(encoding="utf-8"))
        action = next(item for item in reference["1"] if item["action"] == "CLICK")
        params = action["params"]
        x1, x2 = params["x_real"]
        y1, y2 = params["y_real"]
        cases.append(
            {
                "case_id": case_id,
                "instruction": reference["case_overview"]["instruction"],
                "image_path": case_dir / "1.png",
                "bbox_xywh": (x1, y1, x2 - x1, y2 - y1),
            }
        )
    return cases


class GridDevelopmentRunner:
    def __init__(self, *, output_dir: Path, policy: GuiPlusVisionPolicy | None = None):
        self.output_dir = output_dir
        self.records_path = output_dir / "runs.jsonl"
        self.policy = policy or GuiPlusVisionPolicy()

    def run(self, cases: list[dict[str, Any]], *, repeats: int = 3) -> dict[str, Any]:
        completed = {
            (row["case_id"], row["variant"], int(row["repeat"]))
            for row in read_jsonl(self.records_path)
        }
        for repeat in range(1, repeats + 1):
            for case in cases:
                for variant in GRID_VARIANTS:
                    key = (case["case_id"], variant.value, repeat)
                    if key in completed:
                        continue
                    record = self.run_one(case, variant, repeat)
                    append_jsonl(self.records_path, record)
                    print(
                        json.dumps(
                            {
                                "case_id": case["case_id"],
                                "variant": variant.value,
                                "repeat": repeat,
                                "correct": record["correct"],
                            },
                            ensure_ascii=False,
                        ),
                        flush=True,
                    )
        records = read_jsonl(self.records_path)
        summary = summarize_grid_records(records)
        frozen = freeze_unique_grid(summary)
        self.output_dir.mkdir(parents=True, exist_ok=True)
        (self.output_dir / "summary.json").write_text(
            json.dumps(summary, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        (self.output_dir / "frozen_grid.json").write_text(
            json.dumps(frozen, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        return frozen

    def run_one(
        self,
        case: dict[str, Any],
        variant: ImageVariant,
        repeat: int,
    ) -> dict[str, Any]:
        image = Image.open(case["image_path"]).convert("RGB")
        processed = apply_image_variant(image, variant)
        decision = self.policy.decide_with_metrics(GuiPlusRequest(case["instruction"], processed))
        normalized = None
        prediction = None
        correct = False
        if decision.result.is_success and decision.result.action is not None:
            normalized = decision.result.action.parameters["point"]
            prediction = normalized_to_pixel(normalized, image.size)
            correct = point_in_bbox_xywh(prediction, case["bbox_xywh"])
        return {
            "case_id": case["case_id"],
            "instruction": case["instruction"],
            "image_path": str(case["image_path"]),
            "target_bbox_xywh": list(case["bbox_xywh"]),
            "variant": variant.value,
            "repeat": repeat,
            "normalized_prediction": normalized,
            "prediction_point": list(prediction) if prediction else None,
            "correct": correct,
            "parse_success": decision.result.is_success,
            "raw_model_response": decision.result.raw_output,
            **asdict(decision.metrics),
        }


def summarize_grid_records(records: list[dict[str, Any]]) -> list[dict[str, Any]]:
    summary = []
    for variant in GRID_VARIANTS:
        rows = [row for row in records if row["variant"] == variant.value]
        failures = sum(not row["parse_success"] for row in rows)
        summary.append(
            {
                "variant": variant.value,
                "runs": len(rows),
                "correct": sum(bool(row["correct"]) for row in rows),
                "accuracy": sum(bool(row["correct"]) for row in rows) / len(rows),
                "invalid_outputs": failures,
                "mean_latency_seconds": statistics.mean(float(row["latency_seconds"]) for row in rows),
                "prompt_tokens": sum(int(row.get("prompt_tokens") or 0) for row in rows),
                "completion_tokens": sum(int(row.get("completion_tokens") or 0) for row in rows),
                "estimated_list_cost_cny": sum(float(row.get("estimated_list_cost_cny") or 0.0) for row in rows),
                "grid_density": GRID_DENSITY[variant.value],
            }
        )
    return summary


def freeze_unique_grid(summary: list[dict[str, Any]]) -> dict[str, Any]:
    """成功数优先；再看无效输出；仍相同时选择遮挡更少的稀疏网格。"""

    ranked = sorted(
        summary,
        key=lambda row: (
            -int(row["correct"]),
            int(row["invalid_outputs"]),
            int(row["grid_density"]),
            row["variant"],
        ),
    )
    selected = ranked[0]["variant"]
    payload = {
        "selected_variant": selected,
        "selection_rule": [
            "maximize_correct",
            "minimize_invalid_outputs",
            "minimize_grid_density",
            "lexicographic_variant",
        ],
        "ranking": ranked,
        "public_test_results_used": False,
    }
    payload["freeze_sha256"] = hashlib.sha256(
        json.dumps(payload, ensure_ascii=False, sort_keys=True).encode("utf-8")
    ).hexdigest()
    return payload


def main() -> None:
    parser = argparse.ArgumentParser(description="Select one frozen grid on the private offline dev set.")
    parser.add_argument("--data-root", type=Path, default=Path("test_data/offline"))
    parser.add_argument(
        "--output",
        type=Path,
        default=Path("artifacts/evaluation/grid-development-20260723"),
    )
    parser.add_argument("--repeats", type=int, default=3)
    args = parser.parse_args()
    if args.repeats < 1:
        raise ValueError("repeats must be positive")
    GridDevelopmentRunner(output_dir=args.output).run(
        load_dev_cases(args.data_root),
        repeats=args.repeats,
    )


if __name__ == "__main__":
    main()
