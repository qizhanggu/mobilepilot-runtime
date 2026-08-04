import json
from types import SimpleNamespace

import pytest

from mobile_pilot.androidworld.evaluation import (
    load_runtime_eval_manifest,
    task_id_hash,
)
from scripts.run_androidworld_runtime_eval import (
    _existing_records,
    _summary,
    _trace_metrics,
    _validate_protocol,
)


def test_legacy_20_task_manifest_is_explicitly_development_evidence():
    manifest = load_runtime_eval_manifest("configs/androidworld/held_out_20.json")

    assert manifest.evaluation_role == "development"
    assert len(manifest.tasks) == 20
    assert manifest.variants == ()


def test_frozen_12_task_manifest_keeps_development_sets_disjoint():
    manifest = load_runtime_eval_manifest(
        "configs/androidworld/runtime_eval_12_v2.json"
    )

    assert manifest.evaluation_role == "frozen_evaluation"
    assert len(manifest.tasks) == 12
    assert manifest.variants == ("v1", "v2")
    assert manifest.mode == "hybrid"
    assert manifest.model == "gui-plus-2026-02-26"
    assert manifest.androidworld_commit == (
        "3e50888527ef9f29b9157ecd537e408008bb1c85"
    )
    assert not set(manifest.task_ids) & set(manifest.development_task_exclusions)


def test_loads_frozen_runtime_manifest_and_rejects_development_overlap(tmp_path):
    task_ids = [f"UnusedTask{index:02d}" for index in range(12)]
    data = {
        "schema_version": "mobilepilot.androidworld.runtime-eval.v1",
        "evaluation_role": "frozen_evaluation",
        "task_count": 12,
        "androidworld_commit": "3e50888527ef9f29b9157ecd537e408008bb1c85",
        "model": "gui-plus-2026-02-26",
        "seed": 0,
        "max_action_steps": 12,
        "task_id_sha256": task_id_hash(task_ids),
        "development_task_exclusions": ["DevelopmentTask"],
        "selection_rule": "selected before results",
        "variants": ["v1", "v2"],
        "mode": "hybrid",
        "frozen_source_sha256": "a" * 64,
        "metrics": ["official_success_rate"],
        "max_logical_calls": 400,
        "cost_cap_cny": 15.0,
        "tasks": [
            {"id": task_id, "tier": "medium", "surface": "test"}
            for task_id in task_ids
        ],
    }
    path = tmp_path / "manifest.json"
    path.write_text(json.dumps(data), encoding="utf-8")

    manifest = load_runtime_eval_manifest(path)
    assert manifest.variants == ("v1", "v2")
    assert manifest.cost_cap_cny == 15.0

    data["development_task_exclusions"].append(task_ids[0])
    path.write_text(json.dumps(data), encoding="utf-8")
    with pytest.raises(ValueError, match="overlaps"):
        load_runtime_eval_manifest(path)


def test_development_runner_requires_explicit_variant():
    manifest = load_runtime_eval_manifest("configs/androidworld/held_out_20.json")
    args = SimpleNamespace(
        variant=None,
        mode="hybrid",
        max_logical_calls=400,
        cost_cap_cny=15.0,
    )

    with pytest.raises(ValueError, match="explicitly select"):
        _validate_protocol(manifest, ("v2",), args)


def test_trace_metrics_keep_protocol_recovery_tree_and_cost_separate(tmp_path):
    rows = [
        {
            "event": "actor_decision",
            "parsed": False,
            "protocol_normalized": False,
            "metrics": {
                "prompt_tokens": 100,
                "completion_tokens": 10,
                "total_tokens": 110,
                "estimated_list_cost_cny": 0.01,
                "latency_seconds": 1.5,
            },
        },
        {"event": "protocol_guard", "strategy": "structured_retry", "outcome": "triggered"},
        {
            "event": "actor_decision",
            "parsed": True,
            "protocol_normalized": False,
            "metrics": {
                "prompt_tokens": 120,
                "completion_tokens": 12,
                "total_tokens": 132,
                "estimated_list_cost_cny": 0.02,
                "latency_seconds": 2.0,
            },
        },
        {"event": "protocol_guard", "strategy": "structured_retry", "outcome": "action_obtained"},
        {"event": "observation", "ui_tree_requested": True, "ui_tree_trigger_reason": "invalid_actor_output"},
        {"event": "execution", "executed": True},
        {"event": "loop_detected"},
        {"event": "agent_recovery_triggered"},
        {"event": "agent_recovery_outcome", "rescued": True, "misfire": False},
        {"event": "agent_finished", "reason": "step_budget_exhausted"},
    ]
    path = tmp_path / "trace.jsonl"
    path.write_text("\n".join(json.dumps(row) for row in rows) + "\n", encoding="utf-8")

    metrics = _trace_metrics(path)

    assert metrics["vlm_call_count"] == 2
    assert metrics["invalid_decision_count"] == 1
    assert metrics["protocol_retry_trigger_count"] == 1
    assert metrics["protocol_retry_action_obtained_count"] == 1
    assert metrics["recovery_rescue_count"] == 1
    assert metrics["ui_tree_trigger_reasons"] == {"invalid_actor_output": 1}
    assert metrics["estimated_list_cost_cny"] == pytest.approx(0.03)


def test_existing_infrastructure_error_forbids_automatic_task_retry(tmp_path):
    path = tmp_path / "runs.jsonl"
    path.write_text(
        json.dumps(
            {
                "task_id": "Task",
                "variant": "v1",
                "mode": "hybrid",
                "status": "infrastructure_error",
            }
        )
        + "\n",
        encoding="utf-8",
    )

    with pytest.raises(RuntimeError, match="forbids automatic retry"):
        _existing_records(path)


def test_summary_reports_paired_outcomes_and_failure_taxonomy():
    manifest = load_runtime_eval_manifest("configs/androidworld/held_out_20.json")
    rows = [
        {
            "task_id": "TaskA",
            "variant": "v1",
            "official_reward": 0.0,
            "terminal_reason": "invalid_actor_output",
        },
        {
            "task_id": "TaskA",
            "variant": "v2",
            "official_reward": 1.0,
            "terminal_reason": "official_success_without_agent_finish",
        },
    ]

    result = _summary(rows, manifest, ("v1", "v2"), "hybrid", {})

    assert result["paired_outcomes"] == {"v1_failure__v2_success": 1}
    assert result["by_variant"]["v1"]["failure_taxonomy"] == {
        "invalid_actor_output": 1
    }
