# MobilePilot V2.2 Final Evidence Audit

## Verdict: PASS

The core numerical claims are reproducible from preserved raw files. No Agent behavior, Prompt, Recovery, reward logic, or evaluation config changed after the frozen commit. The result is scoped to 30 valid pairs from a pre-frozen 36-task list; it is not an AndroidWorld-wide 30% score.

## Locked paired result

```text
valid_pairs: 30
v1_success: 0
v22_success: 9
improved: 9
regressed: 0
both_success: 0
both_failed: 21
v1_invalid_output: 21
v22_invalid_output: 4
```

Sources: the first 16 valid pairs come from `artifacts/evaluation/androidworld-v22-final-frozen36-20260817/runs.jsonl`; the final 14 come from `artifacts/evaluation/androidworld-v22-final-frozen36-continuation5-network-restored-20260817/runs.jsonl`. `paired-30.csv` records the source file for every task.

## Recovery audit

```text
total_recovery_episodes: 25
executed_replans: 12
changed_actions: 15
same_blocked_action: 8
insufficient_new_evidence: 11
strict_rescues: 3
misfires: 0
```

Trace-strict rescue means: a Recovery trigger exists; the replan is dissimilar to the blocked action; that recovery-derived action is actually executed; an official reward=1 event occurs afterwards; and the matching `agent_recovery_outcome` records `rescued=true`. This is a trace-chain definition, not a counterfactual proof that no other route could have succeeded.

- **MarkorDeleteNewestNote:** LONG_PRESS led to a recovery episode grounded on Tree `Delete`; a second recovery grounded `OK`, executed it, then official reward became 1. The second episode is the single strict rescue row for this task; the first is correctly recorded as not rescued.
- **SimpleCalendarDeleteEvents:** two unchanged screens triggered recovery; Tree grounded `Yes`; the changed click was executed and the immediately subsequent official reward became 1.
- **TasksHighPriorityTasks:** Verifier stalled on the wrong launcher context; recovery changed DRAG to task-grounded OPEN_APP[tasks] and executed it. Reward became 1 only after three subsequent ANSWER attempts, the final corrected answer being `Follow up on support tickets`. This is not an immediate one-action rescue, but it satisfies the declared trace-strict definition.

## UI Tree audit

V1 requests: **209**. V2.2 requests: **49**. V2.2 changed-action decisions: **19**.

The 19 count is exactly the number of `ui_tree_decision` events with `changed_action=true`. In code, that field is set by comparing the candidate action with the active Recovery's blocked action through `actions_are_similar`. It does not count `ui_tree_outcome` duplicates. All 19 happened while a Recovery episode was active; five Tree requests were immediately triggered by `invalid_actor_output`, while the other fourteen were immediately triggered by stall/loop Recovery signals.

## Commit boundary

Frozen `487f2abe7382d11a5cc15572c4902265547d42dd` -> final `9b643077e7ce999589f44413403513bf2ce67a09` changes only documentation/evidence files:

```text
M	README.md
M	docs/README.md
M	docs/final/demo-script.md
M	docs/final/evaluation-summary.md
A	docs/final/frozen-evaluation-report.md
M	docs/final/interview-handbook.md
M	docs/final/representative-traces.md
M	docs/final/resume-candidates.md
M	docs/final/v22-root-cause-analysis.md
M	docs/progress/androidworld-v22-final-directed-fixes.md
```

Targeted diff over `mobile_pilot/`, the two AndroidWorld runners, and `configs/androidworld/` is empty.

## YES / NO / PARTIAL checklist

| # | Answer | Evidence conclusion |
| --- | --- | --- |
| 1 | **YES** | 0/30 -> 9/30 is recomputed from raw runs. |
| 2 | **YES** | 9 improved / 0 regressed is recomputed. |
| 3 | **YES** | invalid_actor_output 21 -> 4 is recomputed. |
| 4 | **YES** | 25 Recovery episodes and 3 trace-strict rescues are recomputed from traces. |
| 5 | **YES** | UI Tree 209 -> 49 is recomputed from observation events. |
| 6 | **YES** | 19 uses the explicit and reproducible ui_tree_decision definition below. |
| 7 | **YES** | All three contain trigger, changed executed replan, later reward=1, and rescued=true. |
| 8 | **YES** | All 30 pair task IDs are members of the original ordered 36-task manifest. |
| 9 | **NO** | No Agent/evaluation behavior path changed between frozen commit and final HEAD. |
| 10 | **YES** | Four observed failures and two same-family non-runs are separately evidenced. |
| 11 | **YES** | The invalid and restored suffixes have identical ordered tasks and locked Agent fields. |
| 12 | **YES** | Current-HEAD pytest reproduction is stored in pytest-final.txt. |
| 13 | **YES** | Core resume numbers are supported with the scope/attribution wording below. |

## Resume-safe wording

> On a pre-frozen 36-task AndroidWorld list, 30 tasks formed valid paired runs: V1 achieved 0/30 and V2.2 achieved 9/30 (9 improved, 0 regressed). Invalid-output terminations fell from 21 to 4; on-demand UI Tree requests fell from 209 to 49; 25 bounded Recovery episodes produced 3 trace-strict rescues. Four tasks failed before Agent takeover due to observed infrastructure initialization errors, and two additional Recipe tasks were not run after the shared Broccoli/FTS4 validator defect was confirmed.

Do not shorten this to `AndroidWorld 30%`, `36 tasks completed`, `Recovery solved 9 tasks`, or `all 6 tasks observed infrastructure_error`.

## Bundle contents

- `paired-30.csv`: one row per valid pair
- `recovery-25.csv`: one row per Recovery episode
- `rescue-event-chains.json`: automatically extracted trigger-to-reward chains
- three complete rescue JSONL traces
- `infrastructure-exclusions.md`: observed vs same-family non-run split
- `network-restart-audit.md`: invalid batch vs restored fixed suffix
- `pytest-final.txt`: current-HEAD test environment and full output
- `audit-metrics.json`: machine-readable recomputation
- `source-file-sha256.csv`: hashes of raw source result files
- `source-batches.md`: all run/suffix batches and summary availability
- `SHA256SUMS.txt`: hashes of the audit bundle (excluding itself)
