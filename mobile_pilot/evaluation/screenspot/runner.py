"""GUI-Plus 在 ScreenSpot-v2 Mobile 上的可恢复、可审计运行器。"""

from __future__ import annotations

from dataclasses import asdict, dataclass
import argparse
import hashlib
import json
from pathlib import Path
from typing import Any, Iterable

from PIL import Image

from mobile_pilot.policy.gui_plus import GUI_PLUS_SYSTEM_PROMPT, GuiPlusRequest, GuiPlusVisionPolicy

from .dataset import ScreenSpotSample, load_manifest
from .evaluator import normalized_to_pixel, point_in_bbox_xywh
from .preprocess import ImageVariant, apply_image_variant
from .reporting import append_jsonl, read_jsonl, render_audit_examples, write_summary


@dataclass(frozen=True)
class ScreenSpotConfig:
    name: str
    image_variant: ImageVariant


class ScreenSpotRunner:
    def __init__(
        self,
        *,
        output_dir: Path,
        policy: GuiPlusVisionPolicy | None = None,
        max_calls: int = 60,
        max_estimated_cost_cny: float = 5.0,
    ):
        self.output_dir = output_dir
        self.records_path = output_dir / "runs.jsonl"
        self.policy = policy or GuiPlusVisionPolicy()
        self.max_calls = max_calls
        self.max_estimated_cost_cny = max_estimated_cost_cny

    def run(
        self,
        samples: Iterable[ScreenSpotSample],
        configs: Iterable[ScreenSpotConfig],
    ) -> list[dict[str, Any]]:
        samples = tuple(samples)
        configs = tuple(configs)
        existing = read_jsonl(self.records_path)
        completed = {(row["sample_id"], row["config"]) for row in existing}
        calls = sum(int(row["model_call_count"]) for row in existing)
        estimated_cost = sum(float(row.get("estimated_list_cost_cny") or 0.0) for row in existing)

        for sample in samples:
            for config in configs:
                if (sample.sample_id, config.name) in completed:
                    continue
                if calls >= self.max_calls:
                    raise RuntimeError(f"model call budget exhausted: {calls}/{self.max_calls}")
                if estimated_cost >= self.max_estimated_cost_cny:
                    raise RuntimeError(
                        f"estimated cost budget exhausted: {estimated_cost:.6f}/{self.max_estimated_cost_cny:.2f} CNY"
                    )
                record = self.run_one(sample, config)
                append_jsonl(self.records_path, record)
                calls += 1
                estimated_cost += float(record.get("estimated_list_cost_cny") or 0.0)
                print(
                    json.dumps(
                        {
                            "sample_id": sample.sample_id,
                            "config": config.name,
                            "correct": record["correct"],
                            "failure_reason": record["failure_reason"],
                        },
                        ensure_ascii=False,
                    ),
                    flush=True,
                )

        records = read_jsonl(self.records_path)
        write_summary(records, self.output_dir)
        render_audit_examples(records, output_dir=self.output_dir / "visualizations")
        return records

    def run_one(self, sample: ScreenSpotSample, config: ScreenSpotConfig) -> dict[str, Any]:
        if sample.image_path is None or not sample.image_path.exists():
            raise FileNotFoundError(f"missing image for {sample.sample_id}: {sample.image_path}")
        original = Image.open(sample.image_path).convert("RGB")
        processed = apply_image_variant(original, config.image_variant)
        decision = self.policy.decide_with_metrics(GuiPlusRequest(sample.instruction, processed))

        prediction = None
        correct = False
        failure_reason = ""
        normalized = None
        if decision.result.is_success and decision.result.action is not None:
            normalized = decision.result.action.parameters["point"]
            prediction = normalized_to_pixel(normalized, original.size)
            correct = point_in_bbox_xywh(prediction, sample.bbox_xywh)
            if not correct:
                failure_reason = "prediction_outside_target"
        else:
            failure_reason = "invalid_model_output"

        return {
            "sample_id": sample.sample_id,
            "sample_index": sample.index,
            "subset": sample.subset,
            "img_filename": sample.img_filename,
            "image_path": str(sample.image_path),
            "image_repository_path": sample.image_repository_path,
            "image_width": original.width,
            "image_height": original.height,
            "instruction": sample.instruction,
            "data_type": sample.data_type,
            "data_source": sample.data_source,
            "target_bbox_xywh": list(sample.bbox_xywh),
            "target_bbox_xyxy": list(sample.bbox_xyxy),
            "config": config.name,
            "image_variant": config.image_variant.value,
            "normalized_prediction": normalized,
            "prediction_point": list(prediction) if prediction else None,
            "correct": correct,
            "failure_reason": failure_reason,
            "parse_success": decision.result.is_success,
            "parse_error_kind": decision.result.error_kind.value if decision.result.error_kind else None,
            "parse_message": decision.result.message,
            "raw_model_response": decision.result.raw_output,
            "model_call_count": 1,
            **asdict(decision.metrics),
            "system_prompt_sha256": hashlib.sha256(GUI_PLUS_SYSTEM_PROMPT.encode("utf-8")).hexdigest(),
            "runner_config_sha256": _config_hash(config),
        }


def _config_hash(config: ScreenSpotConfig) -> str:
    payload = {
        "name": config.name,
        "image_variant": config.image_variant.value,
        "system_prompt": GUI_PLUS_SYSTEM_PROMPT,
        "coordinate_space": "normalized_0_1000",
        "high_resolution_images": True,
    }
    return hashlib.sha256(
        json.dumps(payload, ensure_ascii=False, sort_keys=True).encode("utf-8")
    ).hexdigest()


def main() -> None:
    parser = argparse.ArgumentParser(description="Run the frozen ScreenSpot-v2 integration/audit subset.")
    parser.add_argument(
        "--manifest",
        type=Path,
        default=Path(
            "artifacts/evaluation/screenspot-v2-20260723/manifests/"
            "integration_audit_manifest.json"
        ),
    )
    parser.add_argument(
        "--frozen-grid",
        type=Path,
        default=Path("artifacts/evaluation/grid-development-20260723/frozen_grid.json"),
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=Path("artifacts/evaluation/screenspot-v2-20260723/integration-audit"),
    )
    parser.add_argument("--max-calls", type=int, default=60)
    parser.add_argument("--max-estimated-cost-cny", type=float, default=5.0)
    args = parser.parse_args()

    samples = load_manifest(args.manifest)
    if len(samples) != 30 or any(sample.subset != "integration_audit" for sample in samples):
        raise ValueError("runner only accepts the frozen 30-sample integration/audit manifest")
    frozen = json.loads(args.frozen_grid.read_text(encoding="utf-8"))
    variant = ImageVariant(frozen["selected_variant"])
    configs = (
        ScreenSpotConfig("raw__vision_only", ImageVariant.RAW),
        ScreenSpotConfig(f"{variant.value}__vision_only", variant),
    )
    args.output.mkdir(parents=True, exist_ok=True)
    run_configuration = {
        "manifest": str(args.manifest),
        "manifest_sha256": hashlib.sha256(args.manifest.read_bytes()).hexdigest(),
        "frozen_grid": frozen,
        "configs": [
            {"name": config.name, "image_variant": config.image_variant.value}
            for config in configs
        ],
        "prompt_changes_after_audit": False,
        "strategy_changes_after_audit": False,
        "output_rule_changes_after_audit": False,
    }
    (args.output / "run_config.json").write_text(
        json.dumps(run_configuration, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    ScreenSpotRunner(
        output_dir=args.output,
        max_calls=args.max_calls,
        max_estimated_cost_cny=args.max_estimated_cost_cny,
    ).run(samples, configs)


if __name__ == "__main__":
    main()
