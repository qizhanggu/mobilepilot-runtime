# Network suffix restart audit

## Verdict

**YES.** The preserved invalid batch and network-restored batch contain the same ordered 14-task × 2-variant suffix. All locked Agent fields match; only `created_at` differs in preflight metadata.

| Check | Invalid batch | Restored batch | Same |
| --- | --- | --- | --- |
| runs | 28 | 28 | YES |
| task/variant order | fixed 28 rows | fixed 28 rows | YES |
| Agent commit | `487f2abe7382d11a5cc15572c4902265547d42dd` | `487f2abe7382d11a5cc15572c4902265547d42dd` | YES |
| source hash | `246cce8ea4a7c7edac304cac267f41e9fe59945e6de3332c284db2fe650e74cb` | `246cce8ea4a7c7edac304cac267f41e9fe59945e6de3332c284db2fe650e74cb` | YES |
| model | `gui-plus-2026-02-26` | `gui-plus-2026-02-26` | YES |
| seed / max steps | 0 / 16 | 0 / 16 | YES |

All 28 invalid rows have `executed_action_count=0`, `total_tokens=0`, and estimated cost 0. Their traces show attempted model calls failing with `Connection error`, empty `raw_response`, and no executed phone action. They are therefore an invalid run-infrastructure batch, not 28 Agent failures.

The restored directory reruns the complete fixed suffix in the same order. It does not select tasks by success/failure and does not change Prompt, Runtime, model, seed, step budget, source hash, or commit.

Sources:

- `artifacts/evaluation/androidworld-v22-final-frozen36-continuation4-20260817/preflight.json`
- `artifacts/evaluation/androidworld-v22-final-frozen36-continuation4-20260817/runs.jsonl`
- `artifacts/evaluation/androidworld-v22-final-frozen36-continuation5-network-restored-20260817/preflight.json`
- `artifacts/evaluation/androidworld-v22-final-frozen36-continuation5-network-restored-20260817/runs.jsonl`
