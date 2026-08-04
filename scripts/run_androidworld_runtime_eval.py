"""Run auditable V1/V2 AndroidWorld Runtime comparisons without task retries."""

from __future__ import annotations

import argparse
from collections import Counter
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys
from typing import Any, Iterable


PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from mobile_pilot.androidworld.evaluation import (
    RuntimeEvalManifest,
    assert_registry_contains,
    load_runtime_eval_manifest,
)


FROZEN_SOURCE_FILES = (
    "mobile_pilot/androidworld/actor.py",
    "mobile_pilot/androidworld/agent.py",
    "mobile_pilot/androidworld/adapter.py",
    "mobile_pilot/androidworld/runtime_state.py",
    "scripts/run_mobilepilot_androidworld.py",
    "scripts/run_androidworld_runtime_eval.py",
)
MAX_COST_PER_LOGICAL_CALL_CNY = 0.02
DOWNLOAD_CACHE_ENV = "MOBILEPILOT_ANDROIDWORLD_DOWNLOAD_CACHE"
REQUIRED_A11Y_CACHE_FILE = "2024.05.13-accessibility_forwarder.apk"


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--manifest", required=True)
    parser.add_argument("--output-dir", required=True)
    parser.add_argument("--adb-path", required=True)
    parser.add_argument("--variant", action="append", choices=("v1", "v2"))
    parser.add_argument("--mode", choices=("vision_only", "hybrid"), default="hybrid")
    parser.add_argument("--verify-only", action="store_true")
    parser.add_argument("--max-logical-calls", type=int, default=400)
    parser.add_argument("--cost-cap-cny", type=float, default=15.0)
    parser.add_argument("--task-timeout-seconds", type=int, default=600)
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    manifest = load_runtime_eval_manifest(PROJECT_ROOT / args.manifest)
    variants = tuple(args.variant or manifest.variants or ("v2",))
    _validate_protocol(manifest, variants, args)
    output_dir = PROJECT_ROOT / args.output_dir
    output_dir.mkdir(parents=True, exist_ok=True)
    audit = _load_or_create_preflight(output_dir, manifest, variants, args)
    if args.verify_only:
        print(json.dumps({"verified": True, **audit}, ensure_ascii=False, sort_keys=True))
        return

    runs_path = output_dir / "runs.jsonl"
    existing = _existing_records(runs_path)
    totals = _totals(existing.values())
    for task in manifest.tasks:
        for variant in variants:
            key = (task.task_id, variant, args.mode)
            if key in existing:
                continue
            _assert_budget(
                totals,
                manifest.max_action_steps + 2,
                _max_calls(manifest, args),
                _cost_cap(manifest, args),
            )
            trace_path = output_dir / "traces" / f"{task.task_id}--{variant}--{args.mode}.jsonl"
            if trace_path.exists():
                raise RuntimeError(f"refusing to overwrite orphan Trace: {trace_path}")
            record = _run_one(manifest, task.task_id, variant, args, trace_path, audit)
            _append_jsonl(runs_path, record)
            existing[key] = record
            totals = _totals(existing.values())
            if record["status"] == "infrastructure_error":
                raise RuntimeError("evaluation paused after infrastructure error; do not retry the task")
    summary = _summary(existing.values(), manifest, variants, args.mode, audit)
    _write_json_once(output_dir / "summary.json", summary)


def _validate_protocol(
    manifest: RuntimeEvalManifest,
    variants: tuple[str, ...],
    args: argparse.Namespace,
) -> None:
    if len(variants) != len(set(variants)):
        raise ValueError("variants must not repeat")
    if manifest.evaluation_role == "frozen_evaluation":
        if variants != manifest.variants or args.mode != manifest.mode:
            raise ValueError("frozen evaluation variants or mode differ from the manifest")
        if args.max_logical_calls != 400 or args.cost_cap_cny != 15.0:
            raise ValueError("frozen budgets come from the manifest; do not override them")
    elif not args.variant:
        raise ValueError("development runs must explicitly select --variant")
    if not (0 < _cost_cap(manifest, args) <= 15):
        raise ValueError("cost cap must be within (0, 15]")


def _load_or_create_preflight(
    output_dir: Path,
    manifest: RuntimeEvalManifest,
    variants: tuple[str, ...],
    args: argparse.Namespace,
) -> dict[str, Any]:
    current = _preflight(manifest, variants, args)
    path = output_dir / "preflight.json"
    if not path.exists():
        _write_json_once(path, current)
        return current
    existing = json.loads(path.read_text(encoding="utf-8"))
    stable_keys = (
        "git_commit",
        "androidworld_commit",
        "manifest_task_hash",
        "model",
        "seed",
        "max_action_steps",
        "mode",
        "variants",
        "frozen_source_sha256",
        "evaluation_role",
        "task_count",
        "androidworld_download_cache",
    )
    if any(existing.get(key) != current.get(key) for key in stable_keys):
        raise RuntimeError("existing preflight differs from the current frozen protocol")
    return existing


def _preflight(
    manifest: RuntimeEvalManifest,
    variants: tuple[str, ...],
    args: argparse.Namespace,
) -> dict[str, Any]:
    from android_world import registry

    if os.getenv("MOBILEPILOT_ACTOR_MODEL") != manifest.model:
        raise ValueError("MOBILEPILOT_ACTOR_MODEL differs from the evaluation manifest")
    assert_registry_contains(
        manifest,
        registry.TaskRegistry().get_registry(registry.TaskRegistry.ANDROID_WORLD_FAMILY),
    )
    official_commit = _git_output(PROJECT_ROOT / ".local" / "android_world", "rev-parse", "HEAD")
    if official_commit != manifest.androidworld_commit:
        raise ValueError("AndroidWorld checkout commit differs from the evaluation manifest")
    serials = _adb_serials(args.adb_path)
    if serials != ["emulator-5554"]:
        raise RuntimeError(
            "evaluation requires exactly emulator-5554 and refuses real or additional devices: "
            + repr(serials)
        )
    source_hash = _frozen_source_hash()
    download_cache = _validated_download_cache(manifest.evaluation_role)
    if manifest.evaluation_role == "frozen_evaluation":
        if source_hash != manifest.frozen_source_sha256:
            raise ValueError("Agent source differs from the frozen evaluation manifest")
        if _git_output(PROJECT_ROOT, "status", "--porcelain", "--untracked-files=no"):
            raise ValueError("tracked workspace changes are forbidden for frozen evaluation")
    return {
        "created_at": datetime.now(timezone.utc).isoformat(),
        "git_commit": _git_output(PROJECT_ROOT, "rev-parse", "HEAD"),
        "androidworld_commit": official_commit,
        "manifest_path": str(manifest.path),
        "manifest_task_hash": manifest.task_id_sha256,
        "model": manifest.model,
        "seed": manifest.seed,
        "max_action_steps": manifest.max_action_steps,
        "mode": args.mode,
        "variants": list(variants),
        "frozen_source_sha256": source_hash,
        "evaluation_role": manifest.evaluation_role,
        "task_count": len(manifest.tasks),
        "device_serials": serials,
        "max_logical_calls": _max_calls(manifest, args),
        "cost_cap_cny": _cost_cap(manifest, args),
        "androidworld_download_cache": download_cache,
    }


def _run_one(
    manifest: RuntimeEvalManifest,
    task_id: str,
    variant: str,
    args: argparse.Namespace,
    trace_path: Path,
    audit: dict[str, Any],
) -> dict[str, Any]:
    trace_path.parent.mkdir(parents=True, exist_ok=True)
    command = [
        sys.executable,
        str(PROJECT_ROOT / "scripts" / "run_mobilepilot_androidworld.py"),
        "--task", task_id,
        "--mode", args.mode,
        "--runtime-version", variant,
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
        return _infrastructure_record(task_id, variant, args.mode, trace_path, audit, f"task_timeout: {exc}")
    if completed.returncode != 0:
        return _infrastructure_record(task_id, variant, args.mode, trace_path, audit, completed.stderr[-4000:])
    payload = _last_json_line(completed.stdout)
    if payload is None:
        return _infrastructure_record(
            task_id,
            variant,
            args.mode,
            trace_path,
            audit,
            "single-task runner emitted no JSON summary",
        )
    metrics = _trace_metrics(trace_path)
    reward = float(payload.get("official_reward", 0.0))
    return {
        "recorded_at": datetime.now(timezone.utc).isoformat(),
        "task_id": task_id,
        "variant": variant,
        "mode": args.mode,
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


def _trace_metrics(trace_path: Path) -> dict[str, Any]:
    rows = [
        json.loads(line)
        for line in trace_path.read_text(encoding="utf-8").splitlines()
    ] if trace_path.exists() else []
    decisions = [row for row in rows if row.get("event") == "actor_decision"]
    observations = [row for row in rows if row.get("event") == "observation"]
    executions = [row for row in rows if row.get("event") == "execution"]
    finish = next((row for row in reversed(rows) if row.get("event") == "agent_finished"), {})
    recovery_outcomes = [row for row in rows if row.get("event") == "agent_recovery_outcome"]
    guard_rows = [row for row in rows if row.get("event") == "protocol_guard"]
    usage = [row.get("metrics", {}) for row in decisions]
    tree_reasons = Counter(
        str(row.get("ui_tree_trigger_reason"))
        for row in observations
        if row.get("ui_tree_requested")
    )
    return {
        "terminal_reason": finish.get("reason", "official_success_without_agent_finish"),
        "vlm_call_count": len(decisions),
        "invalid_decision_count": sum(not row.get("parsed") for row in decisions),
        "protocol_normalization_count": sum(bool(row.get("protocol_normalized")) for row in decisions),
        "protocol_retry_trigger_count": sum(row.get("outcome") == "triggered" for row in guard_rows),
        "protocol_retry_action_obtained_count": sum(
            row.get("strategy") == "structured_retry" and row.get("outcome") == "action_obtained"
            for row in guard_rows
        ),
        "executed_action_count": len(executions),
        "execution_failure_count": sum(not row.get("executed") for row in executions),
        "loop_detection_count": sum(row.get("event") == "loop_detected" for row in rows),
        "recovery_trigger_count": sum(row.get("event") == "agent_recovery_triggered" for row in rows),
        "recovery_rescue_count": sum(bool(row.get("rescued")) for row in recovery_outcomes),
        "recovery_misfire_count": sum(bool(row.get("misfire")) for row in recovery_outcomes),
        "ui_tree_request_count": sum(bool(row.get("ui_tree_requested")) for row in observations),
        "ui_tree_trigger_reasons": dict(sorted(tree_reasons.items())),
        "ui_tree_changed_action_count": sum(
            row.get("event") == "ui_tree_decision" and row.get("changed_action") is True
            for row in rows
        ),
        "prompt_tokens": sum(int(row.get("prompt_tokens") or 0) for row in usage),
        "completion_tokens": sum(int(row.get("completion_tokens") or 0) for row in usage),
        "total_tokens": sum(int(row.get("total_tokens") or 0) for row in usage),
        "estimated_list_cost_cny": sum(float(row.get("estimated_list_cost_cny") or 0.0) for row in usage),
        "model_latency_seconds": sum(float(row.get("latency_seconds") or 0.0) for row in usage),
    }


def _summary(
    records: Iterable[dict[str, Any]],
    manifest: RuntimeEvalManifest,
    variants: tuple[str, ...],
    mode: str,
    audit: dict[str, Any],
) -> dict[str, Any]:
    rows = list(records)
    by_variant: dict[str, dict[str, Any]] = {}
    for variant in variants:
        subset = [row for row in rows if row.get("variant") == variant]
        success = sum(float(row.get("official_reward", 0.0)) > 0 for row in subset)
        actions = sum(int(row.get("executed_action_count", 0)) for row in subset)
        reasons = Counter(
            str(row.get("terminal_reason", "unknown"))
            for row in subset
            if float(row.get("official_reward", 0.0)) <= 0
        )
        by_variant[variant] = {
            "task_count": len(subset),
            "success_count": success,
            "official_success_rate": success / len(subset) if subset else 0.0,
            "invalid_output_terminal_count": reasons.get("invalid_actor_output", 0),
            "step_budget_exhausted_count": reasons.get("step_budget_exhausted", 0),
            "loop_detection_count": sum(int(row.get("loop_detection_count", 0)) for row in subset),
            "recovery_trigger_count": sum(int(row.get("recovery_trigger_count", 0)) for row in subset),
            "recovery_rescue_count": sum(int(row.get("recovery_rescue_count", 0)) for row in subset),
            "recovery_misfire_count": sum(int(row.get("recovery_misfire_count", 0)) for row in subset),
            "ui_tree_request_count": sum(int(row.get("ui_tree_request_count", 0)) for row in subset),
            "executed_action_count": actions,
            "average_executed_actions": actions / len(subset) if subset else 0.0,
            "vlm_call_count": sum(int(row.get("vlm_call_count", 0)) for row in subset),
            "total_tokens": sum(int(row.get("total_tokens", 0)) for row in subset),
            "model_latency_seconds": sum(float(row.get("model_latency_seconds", 0.0)) for row in subset),
            "estimated_list_cost_cny": sum(float(row.get("estimated_list_cost_cny", 0.0)) for row in subset),
            "failure_taxonomy": dict(sorted(reasons.items())),
        }
    paired = _paired_outcomes(rows, variants) if len(variants) == 2 else {}
    return {
        "audit": audit,
        "manifest": {
            "path": str(manifest.path),
            "evaluation_role": manifest.evaluation_role,
            "androidworld_commit": manifest.androidworld_commit,
            "model": manifest.model,
            "seed": manifest.seed,
            "max_action_steps": manifest.max_action_steps,
            "task_id_sha256": manifest.task_id_sha256,
            "mode": mode,
            "variants": list(variants),
        },
        "by_variant": by_variant,
        "paired_outcomes": paired,
        "run_count": len(rows),
        "total_estimated_list_cost_cny": sum(
            float(row.get("estimated_list_cost_cny", 0.0)) for row in rows
        ),
    }


def _paired_outcomes(rows: list[dict[str, Any]], variants: tuple[str, ...]) -> dict[str, int]:
    first, second = variants
    table = {(row["task_id"], row["variant"]): float(row.get("official_reward", 0)) > 0 for row in rows}
    outcomes = Counter()
    for task_id in sorted({row["task_id"] for row in rows}):
        key1, key2 = (task_id, first), (task_id, second)
        if key1 not in table or key2 not in table:
            continue
        outcomes[f"{first}_{'success' if table[key1] else 'failure'}__{second}_{'success' if table[key2] else 'failure'}"] += 1
    return dict(sorted(outcomes.items()))


def _existing_records(path: Path) -> dict[tuple[str, str, str], dict[str, Any]]:
    if not path.exists():
        return {}
    records: dict[tuple[str, str, str], dict[str, Any]] = {}
    for line in path.read_text(encoding="utf-8").splitlines():
        row = json.loads(line)
        key = (row["task_id"], row["variant"], row["mode"])
        if key in records:
            raise ValueError(f"duplicate evaluation record: {key}")
        if row.get("status") == "infrastructure_error":
            raise RuntimeError(f"previous infrastructure error forbids automatic retry: {key}")
        records[key] = row
    return records


def _totals(records: Iterable[dict[str, Any]]) -> dict[str, float]:
    rows = list(records)
    return {
        "logical_calls": sum(float(row.get("vlm_call_count", 0)) for row in rows),
        "estimated_cost_cny": sum(float(row.get("estimated_list_cost_cny", 0.0)) for row in rows),
    }


def _assert_budget(totals: dict[str, float], reserve_calls: int, max_calls: int, cost_cap: float) -> None:
    if totals["logical_calls"] + reserve_calls > max_calls:
        raise RuntimeError("evaluation paused before exceeding the logical-call budget")
    if totals["estimated_cost_cny"] + reserve_calls * MAX_COST_PER_LOGICAL_CALL_CNY > cost_cap:
        raise RuntimeError("evaluation paused before exceeding the cost safety bound")


def _max_calls(manifest: RuntimeEvalManifest, args: argparse.Namespace) -> int:
    return manifest.max_logical_calls or args.max_logical_calls


def _cost_cap(manifest: RuntimeEvalManifest, args: argparse.Namespace) -> float:
    return manifest.cost_cap_cny or args.cost_cap_cny


def _adb_serials(adb_path: str) -> list[str]:
    output = subprocess.check_output([adb_path, "devices"], text=True)
    serials = []
    for line in output.splitlines()[1:]:
        fields = line.split()
        if len(fields) >= 2 and fields[1] == "device":
            serials.append(fields[0])
    return serials


def _frozen_source_hash() -> str:
    digest = hashlib.sha256()
    for relative in FROZEN_SOURCE_FILES:
        digest.update(relative.encode("utf-8"))
        digest.update((PROJECT_ROOT / relative).read_bytes())
    return digest.hexdigest()


def _validated_download_cache(evaluation_role: str) -> str:
    configured = os.getenv(DOWNLOAD_CACHE_ENV)
    if not configured:
        if evaluation_role == "frozen_evaluation":
            raise ValueError(
                f"{DOWNLOAD_CACHE_ENV} is required for frozen evaluation"
            )
        return ""
    cache = Path(configured).resolve()
    required = cache / REQUIRED_A11Y_CACHE_FILE
    if evaluation_role == "frozen_evaluation" and (
        not required.is_file() or required.stat().st_size == 0
    ):
        raise ValueError(
            "frozen evaluation requires the cached official Accessibility "
            f"Forwarder APK: {required}"
        )
    return str(cache)


def _last_json_line(text: str) -> dict[str, Any] | None:
    for line in reversed(text.splitlines()):
        try:
            parsed = json.loads(line)
        except json.JSONDecodeError:
            continue
        if isinstance(parsed, dict) and "official_reward" in parsed:
            return parsed
    return None


def _infrastructure_record(
    task_id: str,
    variant: str,
    mode: str,
    trace_path: Path,
    audit: dict[str, Any],
    error: str,
) -> dict[str, Any]:
    return {
        "recorded_at": datetime.now(timezone.utc).isoformat(),
        "task_id": task_id,
        "variant": variant,
        "mode": mode,
        "status": "infrastructure_error",
        "trace_path": str(trace_path),
        "audit": audit,
        "error": error,
    }


def _git_output(cwd: Path, *arguments: str) -> str:
    return subprocess.check_output(["git", *arguments], cwd=cwd, text=True).strip()


def _append_jsonl(path: Path, row: dict[str, Any]) -> None:
    with path.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(row, ensure_ascii=False, sort_keys=True) + "\n")


def _write_json_once(path: Path, value: dict[str, Any]) -> None:
    serialized = json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True) + "\n"
    if path.exists():
        if path.read_text(encoding="utf-8") != serialized:
            raise RuntimeError(f"refusing to overwrite existing evaluation artifact: {path}")
        return
    path.write_text(serialized, encoding="utf-8")


if __name__ == "__main__":
    main()
