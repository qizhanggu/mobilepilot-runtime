"""Frozen-manifest validation shared by AndroidWorld held-out tooling."""

from __future__ import annotations

from dataclasses import dataclass
import hashlib
import json
from pathlib import Path
from typing import Any, Iterable


SCHEMA_VERSION = "mobilepilot.androidworld.held-out.v1"


@dataclass(frozen=True)
class HeldOutTask:
    task_id: str
    tier: str
    surface: str


@dataclass(frozen=True)
class HeldOutManifest:
    path: Path
    androidworld_commit: str
    model: str
    seed: int
    max_action_steps: int
    task_id_sha256: str
    development_task_exclusions: tuple[str, ...]
    tasks: tuple[HeldOutTask, ...]

    @property
    def task_ids(self) -> tuple[str, ...]:
        return tuple(task.task_id for task in self.tasks)


def load_held_out_manifest(path: str | Path) -> HeldOutManifest:
    manifest_path = Path(path)
    data = json.loads(manifest_path.read_text(encoding="utf-8"))
    if not isinstance(data, dict) or data.get("schema_version") != SCHEMA_VERSION:
        raise ValueError("unsupported AndroidWorld held-out manifest schema")
    task_rows = data.get("tasks")
    exclusions = data.get("development_task_exclusions")
    if not isinstance(task_rows, list) or not isinstance(exclusions, list):
        raise ValueError("manifest tasks and development exclusions must be lists")
    tasks = tuple(_parse_task(row) for row in task_rows)
    if len(tasks) != 20:
        raise ValueError(f"held-out manifest must contain exactly 20 tasks, got {len(tasks)}")
    ids = tuple(task.task_id for task in tasks)
    if len(set(ids)) != len(ids):
        raise ValueError("held-out manifest contains duplicate task IDs")
    if any(not isinstance(item, str) or not item for item in exclusions):
        raise ValueError("development exclusions must contain non-empty IDs")
    if set(ids) & set(exclusions):
        raise ValueError("held-out manifest overlaps the development task list")
    expected_hash = _task_id_hash(ids)
    if data.get("task_id_sha256") != expected_hash:
        raise ValueError("held-out manifest task ID hash does not match its ordered task list")
    model = data.get("model")
    commit = data.get("androidworld_commit")
    seed = data.get("seed")
    max_steps = data.get("max_action_steps")
    if not isinstance(model, str) or not model or not isinstance(commit, str) or len(commit) < 12:
        raise ValueError("manifest model or AndroidWorld commit is invalid")
    if not isinstance(seed, int) or not isinstance(max_steps, int) or max_steps < 1:
        raise ValueError("manifest seed or max_action_steps is invalid")
    return HeldOutManifest(
        path=manifest_path,
        androidworld_commit=commit,
        model=model,
        seed=seed,
        max_action_steps=max_steps,
        task_id_sha256=expected_hash,
        development_task_exclusions=tuple(exclusions),
        tasks=tasks,
    )


def assert_registry_contains(manifest: HeldOutManifest, registered_task_ids: Iterable[str]) -> None:
    missing = sorted(set(manifest.task_ids) - set(registered_task_ids))
    if missing:
        raise ValueError("held-out manifest task IDs missing from AndroidWorld registry: " + ", ".join(missing))


def _parse_task(row: Any) -> HeldOutTask:
    if not isinstance(row, dict):
        raise ValueError("manifest task entries must be objects")
    task_id, tier, surface = row.get("id"), row.get("tier"), row.get("surface")
    if not all(isinstance(value, str) and value for value in (task_id, tier, surface)):
        raise ValueError("manifest task entry requires non-empty id, tier, and surface")
    return HeldOutTask(task_id=task_id, tier=tier, surface=surface)


def _task_id_hash(task_ids: Iterable[str]) -> str:
    return hashlib.sha256(("\n".join(task_ids) + "\n").encode("utf-8")).hexdigest()
