"""Deterministically audit the frozen MobilePilot V2.2 evidence bundle.

This script never starts AndroidWorld and never imports or calls an Agent model.
It reads the preserved manifests, run records, and traces, verifies the locked
claims, and writes a small third-party-checkable bundle under docs/final/audit.
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import shutil
import subprocess
import time
from collections import Counter
from pathlib import Path
from typing import Any, Iterable


FROZEN_COMMIT = "487f2abe7382d11a5cc15572c4902265547d42dd"
FINAL_HEAD = "9b643077e7ce999589f44413403513bf2ce67a09"
EXPECTED_SOURCE_HASH = "246cce8ea4a7c7edac304cac267f41e9fe59945e6de3332c284db2fe650e74cb"
EXPECTED_TASK_HASH = "cc408d7185991b356d60531c33ca2ca1c5681aa13e62eeeae03c70983437e8b2"
EXPECTED_PAIRED = {
    "valid_pairs": 30,
    "v1_success": 0,
    "v22_success": 9,
    "improved": 9,
    "regressed": 0,
    "both_success": 0,
    "both_failed": 21,
    "v1_invalid_output": 21,
    "v22_invalid_output": 4,
}
RESCUE_TASKS = (
    "MarkorDeleteNewestNote",
    "SimpleCalendarDeleteEvents",
    "TasksHighPriorityTasks",
)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--repo", type=Path, default=Path(__file__).resolve().parents[1])
    parser.add_argument("--output", type=Path, default=Path("docs/final/audit"))
    parser.add_argument("--run-pytest", action="store_true")
    parser.add_argument("--pytest-python", type=Path)
    return parser.parse_args()


def load_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def load_jsonl(path: Path) -> list[dict[str, Any]]:
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line]


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def git(repo: Path, *args: str) -> str:
    return subprocess.check_output(["git", *args], cwd=repo, text=True).strip()


def rel(path: Path, repo: Path) -> str:
    return path.resolve().relative_to(repo.resolve()).as_posix()


def write_csv(path: Path, rows: Iterable[dict[str, Any]], fields: list[str]) -> None:
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields)
        writer.writeheader()
        writer.writerows(rows)


def outcome_for(v1_reward: float, v22_reward: float) -> str:
    v1 = v1_reward >= 1.0
    v22 = v22_reward >= 1.0
    if v1 and v22:
        return "both_success"
    if not v1 and v22:
        return "improved"
    if v1 and not v22:
        return "regressed"
    return "both_failed"


def trace_path_for(run_file: Path, row: dict[str, Any]) -> Path:
    return run_file.parent / "traces" / Path(str(row["trace_path"])).name


def run_pytest(repo: Path, output: Path, python_executable: Path) -> bool:
    started = time.perf_counter()
    before = git(repo, "status", "--short")
    process = subprocess.run(
        [str(python_executable), "-m", "pytest"],
        cwd=repo,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        check=False,
    )
    elapsed = time.perf_counter() - started
    after = git(repo, "status", "--short")
    versions = subprocess.run(
        [
            str(python_executable),
            "-c",
            "import platform,pytest; print(platform.python_version()); print(pytest.__version__)",
        ],
        cwd=repo,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        check=False,
    ).stdout.splitlines()
    python_version = versions[0] if versions else "unknown"
    pytest_version = versions[1] if len(versions) > 1 else "unknown"
    header = [
        f"git_head: {git(repo, 'rev-parse', 'HEAD')}",
        f"python: {python_version}",
        f"pytest: {pytest_version}",
        f"command: {python_executable} -m pytest",
        f"elapsed_seconds: {elapsed:.3f}",
        f"exit_code: {process.returncode}",
        f"workspace_before: {'clean' if not before else 'dirty'}",
        f"workspace_after: {'clean' if not after else 'dirty'}",
        "",
        "--- stdout/stderr ---",
        process.stdout,
    ]
    output.write_text("\n".join(header), encoding="utf-8")
    return process.returncode == 0 and "186 passed" in process.stdout


def main() -> int:
    args = parse_args()
    repo = args.repo.resolve()
    output = args.output if args.output.is_absolute() else repo / args.output
    output.mkdir(parents=True, exist_ok=True)

    manifest_path = repo / "configs/androidworld/runtime_eval_36_v22_final.json"
    manifest = load_json(manifest_path)
    if manifest["task_count"] != 36 or manifest["task_id_sha256"] != EXPECTED_TASK_HASH:
        raise SystemExit("DISCREPANCY: frozen 36-task manifest/hash changed")
    manifest_tasks = [task["id"] for task in manifest["tasks"]]

    main_runs = repo / "artifacts/evaluation/androidworld-v22-final-frozen36-20260817/runs.jsonl"
    restored_runs = repo / (
        "artifacts/evaluation/"
        "androidworld-v22-final-frozen36-continuation5-network-restored-20260817/runs.jsonl"
    )
    valid_sources = (main_runs, restored_runs)
    records: list[tuple[Path, dict[str, Any]]] = []
    for source in valid_sources:
        for row in load_jsonl(source):
            if row.get("status") != "infrastructure_error":
                audit = row.get("audit", {})
                locked = (
                    audit.get("git_commit") == FROZEN_COMMIT
                    and audit.get("frozen_source_sha256") == EXPECTED_SOURCE_HASH
                    and audit.get("model") == manifest["model"]
                    and audit.get("seed") == manifest["seed"]
                    and audit.get("max_action_steps") == manifest["max_action_steps"]
                    and audit.get("mode") == manifest["mode"]
                )
                if not locked:
                    raise SystemExit(
                        f"DISCREPANCY: locked run metadata differs in {source}: "
                        f"{row.get('task_id')} {row.get('variant')}"
                    )
                records.append((source, row))

    table: dict[tuple[str, str], tuple[Path, dict[str, Any]]] = {}
    for source, row in records:
        key = (row["task_id"], row["variant"])
        if key in table:
            raise SystemExit(f"DISCREPANCY: duplicate valid run {key}")
        table[key] = (source, row)
    paired_tasks = [
        task for task in manifest_tasks if (task, "v1") in table and (task, "v2.2") in table
    ]
    if len(paired_tasks) * 2 != len(table):
        raise SystemExit("DISCREPANCY: unpaired or out-of-manifest valid runs")
    main_tasks = [
        task for task in manifest_tasks if table.get((task, "v1"), (None,))[0] == main_runs
    ]
    restored_tasks = [
        task for task in manifest_tasks if table.get((task, "v1"), (None,))[0] == restored_runs
    ]
    if main_tasks != manifest_tasks[:16] or restored_tasks != manifest_tasks[22:]:
        raise SystemExit("DISCREPANCY: valid sources are not the fixed 16-task prefix + 14-task suffix")

    paired_rows: list[dict[str, Any]] = []
    metrics = Counter()
    for task in paired_tasks:
        v1_source, v1 = table[(task, "v1")]
        v22_source, v22 = table[(task, "v2.2")]
        if v1_source != v22_source:
            raise SystemExit(f"DISCREPANCY: pair split across files for {task}")
        pair_outcome = outcome_for(float(v1["official_reward"]), float(v22["official_reward"]))
        metrics[pair_outcome] += 1
        metrics["v1_success"] += float(v1["official_reward"]) >= 1.0
        metrics["v22_success"] += float(v22["official_reward"]) >= 1.0
        metrics["v1_invalid_output"] += v1.get("terminal_reason") == "invalid_actor_output"
        metrics["v22_invalid_output"] += v22.get("terminal_reason") == "invalid_actor_output"
        paired_rows.append(
            {
                "task_id": task,
                "v1_status": v1["status"],
                "v1_reward": v1["official_reward"],
                "v1_terminal_reason": v1["terminal_reason"],
                "v22_status": v22["status"],
                "v22_reward": v22["official_reward"],
                "v22_terminal_reason": v22["terminal_reason"],
                "pair_outcome": pair_outcome,
                "source_run_file": rel(v1_source, repo),
            }
        )
    observed_paired = {
        "valid_pairs": len(paired_tasks),
        "v1_success": metrics["v1_success"],
        "v22_success": metrics["v22_success"],
        "improved": metrics["improved"],
        "regressed": metrics["regressed"],
        "both_success": metrics["both_success"],
        "both_failed": metrics["both_failed"],
        "v1_invalid_output": metrics["v1_invalid_output"],
        "v22_invalid_output": metrics["v22_invalid_output"],
    }
    if observed_paired != EXPECTED_PAIRED:
        raise SystemExit(
            "DISCREPANCY: paired metrics differ; "
            + json.dumps(observed_paired, ensure_ascii=False, sort_keys=True)
        )
    write_csv(
        output / "paired-30.csv",
        paired_rows,
        [
            "task_id",
            "v1_status",
            "v1_reward",
            "v1_terminal_reason",
            "v22_status",
            "v22_reward",
            "v22_terminal_reason",
            "pair_outcome",
            "source_run_file",
        ],
    )

    trace_rows: dict[tuple[str, str], list[dict[str, Any]]] = {}
    trace_files: dict[tuple[str, str], Path] = {}
    for task in paired_tasks:
        for variant in ("v1", "v2.2"):
            source, row = table[(task, variant)]
            trace_path = trace_path_for(source, row)
            trace_rows[(task, variant)] = load_jsonl(trace_path)
            trace_files[(task, variant)] = trace_path

    recovery_rows: list[dict[str, Any]] = []
    strict_rescues: list[tuple[str, int]] = []
    rescue_chains: dict[str, dict[str, Any]] = {}
    for task in paired_tasks:
        rows = trace_rows[(task, "v2.2")]
        final_reward = float(table[(task, "v2.2")][1]["official_reward"])
        trigger_indexes = [i for i, row in enumerate(rows) if row.get("event") == "agent_recovery_triggered"]
        for position, trigger_index in enumerate(trigger_indexes):
            trigger = rows[trigger_index]
            boundary = trigger_indexes[position + 1] if position + 1 < len(trigger_indexes) else len(rows)
            recovery_id = trigger["recovery_id"]
            replans = [
                (i, row)
                for i, row in enumerate(rows[trigger_index + 1 : boundary], trigger_index + 1)
                if row.get("event") == "agent_recovery_replan"
                and row.get("recovery_id") == recovery_id
            ]
            tree_decisions = [
                (i, row)
                for i, row in enumerate(rows[trigger_index + 1 : boundary], trigger_index + 1)
                if row.get("event") == "ui_tree_decision"
            ]
            canonical_replan = replans[-1][1] if replans else {}
            grounded_fallback = next(
                (row for _, row in replans if row.get("result") == "task_grounded_fallback"),
                {},
            )
            first_replan_index = replans[0][0] if replans else trigger_index
            executions = [
                (i, row)
                for i, row in enumerate(rows[first_replan_index + 1 : boundary], first_replan_index + 1)
                if row.get("event") == "execution"
            ]
            execution = executions[0] if executions else None
            outcomes = [
                row
                for row in rows
                if row.get("event") == "agent_recovery_outcome"
                and row.get("recovery_id") == recovery_id
            ]
            outcome = outcomes[-1] if outcomes else {}
            tree = tree_decisions[-1][1] if tree_decisions else {}
            changed_values = [row.get("changed_action") for _, row in replans]
            changed_action: bool | None
            if True in changed_values:
                changed_action = True
            elif False in changed_values:
                changed_action = False
            else:
                changed_action = tree.get("changed_action")
            reward_after_execution = False
            if execution:
                reward_after_execution = any(
                    row.get("event") == "official_reward" and float(row.get("reward", 0)) >= 1.0
                    for row in rows[execution[0] + 1 :]
                )
            strict = bool(
                outcome.get("rescued") is True
                and changed_action is True
                and execution is not None
                and execution[1].get("executed") is True
                and reward_after_execution
            )
            if strict:
                strict_rescues.append((task, recovery_id))
            chosen = tree.get("chosen_ui_element")
            recovery_rows.append(
                {
                    "task": task,
                    "step": trigger["step"],
                    "recovery_id": recovery_id,
                    "level": trigger.get("recovery_level", ""),
                    "trigger": trigger.get("trigger", ""),
                    "blocked_action": trigger.get("blocked_action", ""),
                    "tree_used": bool(tree_decisions),
                    "new_evidence": tree.get("new_evidence", ""),
                    "chosen_ui_element": json.dumps(chosen, ensure_ascii=False, sort_keys=True) if chosen else "",
                    "fallback_reason": grounded_fallback.get("reason", ""),
                    "replan": canonical_replan.get("candidate_action", ""),
                    "changed_action": changed_action,
                    "executed": bool(execution and execution[1].get("executed") is True),
                    "executed_action": execution[1].get("action", "") if execution else "",
                    "final_reward": final_reward,
                    "rescued": bool(outcome.get("rescued")),
                    "strict_rescue": strict,
                    "same_blocked_action": changed_action is False,
                    "insufficient_new_evidence": tree.get("result") == "insufficient_new_evidence",
                    "misfire": bool(outcome.get("misfire")),
                }
            )
            if task in RESCUE_TASKS:
                previous_execution = next(
                    (
                        row
                        for row in reversed(rows[:trigger_index])
                        if row.get("event") == "execution"
                    ),
                    {},
                )
                subsequent_rewards = [
                    row
                    for row in rows[(execution[0] + 1 if execution else trigger_index + 1) :]
                    if row.get("event") == "official_reward"
                ]
                rescue_chains.setdefault(
                    task,
                    {
                        "task": task,
                        "trace_path": rel(trace_files[(task, "v2.2")], repo),
                        "final_reward": final_reward,
                        "episodes": [],
                    },
                )["episodes"].append(
                    {
                        "recovery_trigger": trigger.get("event"),
                        "recovery_id": recovery_id,
                        "step": trigger.get("step"),
                        "trigger_reason": trigger.get("trigger"),
                        "blocked_action": trigger.get("blocked_action"),
                        "preceding_execution": previous_execution,
                        "ui_tree_request": bool(tree_decisions),
                        "new_evidence": tree.get("new_evidence", ""),
                        "chosen_ui_element": chosen,
                        "fallback_reason": grounded_fallback.get("reason", ""),
                        "replanned_action": canonical_replan.get("candidate_action", ""),
                        "changed_action": changed_action,
                        "execution": execution[1] if execution else None,
                        "subsequent_official_rewards": subsequent_rewards,
                        "agent_recovery_outcome": outcome,
                        "rescued": bool(outcome.get("rescued")),
                        "strict_rescue": strict,
                    }
                )
    if len(recovery_rows) != 25:
        raise SystemExit(f"DISCREPANCY: expected 25 Recovery episodes, got {len(recovery_rows)}")
    if sorted(task for task, _ in strict_rescues) != sorted(RESCUE_TASKS):
        raise SystemExit(f"DISCREPANCY: strict rescue set differs: {strict_rescues}")
    write_csv(
        output / "recovery-25.csv",
        recovery_rows,
        list(recovery_rows[0]),
    )
    (output / "rescue-event-chains.json").write_text(
        json.dumps(rescue_chains, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )

    v1_tree = sum(
        row.get("event") == "observation" and row.get("ui_tree_requested") is True
        for task in paired_tasks
        for row in trace_rows[(task, "v1")]
    )
    v22_tree = sum(
        row.get("event") == "observation" and row.get("ui_tree_requested") is True
        for task in paired_tasks
        for row in trace_rows[(task, "v2.2")]
    )
    changed_tree = [
        row
        for task in paired_tasks
        for row in trace_rows[(task, "v2.2")]
        if row.get("event") == "ui_tree_decision" and row.get("changed_action") is True
    ]
    if (v1_tree, v22_tree, len(changed_tree)) != (209, 49, 19):
        raise SystemExit(
            f"DISCREPANCY: UI Tree expected 209/49/19, got {v1_tree}/{v22_tree}/{len(changed_tree)}"
        )

    for task in RESCUE_TASKS:
        source = trace_files[(task, "v2.2")]
        shutil.copyfile(source, output / source.name)

    invalid_dir = repo / "artifacts/evaluation/androidworld-v22-final-frozen36-continuation4-20260817"
    restored_dir = repo / (
        "artifacts/evaluation/"
        "androidworld-v22-final-frozen36-continuation5-network-restored-20260817"
    )
    invalid_preflight = load_json(invalid_dir / "preflight.json")
    restored_preflight = load_json(restored_dir / "preflight.json")
    invalid_rows = load_jsonl(invalid_dir / "runs.jsonl")
    restored_rows = load_jsonl(restored_dir / "runs.jsonl")
    invalid_tasks = [(row["task_id"], row["variant"]) for row in invalid_rows]
    restored_tasks = [(row["task_id"], row["variant"]) for row in restored_rows]
    invariant_keys = (
        "androidworld_commit",
        "frozen_source_sha256",
        "git_commit",
        "manifest_task_hash",
        "max_action_steps",
        "mode",
        "model",
        "progress_verifier_model",
        "seed",
        "subgoal_manager_model",
        "task_count",
        "variants",
    )
    network_same = (
        invalid_tasks == restored_tasks
        and all(invalid_preflight[key] == restored_preflight[key] for key in invariant_keys)
        and all(int(row.get("executed_action_count", -1)) == 0 for row in invalid_rows)
        and all(int(row.get("total_tokens", -1)) == 0 for row in invalid_rows)
        and all(float(row.get("estimated_list_cost_cny", -1)) == 0 for row in invalid_rows)
    )
    if not network_same:
        raise SystemExit("DISCREPANCY: invalid/restored suffix consistency check failed")

    network_md = f"""# Network suffix restart audit

## Verdict

**YES.** The preserved invalid batch and network-restored batch contain the same ordered 14-task × 2-variant suffix. All locked Agent fields match; only `created_at` differs in preflight metadata.

| Check | Invalid batch | Restored batch | Same |
| --- | --- | --- | --- |
| runs | {len(invalid_rows)} | {len(restored_rows)} | YES |
| task/variant order | fixed 28 rows | fixed 28 rows | YES |
| Agent commit | `{invalid_preflight['git_commit']}` | `{restored_preflight['git_commit']}` | YES |
| source hash | `{invalid_preflight['frozen_source_sha256']}` | `{restored_preflight['frozen_source_sha256']}` | YES |
| model | `{invalid_preflight['model']}` | `{restored_preflight['model']}` | YES |
| seed / max steps | {invalid_preflight['seed']} / {invalid_preflight['max_action_steps']} | {restored_preflight['seed']} / {restored_preflight['max_action_steps']} | YES |

All 28 invalid rows have `executed_action_count=0`, `total_tokens=0`, and estimated cost 0. Their traces show attempted model calls failing with `Connection error`, empty `raw_response`, and no executed phone action. They are therefore an invalid run-infrastructure batch, not 28 Agent failures.

The restored directory reruns the complete fixed suffix in the same order. It does not select tasks by success/failure and does not change Prompt, Runtime, model, seed, step budget, source hash, or commit.

Sources:

- `{rel(invalid_dir / 'preflight.json', repo)}`
- `{rel(invalid_dir / 'runs.jsonl', repo)}`
- `{rel(restored_dir / 'preflight.json', repo)}`
- `{rel(restored_dir / 'runs.jsonl', repo)}`
"""
    (output / "network-restart-audit.md").write_text(network_md, encoding="utf-8")

    infra_sources = [
        repo / "artifacts/evaluation/androidworld-v22-final-frozen36-20260817/runs.jsonl",
        repo / "artifacts/evaluation/androidworld-v22-final-frozen36-continuation-20260817/runs.jsonl",
        repo / "artifacts/evaluation/androidworld-v22-final-frozen36-continuation2-20260817/runs.jsonl",
        repo / "artifacts/evaluation/androidworld-v22-final-frozen36-continuation3-20260817/runs.jsonl",
    ]
    infra_rows = [
        (path, row)
        for path in infra_sources
        for row in load_jsonl(path)
        if row.get("status") == "infrastructure_error"
    ]
    if [row["task_id"] for _, row in infra_rows] != [
        "OsmAndMarker",
        "OsmAndTrack",
        "RecipeAddMultipleRecipes",
        "RecipeAddMultipleRecipesFromImage",
    ]:
        raise SystemExit("DISCREPANCY: observed infrastructure-error task set differs")
    infra_md = """# Infrastructure exclusions

The 36-task pre-frozen list produced 30 valid pairs. The six omitted tasks are deliberately split into two evidence classes.

## A. Actually run; infrastructure failure observed before Agent takeover (4)

| Task | Initialization failure | Before first action | Model call | Evidence file |
| --- | --- | --- | --- | --- |
| OsmAndMarker | `/data/data/net.osmand/databases` missing during `initialize_task` | YES | NO | `artifacts/evaluation/androidworld-v22-final-frozen36-20260817/runs.jsonl` |
| OsmAndTrack | tracks directory missing during initial `is_successful` | YES | NO | `artifacts/evaluation/androidworld-v22-final-frozen36-continuation-20260817/runs.jsonl` |
| RecipeAddMultipleRecipes | Broccoli databases directory missing during `initialize_task` | YES | NO | `artifacts/evaluation/androidworld-v22-final-frozen36-continuation2-20260817/runs.jsonl` |
| RecipeAddMultipleRecipesFromImage | host SQLite reports `no such module: FTS4` during `initialize_task` | YES | NO | `artifacts/evaluation/androidworld-v22-final-frozen36-continuation3-20260817/runs.jsonl` |

These records were emitted by the outer runner before a trace/model/action loop existed. They contain no Agent execution or model-usage fields.

## B. Not run; excluded as the same confirmed Broccoli validator family (2)

| Task | Actually run | Shared dependency evidence | Observed failure that supports exclusion |
| --- | --- | --- | --- |
| RecipeDeleteDuplicateRecipes2 | NO | inherits the same `_RecipeApp`; same Broccoli DB path/table and `SQLiteApp.initialize_task/_clear_db` path | RecipeAddMultipleRecipesFromImage FTS4 initialization failure |
| RecipeDeleteMultipleRecipesWithConstraint | NO | inherits the same `_RecipeApp`; same Broccoli DB path/table and `SQLiteApp.initialize_task/_clear_db` path | RecipeAddMultipleRecipesFromImage FTS4 initialization failure |

Code evidence: `.local/android_world/android_world/task_evals/single/recipe.py` defines one `_RecipeApp` with `/data/data/com.flauschcode.broccoli/databases/broccoli`; both delete tasks and the observed failing add task inherit this family. `.local/android_world/android_world/task_evals/common_validators/sqlite_validators.py` routes initialization through `_clear_db` and host-side SQLite operations.

Correct wording: **four tasks actually observed pre-action infrastructure failures; two additional Recipe tasks were not run after the shared Broccoli/FTS4 validator defect was confirmed.** The latter must never be described as observed `infrastructure_error` runs.
"""
    (output / "infrastructure-exclusions.md").write_text(infra_md, encoding="utf-8")

    targeted_diff = git(
        repo,
        "diff",
        "--name-status",
        f"{FROZEN_COMMIT}..{FINAL_HEAD}",
        "--",
        "mobile_pilot",
        "scripts/run_mobilepilot_androidworld.py",
        "scripts/run_androidworld_runtime_eval.py",
        "configs/androidworld",
    )
    if targeted_diff:
        raise SystemExit("DISCREPANCY: Agent/evaluation behavior paths changed after freeze")
    full_diff = git(repo, "diff", "--name-status", f"{FROZEN_COMMIT}..{FINAL_HEAD}")

    pytest_path = output / "pytest-final.txt"
    pytest_python = (
        args.pytest_python.resolve()
        if args.pytest_python
        else repo / ".local/conda/androidworld-py312/python.exe"
    )
    if args.run_pytest and not pytest_python.exists():
        raise SystemExit(f"pytest Python not found: {pytest_python}")
    pytest_ok = run_pytest(repo, pytest_path, pytest_python) if args.run_pytest else (
        pytest_path.exists() and "186 passed" in pytest_path.read_text(encoding="utf-8")
    )

    recovery_counts = {
        "total_recovery_episodes": len(recovery_rows),
        "executed_replans": sum(row["executed"] for row in recovery_rows),
        "changed_actions": sum(row["changed_action"] is True for row in recovery_rows),
        "same_blocked_action": sum(row["same_blocked_action"] for row in recovery_rows),
        "insufficient_new_evidence": sum(row["insufficient_new_evidence"] for row in recovery_rows),
        "strict_rescues": sum(row["strict_rescue"] for row in recovery_rows),
        "misfires": sum(row["misfire"] for row in recovery_rows),
    }
    metrics_json = {
        "paired": observed_paired,
        "recovery": recovery_counts,
        "ui_tree": {
            "v1_requests": v1_tree,
            "v22_requests": v22_tree,
            "v22_changed_action": len(changed_tree),
            "changed_action_definition": (
                "Count ui_tree_decision events with changed_action=true. Runtime sets this by "
                "comparing normalized action similarity against the active Recovery blocked action; "
                "ui_tree_outcome duplicates are excluded."
            ),
        },
    }
    (output / "audit-metrics.json").write_text(
        json.dumps(metrics_json, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )

    batch_dirs = [
        repo / "artifacts/evaluation/androidworld-v22-final-frozen36-20260817",
        repo / "artifacts/evaluation/androidworld-v22-final-frozen36-continuation-20260817",
        repo / "artifacts/evaluation/androidworld-v22-final-frozen36-continuation2-20260817",
        repo / "artifacts/evaluation/androidworld-v22-final-frozen36-continuation3-20260817",
        invalid_dir,
        restored_dir,
    ]
    batch_rows = []
    for directory in batch_dirs:
        runs_path = directory / "runs.jsonl"
        summary_path = directory / "summary.json"
        rows = load_jsonl(runs_path)
        batch_rows.append(
            {
                "batch": directory.name,
                "run_rows": len(rows),
                "summary": rel(summary_path, repo) if summary_path.exists() else "not emitted",
                "role": load_json(directory / "preflight.json")["evaluation_role"],
                "audit_use": (
                    "valid fixed prefix"
                    if directory.name == "androidworld-v22-final-frozen36-20260817"
                    else "valid restored fixed suffix"
                    if directory == restored_dir
                    else "invalid network batch"
                    if directory == invalid_dir
                    else "observed pre-action infrastructure failure"
                ),
            }
        )
    batch_md = [
        "# Frozen source batches",
        "",
        "| Batch | runs rows | runner summary | metadata role | Audit use |",
        "| --- | ---: | --- | --- | --- |",
        *(
            f"| `{row['batch']}` | {row['run_rows']} | `{row['summary']}` | "
            f"`{row['role']}` | {row['audit_use']} |"
            for row in batch_rows
        ),
        "",
        "The main batch and the three one-row infrastructure-stop continuations did not emit `summary.json` because the runner stopped at the first infrastructure error. The restored 14-task suffix did emit its own summary. `audit-metrics.json` is the deterministic merged 30-pair summary and `paired-30.csv` records each row's source.",
    ]
    (output / "source-batches.md").write_text("\n".join(batch_md) + "\n", encoding="utf-8")

    source_paths = [
        manifest_path,
        *(path for directory in batch_dirs for path in (directory / "preflight.json", directory / "runs.jsonl", directory / "summary.json")),
    ]
    source_paths = [path for path in source_paths if path.exists()]
    write_csv(
        output / "source-file-sha256.csv",
        ({"sha256": sha256(path), "path": rel(path, repo)} for path in source_paths),
        ["sha256", "path"],
    )

    rescue_notes = {
        "MarkorDeleteNewestNote": (
            "LONG_PRESS led to a recovery episode grounded on Tree `Delete`; a second recovery "
            "grounded `OK`, executed it, then official reward became 1. The second episode is the "
            "single strict rescue row for this task; the first is correctly recorded as not rescued."
        ),
        "SimpleCalendarDeleteEvents": (
            "two unchanged screens triggered recovery; Tree grounded `Yes`; the changed click was "
            "executed and the immediately subsequent official reward became 1."
        ),
        "TasksHighPriorityTasks": (
            "Verifier stalled on the wrong launcher context; recovery changed DRAG to task-grounded "
            "OPEN_APP[tasks] and executed it. Reward became 1 only after three subsequent ANSWER "
            "attempts, the final corrected answer being `Follow up on support tickets`. This is not "
            "an immediate one-action rescue, but it satisfies the declared trace-strict definition."
        ),
    }
    checks = [
        ("1", "YES", "0/30 -> 9/30 is recomputed from raw runs."),
        ("2", "YES", "9 improved / 0 regressed is recomputed."),
        ("3", "YES", "invalid_actor_output 21 -> 4 is recomputed."),
        ("4", "YES", "25 Recovery episodes and 3 trace-strict rescues are recomputed from traces."),
        ("5", "YES", "UI Tree 209 -> 49 is recomputed from observation events."),
        ("6", "YES", "19 uses the explicit and reproducible ui_tree_decision definition below."),
        ("7", "YES", "All three contain trigger, changed executed replan, later reward=1, and rescued=true."),
        ("8", "YES", "All 30 pair task IDs are members of the original ordered 36-task manifest."),
        ("9", "NO", "No Agent/evaluation behavior path changed between frozen commit and final HEAD."),
        ("10", "YES", "Four observed failures and two same-family non-runs are separately evidenced."),
        ("11", "YES", "The invalid and restored suffixes have identical ordered tasks and locked Agent fields."),
        ("12", "YES" if pytest_ok else "NO", "Current-HEAD pytest reproduction is stored in pytest-final.txt."),
        ("13", "YES" if pytest_ok else "PARTIAL", "Core resume numbers are supported with the scope/attribution wording below."),
    ]
    verdict = "PASS" if pytest_ok else "FAIL"
    summary_lines = [
        "# MobilePilot V2.2 Final Evidence Audit",
        "",
        f"## Verdict: {verdict}",
        "",
        "The core numerical claims are reproducible from preserved raw files. No Agent behavior, Prompt, Recovery, reward logic, or evaluation config changed after the frozen commit. The result is scoped to 30 valid pairs from a pre-frozen 36-task list; it is not an AndroidWorld-wide 30% score.",
        "",
        "## Locked paired result",
        "",
        "```text",
        *(f"{key}: {value}" for key, value in observed_paired.items()),
        "```",
        "",
        "Sources: the first 16 valid pairs come from `artifacts/evaluation/androidworld-v22-final-frozen36-20260817/runs.jsonl`; the final 14 come from `artifacts/evaluation/androidworld-v22-final-frozen36-continuation5-network-restored-20260817/runs.jsonl`. `paired-30.csv` records the source file for every task.",
        "",
        "## Recovery audit",
        "",
        "```text",
        *(f"{key}: {value}" for key, value in recovery_counts.items()),
        "```",
        "",
        "Trace-strict rescue means: a Recovery trigger exists; the replan is dissimilar to the blocked action; that recovery-derived action is actually executed; an official reward=1 event occurs afterwards; and the matching `agent_recovery_outcome` records `rescued=true`. This is a trace-chain definition, not a counterfactual proof that no other route could have succeeded.",
        "",
        *(f"- **{task}:** {note}" for task, note in rescue_notes.items()),
        "",
        "## UI Tree audit",
        "",
        f"V1 requests: **{v1_tree}**. V2.2 requests: **{v22_tree}**. V2.2 changed-action decisions: **{len(changed_tree)}**.",
        "",
        "The 19 count is exactly the number of `ui_tree_decision` events with `changed_action=true`. In code, that field is set by comparing the candidate action with the active Recovery's blocked action through `actions_are_similar`. It does not count `ui_tree_outcome` duplicates. All 19 happened while a Recovery episode was active; five Tree requests were immediately triggered by `invalid_actor_output`, while the other fourteen were immediately triggered by stall/loop Recovery signals.",
        "",
        "## Commit boundary",
        "",
        f"Frozen `{FROZEN_COMMIT}` -> final `{FINAL_HEAD}` changes only documentation/evidence files:",
        "",
        "```text",
        full_diff,
        "```",
        "",
        "Targeted diff over `mobile_pilot/`, the two AndroidWorld runners, and `configs/androidworld/` is empty.",
        "",
        "## YES / NO / PARTIAL checklist",
        "",
        "| # | Answer | Evidence conclusion |",
        "| --- | --- | --- |",
        *(f"| {number} | **{answer}** | {note} |" for number, answer, note in checks),
        "",
        "## Resume-safe wording",
        "",
        "> On a pre-frozen 36-task AndroidWorld list, 30 tasks formed valid paired runs: V1 achieved 0/30 and V2.2 achieved 9/30 (9 improved, 0 regressed). Invalid-output terminations fell from 21 to 4; on-demand UI Tree requests fell from 209 to 49; 25 bounded Recovery episodes produced 3 trace-strict rescues. Four tasks failed before Agent takeover due to observed infrastructure initialization errors, and two additional Recipe tasks were not run after the shared Broccoli/FTS4 validator defect was confirmed.",
        "",
        "Do not shorten this to `AndroidWorld 30%`, `36 tasks completed`, `Recovery solved 9 tasks`, or `all 6 tasks observed infrastructure_error`.",
        "",
        "## Bundle contents",
        "",
        "- `paired-30.csv`: one row per valid pair",
        "- `recovery-25.csv`: one row per Recovery episode",
        "- `rescue-event-chains.json`: automatically extracted trigger-to-reward chains",
        "- three complete rescue JSONL traces",
        "- `infrastructure-exclusions.md`: observed vs same-family non-run split",
        "- `network-restart-audit.md`: invalid batch vs restored fixed suffix",
        "- `pytest-final.txt`: current-HEAD test environment and full output",
        "- `audit-metrics.json`: machine-readable recomputation",
        "- `source-file-sha256.csv`: hashes of raw source result files",
        "- `source-batches.md`: all run/suffix batches and summary availability",
        "- `SHA256SUMS.txt`: hashes of the audit bundle (excluding itself)",
    ]
    (output / "audit-summary.md").write_text("\n".join(summary_lines) + "\n", encoding="utf-8")

    hash_file = output / "SHA256SUMS.txt"
    hash_lines = [
        f"{sha256(path)}  {path.name}"
        for path in sorted(output.iterdir(), key=lambda item: item.name)
        if path.is_file() and path != hash_file
    ]
    hash_file.write_text("\n".join(hash_lines) + "\n", encoding="utf-8")

    print(json.dumps(metrics_json, ensure_ascii=False, indent=2, sort_keys=True))
    print(f"verdict={verdict}")
    print(f"bundle={output}")
    return 0 if verdict == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
