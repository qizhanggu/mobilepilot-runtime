"""Manifest validation for development and frozen Runtime comparisons."""

from __future__ import annotations

from dataclasses import dataclass
import hashlib
import json
from pathlib import Path
from typing import Any, Iterable

from mobile_pilot.androidworld.held_out import load_held_out_manifest


RUNTIME_EVAL_SCHEMA_VERSION = "mobilepilot.androidworld.runtime-eval.v1"


@dataclass(frozen=True)
class RuntimeEvalTask:
    task_id: str
    tier: str
    surface: str


@dataclass(frozen=True)
class RuntimeEvalManifest:
    path: Path
    source_schema: str
    evaluation_role: str
    androidworld_commit: str
    model: str
    seed: int
    max_action_steps: int
    task_id_sha256: str
    development_task_exclusions: tuple[str, ...]
    tasks: tuple[RuntimeEvalTask, ...]
    selection_rule: str
    variants: tuple[str, ...] = ()
    mode: str = "hybrid"
    frozen_source_sha256: str = ""
    metrics: tuple[str, ...] = ()
    max_logical_calls: int = 0
    cost_cap_cny: float = 0.0

    @property
    def task_ids(self) -> tuple[str, ...]:
        return tuple(task.task_id for task in self.tasks)


def load_runtime_eval_manifest(path: str | Path) -> RuntimeEvalManifest:
    manifest_path = Path(path)
    data = json.loads(manifest_path.read_text(encoding="utf-8"))
    schema = data.get("schema_version") if isinstance(data, dict) else None
    if schema == "mobilepilot.androidworld.held-out.v1":
        legacy = load_held_out_manifest(manifest_path)
        return RuntimeEvalManifest(
            path=manifest_path,
            source_schema=schema,
            evaluation_role="development",
            androidworld_commit=legacy.androidworld_commit,
            model=legacy.model,
            seed=legacy.seed,
            max_action_steps=legacy.max_action_steps,
            task_id_sha256=legacy.task_id_sha256,
            development_task_exclusions=legacy.development_task_exclusions,
            tasks=tuple(
                RuntimeEvalTask(task.task_id, task.tier, task.surface)
                for task in legacy.tasks
            ),
            selection_rule=str(data.get("selection_rule", "")),
            variants=(),
            mode="hybrid",
        )
    if schema != RUNTIME_EVAL_SCHEMA_VERSION:
        raise ValueError("unsupported AndroidWorld Runtime evaluation manifest schema")
    return _parse_runtime_manifest(manifest_path, data)


def assert_registry_contains(
    manifest: RuntimeEvalManifest,
    registered_task_ids: Iterable[str],
) -> None:
    missing = sorted(set(manifest.task_ids) - set(registered_task_ids))
    if missing:
        raise ValueError(
            "Runtime evaluation task IDs missing from AndroidWorld registry: "
            + ", ".join(missing)
        )


def _parse_runtime_manifest(path: Path, data: dict[str, Any]) -> RuntimeEvalManifest:
    role = data.get("evaluation_role")
    task_rows = data.get("tasks")
    exclusions = data.get("development_task_exclusions")
    if role not in {"development", "frozen_evaluation"}:
        raise ValueError("evaluation_role must be development or frozen_evaluation")
    if not isinstance(task_rows, list) or not isinstance(exclusions, list):
        raise ValueError("manifest tasks and development exclusions must be lists")
    tasks = tuple(_parse_task(row) for row in task_rows)
    expected_count = data.get("task_count")
    if not isinstance(expected_count, int) or expected_count != len(tasks):
        raise ValueError("manifest task_count does not match tasks")
    if role == "frozen_evaluation" and len(tasks) != 12:
        raise ValueError("frozen Runtime evaluation manifest must contain exactly 12 tasks")
    ids = tuple(task.task_id for task in tasks)
    if len(ids) != len(set(ids)):
        raise ValueError("Runtime evaluation manifest contains duplicate task IDs")
    if any(not isinstance(item, str) or not item for item in exclusions):
        raise ValueError("development exclusions must contain non-empty task IDs")
    if role == "frozen_evaluation" and set(ids) & set(exclusions):
        raise ValueError("frozen Runtime evaluation overlaps exposed development tasks")
    expected_hash = _task_id_hash(ids)
    if data.get("task_id_sha256") != expected_hash:
        raise ValueError("Runtime evaluation task ID hash does not match ordered tasks")
    model = data.get("model")
    commit = data.get("androidworld_commit")
    seed = data.get("seed")
    max_steps = data.get("max_action_steps")
    selection_rule = data.get("selection_rule")
    variants = data.get("variants")
    mode = data.get("mode")
    source_hash = data.get("frozen_source_sha256")
    metrics = data.get("metrics")
    max_calls = data.get("max_logical_calls")
    cost_cap = data.get("cost_cap_cny")
    if not isinstance(model, str) or not model:
        raise ValueError("Runtime evaluation model is invalid")
    if not isinstance(commit, str) or len(commit) < 12:
        raise ValueError("Runtime evaluation AndroidWorld commit is invalid")
    if not isinstance(seed, int) or not isinstance(max_steps, int) or max_steps < 1:
        raise ValueError("Runtime evaluation seed or max_action_steps is invalid")
    if not isinstance(selection_rule, str) or not selection_rule:
        raise ValueError("Runtime evaluation selection_rule is required")
    if variants != ["v1", "v2"]:
        raise ValueError("Runtime evaluation variants must be frozen as v1 then v2")
    if mode != "hybrid":
        raise ValueError("Runtime evaluation mode must be hybrid")
    if not isinstance(source_hash, str) or len(source_hash) != 64:
        raise ValueError("Runtime evaluation frozen_source_sha256 is invalid")
    if not isinstance(metrics, list) or not metrics or not all(
        isinstance(item, str) and item for item in metrics
    ):
        raise ValueError("Runtime evaluation metrics must be a non-empty list")
    if not isinstance(max_calls, int) or max_calls < 1:
        raise ValueError("Runtime evaluation max_logical_calls is invalid")
    if not isinstance(cost_cap, (int, float)) or not (0 < cost_cap <= 15):
        raise ValueError("Runtime evaluation cost_cap_cny must be within (0, 15]")
    return RuntimeEvalManifest(
        path=path,
        source_schema=RUNTIME_EVAL_SCHEMA_VERSION,
        evaluation_role=role,
        androidworld_commit=commit,
        model=model,
        seed=seed,
        max_action_steps=max_steps,
        task_id_sha256=expected_hash,
        development_task_exclusions=tuple(exclusions),
        tasks=tasks,
        selection_rule=selection_rule,
        variants=tuple(variants),
        mode=mode,
        frozen_source_sha256=source_hash,
        metrics=tuple(metrics),
        max_logical_calls=max_calls,
        cost_cap_cny=float(cost_cap),
    )


def _parse_task(row: Any) -> RuntimeEvalTask:
    if not isinstance(row, dict):
        raise ValueError("Runtime evaluation task entries must be objects")
    task_id, tier, surface = row.get("id"), row.get("tier"), row.get("surface")
    if not all(isinstance(value, str) and value for value in (task_id, tier, surface)):
        raise ValueError("Runtime evaluation task requires id, tier, and surface")
    return RuntimeEvalTask(task_id, tier, surface)


def task_id_hash(task_ids: Iterable[str]) -> str:
    return _task_id_hash(tuple(task_ids))


def _task_id_hash(task_ids: Iterable[str]) -> str:
    return hashlib.sha256(("\n".join(task_ids) + "\n").encode("utf-8")).hexdigest()
