# Frozen source batches

| Batch | runs rows | runner summary | metadata role | Audit use |
| --- | ---: | --- | --- | --- |
| `androidworld-v22-final-frozen36-20260817` | 33 | `not emitted` | `frozen_evaluation` | valid fixed prefix |
| `androidworld-v22-final-frozen36-continuation-20260817` | 1 | `not emitted` | `development` | observed pre-action infrastructure failure |
| `androidworld-v22-final-frozen36-continuation2-20260817` | 1 | `not emitted` | `development` | observed pre-action infrastructure failure |
| `androidworld-v22-final-frozen36-continuation3-20260817` | 1 | `not emitted` | `development` | observed pre-action infrastructure failure |
| `androidworld-v22-final-frozen36-continuation4-20260817` | 28 | `artifacts/evaluation/androidworld-v22-final-frozen36-continuation4-20260817/summary.json` | `development` | invalid network batch |
| `androidworld-v22-final-frozen36-continuation5-network-restored-20260817` | 28 | `artifacts/evaluation/androidworld-v22-final-frozen36-continuation5-network-restored-20260817/summary.json` | `development` | valid restored fixed suffix |

The main batch and the three one-row infrastructure-stop continuations did not emit `summary.json` because the runner stopped at the first infrastructure error. The restored 14-task suffix did emit its own summary. `audit-metrics.json` is the deterministic merged 30-pair summary and `paired-30.csv` records each row's source.
