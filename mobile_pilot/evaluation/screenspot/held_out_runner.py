"""Strict ScreenSpot-v2 Mobile held-out evaluation entry point.

This module is intentionally separate from the 30-sample integration runner.
It accepts only the frozen 471-sample split and the two pre-registered image
variants. Any mismatch is rejected before the first model request.
"""

from __future__ import annotations

import argparse
from dataclasses import asdict, replace
import hashlib
import json
import os
from pathlib import Path
import subprocess
from typing import Any, Iterable

from PIL import Image

from mobile_pilot.evaluation.screenspot.dataset import ScreenSpotSample, load_manifest
from mobile_pilot.evaluation.screenspot.preprocess import ImageVariant
from mobile_pilot.evaluation.screenspot.reporting import (
    append_jsonl,
    read_jsonl,
    render_audit_examples,
    write_summary,
)
from mobile_pilot.evaluation.screenspot.runner import ScreenSpotConfig, ScreenSpotRunner
from mobile_pilot.evaluation.screenspot.statistics import paired_comparison
from mobile_pilot.policy import GuiPlusVisionPolicy
from mobile_pilot.policy.gui_plus import GUI_PLUS_SYSTEM_PROMPT


PROJECT_ROOT = Path(__file__).resolve().parents[3]
BENCHMARK_ROOT = PROJECT_ROOT / "artifacts/evaluation/screenspot-v2-20260723"
MANIFEST_PATH = BENCHMARK_ROOT / "manifests/held_out_manifest.json"
INTEGRATION_MANIFEST_PATH = BENCHMARK_ROOT / "manifests/integration_audit_manifest.json"
IMAGE_MAPPING_PATH = BENCHMARK_ROOT / "manifests/held_out_image_mapping.json"
FROZEN_GRID_PATH = PROJECT_ROOT / "artifacts/evaluation/grid-development-20260723/frozen_grid.json"
FREEZE_PATH = BENCHMARK_ROOT / "held-out/pre_run_freeze.json"
OUTPUT_DIR = BENCHMARK_ROOT / "held-out"

EXPECTED_HELD_OUT_COUNT = 471
EXPECTED_LOGICAL_CALLS = 942
MAX_ESTIMATED_COST_CNY = 6.0
EXPECTED_MODEL = "gui-plus-2026-02-26"
EXPECTED_BASE_URL_SHA256 = "88b2578f986bf6705fc4c077ba84db2de09ce73fceaff2de0a17494fcdf1c0ac"
EXPECTED_MANIFEST_SHA256 = "719cdb167c12d3416499c0cf70dfbac480c142dd0e56b6a52f9ada52d322021d"
EXPECTED_INTEGRATION_MANIFEST_SHA256 = (
    "26e8e1f9459e30628a008bc750b9f8d54bed1bad1f20abebd0449d7b07509485"
)
EXPECTED_FROZEN_GRID_SHA256 = (
    "b51967b6368ea293b79b68f719753841dc03ccba08e2f083fcbea8a1796d2db1"
)
EXPECTED_VARIANTS = (ImageVariant.RAW, ImageVariant.GRID_10X10)
MAX_CONSECUTIVE_PLATFORM_ERRORS = 3


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def source_hashes() -> dict[str, str]:
    relative_paths = (
        "mobile_pilot/policy/gui_plus.py",
        "mobile_pilot/evaluation/screenspot/dataset.py",
        "mobile_pilot/evaluation/screenspot/preprocess.py",
        "mobile_pilot/evaluation/screenspot/evaluator.py",
        "mobile_pilot/evaluation/screenspot/reporting.py",
        "mobile_pilot/evaluation/screenspot/runner.py",
        "mobile_pilot/evaluation/screenspot/held_out_runner.py",
        "mobile_pilot/evaluation/screenspot/statistics.py",
        "mobile_pilot/evaluation/screenspot/release_reporting.py",
    )
    return {path: sha256_file(PROJECT_ROOT / path) for path in relative_paths}


def load_and_validate_samples() -> list[ScreenSpotSample]:
    if sha256_file(MANIFEST_PATH) != EXPECTED_MANIFEST_SHA256:
        raise ValueError("held-out manifest hash mismatch")
    if sha256_file(INTEGRATION_MANIFEST_PATH) != EXPECTED_INTEGRATION_MANIFEST_SHA256:
        raise ValueError("integration manifest hash mismatch")
    if sha256_file(FROZEN_GRID_PATH) != EXPECTED_FROZEN_GRID_SHA256:
        raise ValueError("frozen grid hash mismatch")

    samples = load_manifest(MANIFEST_PATH)
    integration = load_manifest(INTEGRATION_MANIFEST_PATH)
    if len(samples) != EXPECTED_HELD_OUT_COUNT:
        raise ValueError(f"expected 471 held-out samples, got {len(samples)}")
    if any(sample.subset != "held_out" for sample in samples):
        raise ValueError("held-out runner rejects non-held_out subset rows")
    sample_ids = [sample.sample_id for sample in samples]
    if len(sample_ids) != len(set(sample_ids)):
        raise ValueError("held-out manifest contains duplicate sample_id values")
    overlap = set(sample_ids) & {sample.sample_id for sample in integration}
    if overlap:
        raise ValueError(f"integration/held-out overlap detected: {sorted(overlap)[:3]}")

    mapping_rows = json.loads(IMAGE_MAPPING_PATH.read_text(encoding="utf-8"))
    mapping = {row["sample_id"]: row for row in mapping_rows}
    if len(mapping_rows) != EXPECTED_HELD_OUT_COUNT or len(mapping) != EXPECTED_HELD_OUT_COUNT:
        raise ValueError("held-out image mapping must contain 471 unique rows")
    if set(mapping) != set(sample_ids):
        raise ValueError("held-out image mapping sample IDs do not match frozen manifest")

    attached: list[ScreenSpotSample] = []
    repository_paths: set[str] = set()
    local_paths: set[str] = set()
    for sample in samples:
        row = mapping[sample.sample_id]
        if row["image_repository_path"] in repository_paths:
            raise ValueError("image repository mapping is not unique")
        if row["local_path"] in local_paths:
            raise ValueError("local image mapping is not unique")
        repository_paths.add(row["image_repository_path"])
        local_paths.add(row["local_path"])
        image_path = PROJECT_ROOT / row["local_path"]
        if not image_path.is_file():
            raise FileNotFoundError(f"missing held-out image: {image_path}")
        if sha256_file(image_path) != row["sha256"]:
            raise ValueError(f"held-out image checksum mismatch: {sample.sample_id}")
        with Image.open(image_path) as image:
            image.verify()
        with Image.open(image_path) as image:
            width, height = image.size
        if [width, height] != row["image_size"]:
            raise ValueError(f"held-out image dimensions changed: {sample.sample_id}")
        x, y, box_width, box_height = sample.bbox_xywh
        if x < 0 or y < 0 or box_width <= 0 or box_height <= 0:
            raise ValueError(f"invalid bbox: {sample.sample_id}")
        if x + box_width > width or y + box_height > height:
            raise ValueError(f"bbox exceeds image bounds: {sample.sample_id}")
        attached.append(
            replace(
                sample,
                image_path=image_path,
                image_repository_path=row["image_repository_path"],
            )
        )
    return attached


def frozen_configs() -> tuple[ScreenSpotConfig, ScreenSpotConfig]:
    frozen = json.loads(FROZEN_GRID_PATH.read_text(encoding="utf-8"))
    if frozen["selected_variant"] != ImageVariant.GRID_10X10.value:
        raise ValueError("held-out runner only accepts the frozen 10x10 grid")
    return (
        ScreenSpotConfig("raw__vision_only", ImageVariant.RAW),
        ScreenSpotConfig("grid_10x10__vision_only", ImageVariant.GRID_10X10),
    )


def validate_freeze() -> dict[str, Any]:
    freeze = json.loads(FREEZE_PATH.read_text(encoding="utf-8"))
    expected = {
        "held_out_manifest_sha256": EXPECTED_MANIFEST_SHA256,
        "integration_manifest_sha256": EXPECTED_INTEGRATION_MANIFEST_SHA256,
        "frozen_grid_sha256": EXPECTED_FROZEN_GRID_SHA256,
        "prompt_sha256": hashlib.sha256(GUI_PLUS_SYSTEM_PROMPT.encode("utf-8")).hexdigest(),
        "model": EXPECTED_MODEL,
        "logical_call_limit": EXPECTED_LOGICAL_CALLS,
        "estimated_cost_limit_cny": MAX_ESTIMATED_COST_CNY,
        "configs": [
            {"name": "raw__vision_only", "image_variant": "raw"},
            {"name": "grid_10x10__vision_only", "image_variant": "grid_10x10"},
        ],
        "api_parameters": {
            "base_url_sha256": EXPECTED_BASE_URL_SHA256,
            "vl_high_resolution_images": True,
            "sdk_max_retries": 0,
            "request_timeout_seconds": 90.0,
        },
    }
    for key, value in expected.items():
        if freeze.get(key) != value:
            raise ValueError(f"pre-run freeze mismatch: {key}")
    if freeze.get("source_hashes") != source_hashes():
        raise ValueError("frozen source/config hashes do not match working tree")
    if freeze.get("image_mapping_sha256") != sha256_file(IMAGE_MAPPING_PATH):
        raise ValueError("held-out image mapping hash mismatch")
    return freeze


def current_git_commit() -> str:
    return subprocess.run(
        ["git", "rev-parse", "HEAD"],
        cwd=PROJECT_ROOT,
        check=True,
        capture_output=True,
        text=True,
    ).stdout.strip()


class HeldOutRunner(ScreenSpotRunner):
    def __init__(self, *, policy: Any | None = None):
        base_url = os.getenv("DASHSCOPE_BASE_URL", "")
        if hashlib.sha256(base_url.encode("utf-8")).hexdigest() != EXPECTED_BASE_URL_SHA256:
            raise ValueError("DASHSCOPE_BASE_URL does not match the frozen inference endpoint")
        super().__init__(
            output_dir=OUTPUT_DIR,
            policy=policy
            or GuiPlusVisionPolicy(
                base_url=base_url,
                model=EXPECTED_MODEL,
                request_timeout_seconds=90.0,
            ),
            max_calls=EXPECTED_LOGICAL_CALLS,
            max_estimated_cost_cny=MAX_ESTIMATED_COST_CNY,
        )

    def run(
        self,
        samples: Iterable[ScreenSpotSample],
        configs: Iterable[ScreenSpotConfig],
    ) -> list[dict[str, Any]]:
        samples = tuple(samples)
        configs = tuple(configs)
        if len(samples) != EXPECTED_HELD_OUT_COUNT:
            raise ValueError("held-out execution requires exactly 471 samples")
        if tuple(config.image_variant for config in configs) != EXPECTED_VARIANTS:
            raise ValueError("held-out execution accepts only Raw and frozen 10x10")

        existing = read_jsonl(self.records_path)
        pairs = [(row["sample_id"], row["config"]) for row in existing]
        if len(pairs) != len(set(pairs)):
            raise ValueError("duplicate terminal held-out records detected")
        allowed_pairs = {
            (sample.sample_id, config.name) for sample in samples for config in configs
        }
        if not set(pairs).issubset(allowed_pairs):
            raise ValueError("held-out JSONL contains an unexpected sample/config pair")
        calls = sum(int(row["model_call_count"]) for row in existing)
        if calls != len(existing) or calls > EXPECTED_LOGICAL_CALLS:
            raise ValueError("held-out logical call ledger is inconsistent")
        estimated_cost = sum(
            float(row.get("estimated_list_cost_cny") or 0.0) for row in existing
        )
        completed = set(pairs)
        consecutive_platform_errors = 0

        for sample in samples:
            for config in configs:
                pair = (sample.sample_id, config.name)
                if pair in completed:
                    continue
                if calls >= EXPECTED_LOGICAL_CALLS:
                    raise RuntimeError("held-out logical call hard limit reached")
                if estimated_cost >= MAX_ESTIMATED_COST_CNY:
                    raise RuntimeError("held-out catalog-price hard limit reached")

                record = self.run_one(sample, config)
                record.update(
                    {
                        "evaluation_split": "held_out",
                        "pass_k": 1,
                        "git_commit_at_run": current_git_commit(),
                        "freeze_sha256": sha256_file(FREEZE_PATH),
                    }
                )
                _validate_terminal_record(record, sample, config)
                append_jsonl(self.records_path, record)
                completed.add(pair)
                calls += 1
                estimated_cost += float(record.get("estimated_list_cost_cny") or 0.0)
                print(
                    json.dumps(
                        {
                            "progress": f"{calls}/{EXPECTED_LOGICAL_CALLS}",
                            "sample_id": sample.sample_id,
                            "config": config.name,
                            "correct": record["correct"],
                            "failure_reason": record["failure_reason"],
                            "estimated_cost_cny": round(estimated_cost, 6),
                        },
                        ensure_ascii=False,
                    ),
                    flush=True,
                )

                if record.get("parse_error_kind") == "MODEL_ERROR":
                    consecutive_platform_errors += 1
                else:
                    consecutive_platform_errors = 0
                if estimated_cost >= MAX_ESTIMATED_COST_CNY:
                    raise RuntimeError("held-out catalog-price hard limit reached")
                if consecutive_platform_errors >= MAX_CONSECUTIVE_PLATFORM_ERRORS:
                    raise RuntimeError(
                        "sustained platform failure: three consecutive MODEL_ERROR records"
                    )

        records = read_jsonl(self.records_path)
        if len(records) != EXPECTED_LOGICAL_CALLS:
            raise RuntimeError(f"held-out run incomplete: {len(records)}/942")
        write_summary(records, self.output_dir)
        paired = paired_comparison(records)
        (self.output_dir / "paired_outcomes.json").write_text(
            json.dumps(paired, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        render_audit_examples(
            _select_case_records(records),
            output_dir=self.output_dir / "visualizations",
            limit_per_config=12,
        )
        return records


def _validate_terminal_record(
    record: dict[str, Any],
    sample: ScreenSpotSample,
    config: ScreenSpotConfig,
) -> None:
    if record["sample_id"] != sample.sample_id or record["config"] != config.name:
        raise AssertionError("runner emitted a record for the wrong sample/config")
    if record["model"] != EXPECTED_MODEL:
        raise AssertionError("held-out model drift detected")
    if record["target_bbox_xywh"] != list(sample.bbox_xywh):
        raise AssertionError("held-out target bbox drift detected")
    if record["model_call_count"] != 1:
        raise AssertionError("held-out pass@1 record must contain exactly one logical call")
    if record["correct"] and record["prediction_point"] is None:
        raise AssertionError("correct record has no prediction")
    if not record["correct"] and not record["failure_reason"]:
        raise AssertionError("failed record has no failure reason")


def _select_case_records(records: list[dict[str, Any]]) -> list[dict[str, Any]]:
    by_sample: dict[str, dict[str, dict[str, Any]]] = {}
    for record in records:
        by_sample.setdefault(record["sample_id"], {})[record["config"]] = record
    selected: list[dict[str, Any]] = []
    for pair in by_sample.values():
        raw = pair["raw__vision_only"]
        grid = pair["grid_10x10__vision_only"]
        if raw["correct"] != grid["correct"]:
            selected.extend((raw, grid))
        elif not raw["correct"]:
            selected.extend((raw, grid))
        if len(selected) >= 40:
            break
    return selected


def preflight() -> dict[str, Any]:
    samples = load_and_validate_samples()
    configs = frozen_configs()
    freeze = validate_freeze()
    return {
        "status": "ready",
        "held_out_samples": len(samples),
        "configs": [asdict(config) for config in configs],
        "logical_calls": len(samples) * len(configs),
        "model": EXPECTED_MODEL,
        "freeze_git_commit": freeze["git_commit"],
        "manifest_sha256": EXPECTED_MANIFEST_SHA256,
        "image_mapping_sha256": sha256_file(IMAGE_MAPPING_PATH),
    }


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Run the frozen 471-sample ScreenSpot-v2 Mobile held-out evaluation."
    )
    parser.add_argument(
        "--preflight-only",
        action="store_true",
        help="validate all gates without calling the model",
    )
    args = parser.parse_args()
    audit = preflight()
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    (OUTPUT_DIR / "preflight.json").write_text(
        json.dumps(audit, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    print(json.dumps(audit, ensure_ascii=False), flush=True)
    if args.preflight_only:
        return
    HeldOutRunner().run(load_and_validate_samples(), frozen_configs())


if __name__ == "__main__":
    main()
