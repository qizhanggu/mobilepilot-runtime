import hashlib
import json

import pytest

from mobile_pilot.evaluation.screenspot import held_out_runner


def test_held_out_constants_keep_integration_runner_separate():
    assert held_out_runner.EXPECTED_HELD_OUT_COUNT == 471
    assert held_out_runner.EXPECTED_LOGICAL_CALLS == 942
    assert held_out_runner.EXPECTED_MODEL == "gui-plus-2026-02-26"
    assert held_out_runner.MAX_ESTIMATED_COST_CNY == 6.0
    assert held_out_runner.MANIFEST_PATH.name == "held_out_manifest.json"


def test_validate_freeze_rejects_model_drift(tmp_path, monkeypatch):
    freeze = {
        "held_out_manifest_sha256": held_out_runner.EXPECTED_MANIFEST_SHA256,
        "integration_manifest_sha256": held_out_runner.EXPECTED_INTEGRATION_MANIFEST_SHA256,
        "frozen_grid_sha256": held_out_runner.EXPECTED_FROZEN_GRID_SHA256,
        "prompt_sha256": hashlib.sha256(
            held_out_runner.GUI_PLUS_SYSTEM_PROMPT.encode("utf-8")
        ).hexdigest(),
        "model": "gui-plus",
        "logical_call_limit": 942,
        "estimated_cost_limit_cny": 6.0,
        "configs": [
            {"name": "raw__vision_only", "image_variant": "raw"},
            {"name": "grid_10x10__vision_only", "image_variant": "grid_10x10"},
        ],
        "api_parameters": {
            "base_url_sha256": held_out_runner.EXPECTED_BASE_URL_SHA256,
            "vl_high_resolution_images": True,
            "sdk_max_retries": 0,
            "request_timeout_seconds": 90.0,
        },
        "source_hashes": held_out_runner.source_hashes(),
        "image_mapping_sha256": "unused",
    }
    path = tmp_path / "freeze.json"
    path.write_text(json.dumps(freeze), encoding="utf-8")
    monkeypatch.setattr(held_out_runner, "FREEZE_PATH", path)

    with pytest.raises(ValueError, match="model"):
        held_out_runner.validate_freeze()
