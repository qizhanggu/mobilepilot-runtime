"""Run the frozen AndroidWorld 20-task held-out comparison safely.

This runner intentionally delegates one task at a time to the existing single
task runner.  It does not alter task goals, model Prompt, or action semantics;
its responsibilities are frozen-manifest gates, resume safety, budget guards,
and an auditable run index.
"""

from __future__ import annotations

import argparse
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys
from typing import Any

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from mobile_pilot.androidworld.held_out import HeldOutManifest, assert_registry_contains, load_held_out_manifest


FROZEN_SOURCE_FILES = (
    "mobile_pilot/androidworld/actor.py",
    "mobile_pilot/androidworld/agent.py",
    "mobile_pilot/androidworld/adapter.py",
    "scripts/run_mobilepilot_androidworld.py",
)
MAX_COST_PER_LOGICAL_CALL_CNY = 0.02


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--manifest", default="configs/androidworld/held_out_20.json")
    parser.add_argument("--output-dir", default="artifacts/evaluation/androidworld-held-out")
    parser.add_argument("--adb-path", required=True)
    parser.add_argument("--mode", action="append", choices=("vision_only", "hybrid"))
    parser.add_argument("--verify-only", action="store_true")
    parser.add_argument("--max-logical-calls", type=int, default=520)
    parser.add_argument("--cost-cap-cny", type=float, default=15.0)
    parser.add_argument("--task-timeout-seconds", type=int, default=600)
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    modes = tuple(args.mode or ("vision_only", "hybrid"))
    manifest = load_held_out_manifest(PROJECT_ROOT / args.manifest)
    audit = _preflight(manifest, modes)
    output_dir = PROJECT_ROOT / args.output_dir
    output_dir.mkdir(parents=True, exist_ok=True)
    _write_json(output_dir / "preflight.json", audit)
    if args.verify_only:
        print(json.dumps({"verified": True, **audit}, ensure_ascii=False, sort_keys=True))
        return

    runs_path = output_dir / "runs.jsonl"
    existing = _existing_terminal_runs(runs_path)
    totals = _totals(existing.values())
    for task in manifest.tasks:
        for mode in modes:
            key = (task.task_id, mode)
            if key in existing:
                continue
            _assert_budget(totals, manifest.max_action_steps + 1, args.max_logical_calls, args.cost_cap_cny)
            trace_path = output_dir / "traces" / f"{task.task_id}--{mode}.jsonl"
            record = _run_one(manifest, task.task_id, mode, args, trace_path, audit)
            _append_jsonl(runs_path, record)
            existing[key] = record
            totals = _totals(existing.values())
            if record["status"] == "infrastructure_error":
                raise RuntimeError("held-out paused after infrastructure error; see runs.jsonl")
    _write_json(output_dir / "summary.json", _summary(existing.values(), manifest, modes, audit))


def _preflight(manifest: HeldOutManifest, modes: tuple[str, ...]) -> dict[str, Any]:
    from android_world import registry

    if os.getenv("MOBILEPILOT_ACTOR_MODEL") != manifest.model:
        raise ValueError(
            "MOBILEPILOT_ACTOR_MODEL must equal the frozen manifest model before any held-out call"
        )
    assert_registry_contains(
        manifest,
        registry.TaskRegistry().get_registry(registry.TaskRegistry.ANDROID_WORLD_FAMILY),
    )
    official_commit = _git_output(PROJECT_ROOT / ".local" / "android_world", "rev-parse", "HEAD")
    if official_commit != manifest.androidworld_commit:
        raise ValueError("AndroidWorld checkout commit differs from the frozen held-out manifest")
    return {
        "created_at": datetime.now(timezone.utc).isoformat(),
        "git_commit": _git_output(PROJECT_ROOT, "rev-parse", "HEAD"),
        "androidworld_commit": official_commit,
        "manifest_path": str(manifest.path),
        "manifest_task_hash": manifest.task_id_sha256,
        "model": manifest.model,
        "seed": manifest.seed,
        "max_action_steps": manifest.max_action_steps,
        "modes": list(modes),
        "frozen_source_sha256": _frozen_source_hash(),
        "task_count": len(manifest.tasks),
    }


def _run_one(
    manifest: HeldOutManifest,
    task_id: str,
    mode: str,
    args: argparse.Namespace,
    trace_path: Path,
    audit: dict[str, Any],
) -> dict[str, Any]:
    trace_path.parent.mkdir(parents=True, exist_ok=True)
    command = [
        sys.executable,
        str(PROJECT_ROOT / "scripts" / "run_mobilepilot_androidworld.py"),
        "--task", task_id,
        "--mode", mode,
        "--max-steps", str(manifest.max_action_steps),
        "--adb-path", args.adb_path,
        "--trace-path", str(trace_path),
        "--seed", str(manifest.seed),
    ]
    environment = os.environ.copy()
    environment["MOBILEPILOT_ACTOR_MODEL"] = manifest.model
    try:
        completed = subprocess.run(
            command,
            cwd=PROJECT_ROOT,
            env=environment,
            capture_output=True,
            text=True,
            timeout=args.task_timeout_seconds,
            check=False,
        )
    except subprocess.TimeoutExpired as exc:
        return _infrastructure_record(task_id, mode, trace_path, audit, f"task_timeout: {exc}")
    if completed.returncode != 0:
        return _infrastructure_record(task_id, mode, trace_path, audit, completed.stderr[-4000:])
    payload = _last_json_line(completed.stdout)
    if payload is None:
        return _infrastructure_record(task_id, mode, trace_path, audit, "single-task runner emitted no JSON summary")
    metrics = _trace_metrics(trace_path)
    reward = float(payload.get("official_reward", 0.0))
    return {
        "recorded_at": datetime.now(timezone.utc).isoformat(),
        "task_id": task_id,
        "mode": mode,
        "status": "success" if reward > 0 else "failure",
        "official_reward": reward,
        "initial_official_reward": payload.get("initial_official_reward"),
        "agent_data": payload.get("agent_data", {}),
        "reward_by_step": payload.get("reward_by_step", []),
        "elapsed_seconds": payload.get("elapsed_seconds"),
        "trace_path": str(trace_path),
        "runner_stdout": completed.stdout[-4000:],
        "runner_stderr": completed.stderr[-4000:],
        "audit": audit,
        **metrics,
    }


def _existing_terminal_runs(path: Path) -> dict[tuple[str, str], dict[str, Any]]:
    if not path.exists():
        return {}
    records: dict[tuple[str, str], dict[str, Any]] = {}
    for line in path.read_text(encoding="utf-8").splitlines():
        row = json.loads(line)
        if row.get("status") not in {"success", "failure"}:
            continue
        key = (row["task_id"], row["mode"])
        if key in records:
            raise ValueError(f"duplicate terminal held-out record: {key}")
        records[key] = row
    return records


def _totals(records: Any) -> dict[str, float]:
    rows = list(records)
    return {
        "logical_calls": sum(float(row.get("vlm_call_count", 0)) for row in rows),
        "estimated_cost_cny": sum(float(row.get("estimated_list_cost_cny", 0.0)) for row in rows),
    }


def _assert_budget(totals: dict[str, float], max_steps: int, max_calls: int, cost_cap: float) -> None:
    if totals["logical_calls"] + max_steps > max_calls:
        raise RuntimeError("held-out paused before exceeding the logical-call budget")
    if totals["estimated_cost_cny"] + max_steps * MAX_COST_PER_LOGICAL_CALL_CNY > cost_cap:
        raise RuntimeError("held-out paused before exceeding the cost safety bound")


def _trace_metrics(trace_path: Path) -> dict[str, Any]:
    rows = []
    if trace_path.exists():
        rows = [json.loads(line) for line in trace_path.read_text(encoding="utf-8").splitlines()]
    decisions = [row for row in rows if row.get("event") == "actor_decision"]
    observations = [row for row in rows if row.get("event") == "observation"]
    executions = [row for row in rows if row.get("event") == "execution"]
    critics = [row for row in rows if row.get("event") == "critic" and not row.get("allowed")]
    recoveries = [row for row in rows if row.get("event") == "recovery"]
    metrics = [row.get("metrics", {}) for row in decisions]
    return {
        "vlm_call_count": len(decisions),
        "invalid_output_count": sum(1 for row in decisions if not row.get("parsed")),
        "ui_tree_observation_count": sum(1 for row in observations if row.get("ui_element_count", 0) > 0),
        "executed_action_count": len(executions),
        "critic_block_count": len(critics),
        "recovery_count": len(recoveries),
        "prompt_tokens": sum(int(row.get("prompt_tokens") or 0) for row in metrics),
        "completion_tokens": sum(int(row.get("completion_tokens") or 0) for row in metrics),
        "total_tokens": sum(int(row.get("total_tokens") or 0) for row in metrics),
        "estimated_list_cost_cny": sum(float(row.get("estimated_list_cost_cny") or 0.0) for row in metrics),
        "model_latency_seconds": sum(float(row.get("latency_seconds") or 0.0) for row in metrics),
    }


def _summary(records: Any, manifest: HeldOutManifest, modes: tuple[str, ...], audit: dict[str, Any]) -> dict[str, Any]:
    rows = list(records)
    by_mode: dict[str, dict[str, Any]] = {}
    for mode in modes:
        subset = [row for row in rows if row.get("mode") == mode]
        by_mode[mode] = {
            "task_count": len(subset),
            "success_count": sum(row.get("official_reward", 0) > 0 for row in subset),
            "official_success_rate": (
                sum(row.get("official_reward", 0) > 0 for row in subset) / len(subset) if subset else 0.0
            ),
            **_totals(subset),
            "invalid_output_count": sum(row.get("invalid_output_count", 0) for row in subset),
            "ui_tree_observation_count": sum(row.get("ui_tree_observation_count", 0) for row in subset),
            "critic_block_count": sum(row.get("critic_block_count", 0) for row in subset),
            "recovery_count": sum(row.get("recovery_count", 0) for row in subset),
        }
    return {
        "audit": audit,
        "manifest": {
            "path": str(manifest.path),
            "androidworld_commit": manifest.androidworld_commit,
            "model": manifest.model,
            "seed": manifest.seed,
            "max_action_steps": manifest.max_action_steps,
            "task_id_sha256": manifest.task_id_sha256,
        },
        "by_mode": by_mode,
        "run_count": len(rows),
    }


def _last_json_line(text: str) -> dict[str, Any] | None:
    for line in reversed(text.splitlines()):
        try:
            parsed = json.loads(line)
        except json.JSONDecodeError:
            continue
        if isinstance(parsed, dict) and "official_reward" in parsed:
            return parsed
    return None


def _infrastructure_record(task_id: str, mode: str, trace_path: Path, audit: dict[str, Any], error: str) -> dict[str, Any]:
    return {
        "recorded_at": datetime.now(timezone.utc).isoformat(),
        "task_id": task_id,
        "mode": mode,
        "status": "infrastructure_error",
        "trace_path": str(trace_path),
        "audit": audit,
        "error": error,
    }


def _frozen_source_hash() -> str:
    digest = hashlib.sha256()
    for relative in FROZEN_SOURCE_FILES:
        digest.update(relative.encode("utf-8"))
        digest.update((PROJECT_ROOT / relative).read_bytes())
    return digest.hexdigest()


def _git_output(cwd: Path, *arguments: str) -> str:
    return subprocess.check_output(["git", *arguments], cwd=cwd, text=True).strip()


def _append_jsonl(path: Path, row: dict[str, Any]) -> None:
    with path.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(row, ensure_ascii=False, sort_keys=True) + "\n")


def _write_json(path: Path, value: dict[str, Any]) -> None:
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")


if __name__ == "__main__":
    main()
