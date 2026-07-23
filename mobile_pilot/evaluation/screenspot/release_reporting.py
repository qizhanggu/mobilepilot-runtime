"""Build held-out-primary and 501-sample ScreenSpot-v2 release reports."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

from mobile_pilot.evaluation.screenspot.reporting import read_jsonl, write_summary
from mobile_pilot.evaluation.screenspot.statistics import (
    outside_bbox_metrics,
    paired_comparison,
)


PROJECT_ROOT = Path(__file__).resolve().parents[3]
BENCHMARK_ROOT = PROJECT_ROOT / "artifacts/evaluation/screenspot-v2-20260723"
INTEGRATION_RECORDS = BENCHMARK_ROOT / "integration-audit/runs.jsonl"
HELD_OUT_RECORDS = BENCHMARK_ROOT / "held-out/runs.jsonl"
RELEASE_DIR = BENCHMARK_ROOT / "release-501"
EXPECTED_CONFIGS = {"raw__vision_only", "grid_10x10__vision_only"}


def validate_records(
    records: list[dict[str, Any]],
    *,
    expected_samples: int,
    expected_subset: str,
) -> None:
    pairs = [(row["sample_id"], row["config"]) for row in records]
    if len(records) != expected_samples * 2:
        raise ValueError(f"expected {expected_samples * 2} records, got {len(records)}")
    if len(pairs) != len(set(pairs)):
        raise ValueError("duplicate sample/config records")
    if {row["config"] for row in records} != EXPECTED_CONFIGS:
        raise ValueError("unexpected release configuration")
    if len({row["sample_id"] for row in records}) != expected_samples:
        raise ValueError("unexpected unique sample count")
    for row in records:
        subset = row.get("evaluation_split", row.get("subset"))
        if subset != expected_subset:
            raise ValueError(f"unexpected subset: {subset}")


def select_typical_cases(records: list[dict[str, Any]]) -> dict[str, Any]:
    by_sample: dict[str, dict[str, dict[str, Any]]] = {}
    for row in records:
        by_sample.setdefault(row["sample_id"], {})[row["config"]] = row

    categories: dict[str, dict[str, Any] | None] = {
        "grid_corrects_raw": None,
        "grid_harms_raw": None,
        "both_fail": None,
        "invalid_output": None,
        "text_difference": None,
        "icon_difference": None,
    }
    for sample_id, pair in by_sample.items():
        raw = pair["raw__vision_only"]
        grid = pair["grid_10x10__vision_only"]
        compact = {
            "sample_id": sample_id,
            "instruction": raw["instruction"],
            "data_type": raw["data_type"],
            "target_bbox_xyxy": raw["target_bbox_xyxy"],
            "image_path": raw["image_path"],
            "raw": _compact_record(raw),
            "grid_10x10": _compact_record(grid),
        }
        if not raw["correct"] and grid["correct"] and categories["grid_corrects_raw"] is None:
            categories["grid_corrects_raw"] = compact
        if raw["correct"] and not grid["correct"] and categories["grid_harms_raw"] is None:
            categories["grid_harms_raw"] = compact
        if not raw["correct"] and not grid["correct"] and categories["both_fail"] is None:
            categories["both_fail"] = compact
        if (
            raw["failure_reason"] == "invalid_model_output"
            or grid["failure_reason"] == "invalid_model_output"
        ) and categories["invalid_output"] is None:
            categories["invalid_output"] = compact
        if (
            raw["correct"] != grid["correct"]
            and raw["data_type"] == "text"
            and categories["text_difference"] is None
        ):
            categories["text_difference"] = compact
        if (
            raw["correct"] != grid["correct"]
            and raw["data_type"] == "icon"
            and categories["icon_difference"] is None
        ):
            categories["icon_difference"] = compact
    return categories


def _compact_record(record: dict[str, Any]) -> dict[str, Any]:
    return {
        "correct": record["correct"],
        "prediction_point": record["prediction_point"],
        "failure_reason": record["failure_reason"],
        "parse_error_kind": record["parse_error_kind"],
        "latency_seconds": record["latency_seconds"],
        "total_tokens": record["total_tokens"],
        "estimated_list_cost_cny": record["estimated_list_cost_cny"],
        "raw_model_response": record["raw_model_response"],
    }


def build_release() -> dict[str, Any]:
    integration = read_jsonl(INTEGRATION_RECORDS)
    held_out = read_jsonl(HELD_OUT_RECORDS)
    validate_records(integration, expected_samples=30, expected_subset="integration_audit")
    validate_records(held_out, expected_samples=471, expected_subset="held_out")
    if {row["sample_id"] for row in integration} & {row["sample_id"] for row in held_out}:
        raise ValueError("integration/held-out sample overlap")

    combined = integration + held_out
    RELEASE_DIR.mkdir(parents=True, exist_ok=True)
    held_summary = write_summary(held_out, RELEASE_DIR / "held-out-471")
    integration_summary = write_summary(integration, RELEASE_DIR / "integration-audit-30")
    combined_summary = write_summary(combined, RELEASE_DIR / "combined-501")
    report = {
        "primary_result": "held_out_471",
        "integration_audit_samples": 30,
        "held_out_samples": 471,
        "combined_samples": 501,
        "held_out_summary": held_summary,
        "integration_audit_summary": integration_summary,
        "combined_summary": combined_summary,
        "held_out_paired_comparison": paired_comparison(held_out),
        "combined_paired_comparison": paired_comparison(combined),
        "held_out_outside_bbox": outside_bbox_metrics(held_out),
        "combined_outside_bbox": outside_bbox_metrics(combined),
        "typical_held_out_cases": select_typical_cases(held_out),
    }
    (RELEASE_DIR / "release_report.json").write_text(
        json.dumps(report, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    return report


def main() -> None:
    argparse.ArgumentParser().parse_args()
    print(json.dumps(build_release(), ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
