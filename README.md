# MobilePilot

**Auditable Android GUI Agent Runtime**

An auditable runtime for multi-step Android GUI agents: structured actions, progress verification, on-demand UI Tree, bounded recovery, and frozen AndroidWorld evaluation.

面向 Android 多步 GUI Agent 的可审计执行框架：状态维护、进展验证、按需 UI Tree、有限 Recovery 与冻结评测。

`Python` · `AndroidWorld` · `ADB` · `Android Emulator` · `uiautomator2` · `Accessibility UI Tree` · `OpenAI-compatible VLM API` · `JSONL Trace` · `pytest`

[Architecture](#architecture) · [Frozen results](#frozen-evaluation) · [Recovery trace](#a-real-recovery-story) · [Root Cause Analysis](docs/final/v22-root-cause-analysis.md) · [Code map](#code-map) · [Full audit](docs/final/audit/audit-summary.md)

![MobilePilot frozen paired evaluation: V1 0/30 to V2.2 9/30, invalid-output exits 21 to 4, UI Tree requests 209 to 49, and 3 strict recovery rescues](docs/assets/frozen-results.svg)

> **Evidence scope:** the 30 valid pairs come from a pre-frozen 36-task list. This is **not** an “AndroidWorld accuracy: 30%” claim. Four tasks had observed pre-action infrastructure failures; two Recipe tasks were not run after the shared Broccoli/FTS4 validator defect was confirmed.

> **Experiment freeze:** [`mobilepilot-v2.2-final`](https://github.com/qizhanggu/mobilepilot-runtime/tree/mobilepilot-v2.2-final). Current showcase work only changes presentation and documentation on top of the frozen implementation.

## Start here

| If you have… | Read this |
| --- | --- |
| 2 minutes | [Problem](#problem) → [Architecture](#architecture) → [Frozen evaluation](#frozen-evaluation) |
| 5 minutes | [Markor Recovery case](#a-real-recovery-story) and its [raw JSONL Trace](docs/final/audit/MarkorDeleteNewestNote--v2.2--hybrid.jsonl) |
| 10 minutes | [Root Cause Analysis](docs/final/v22-root-cause-analysis.md), [negative results](#what-did-not-work), and [code map](#code-map) |
| Full audit | [Audit summary](docs/final/audit/audit-summary.md), [paired-30.csv](docs/final/audit/paired-30.csv), and [recovery-25.csv](docs/final/audit/recovery-25.csv) |

## Problem

A GUI Agent is not just “look at a screenshot and click.” In a real multi-step run:

- the model can emit malformed or unsupported actions;
- the execution layer may lack the action the task requires;
- a changed screen does not necessarily mean useful progress;
- the Agent can repeat actions or loop between pages;
- the model can claim completion before the environment agrees;
- “Recovery” can degrade into asking the same model to guess again.

MobilePilot wraps an imperfect GUI model in a small, explicit control loop. The Runtime owns state, validation, tool timing, recovery budget, official success, and Trace evidence. The model proposes the next action; it does not get to rewrite history or grade itself.

## Architecture

![MobilePilot Runtime architecture from goal and observation through Actor, Protocol Guard, Action Contract, Android execution, verification, bounded recovery, on-demand UI Tree, official reward, and JSONL Trace](docs/assets/architecture.svg)

| Module | Responsibility |
| --- | --- |
| **GUI Actor** | Reads the current screenshot and proposes one structured next action. |
| **Protocol Guard** | Normalizes unambiguous aliases, validates schema, and allows one safe retry only before any action executes. |
| **Action Contract** | Defines Click, Type, Long Press, Drag, Answer, Back, Open App, and other executable capabilities. |
| **Runtime State** | Freezes the active subgoal, progress evidence, blocker, recent actions, loop signals, and recovery budget. |
| **Progress Verifier** | Runs deterministic checks every step and calls a VLM only when semantic evidence is needed. |
| **On-demand UI Tree** | Supplies structural evidence after protocol failure, execution failure, stall, loop, or uncertainty—not every step. |
| **Bounded Recovery** | Tries at most action-level then subgoal-level correction; without new evidence, it stops. |
| **Official Reward + Trace** | AndroidWorld reward is the only final success signal; every decision and outcome is written to JSONL. |

Three completion-evidence types keep verification understandable:

- `package_activity`: the expected App/page context is active;
- `ui_text`: normalized target text exists in the UI Tree;
- `visual_state`: deterministic evidence is insufficient, so a VLM compares before/after screenshots.

## What changed

![MobilePilot project journey from V1 through V2, the negative V2.1 planner result, V2.2, Trace RCA, and frozen evaluation](docs/assets/project-journey.svg)

The decisive improvement was not a bigger Planner. It was clearer ownership:

1. keep the Actor close to its training shape—screenshot in, one GUI action out;
2. move subgoal lifecycle, completion evidence, loop state, and budget into the Runtime;
3. separate protocol repair from post-action Agent Recovery;
4. use UI Tree and semantic verification only after explicit trigger events;
5. require AndroidWorld official reward before declaring success.

The V2.1 Planner/Checklist experiment scored `5/20` on the exposed development set, below V2's `9/20`. That negative result changed the implementation direction instead of being hidden.

## A real Recovery story

`MarkorDeleteNewestNote` is the clearest frozen example of failure signal → new evidence → changed action → official success.

![Trace-derived Markor recovery chain: LONG_PRESS, repeated page, UI Tree finds Delete, second Recovery finds OK, official reward becomes one](docs/assets/recovery-case-study.svg)

The Trace records two Recovery episodes:

- Recovery #1 changes `LONG_PRESS` to the Tree-grounded `Delete` action, but is correctly recorded as **not yet rescued**;
- the confirmation dialog stalls again, Recovery #2 finds `OK`, executes a different click, and the subsequent official reward becomes `1` with `rescued=true`.

The case-study diagram is reconstructed from frozen Trace events. The run did not save Delete/OK screenshots, so no synthetic phone screenshots were created.

**Drill into the evidence:** [complete JSONL Trace](docs/final/audit/MarkorDeleteNewestNote--v2.2--hybrid.jsonl) · [automatically extracted rescue chain](docs/final/audit/rescue-event-chains.json) · [all 25 Recovery episodes](docs/final/audit/recovery-25.csv)

## Frozen evaluation

The final list was frozen before result inspection. V1 and V2.2 used the same `gui-plus-2026-02-26` Actor model, seed `0`, hybrid mode, and 16-action budget.

| Metric | V1 | V2.2 |
| --- | ---: | ---: |
| Official full success | 0/30 | **9/30** |
| Paired improved / regressed | — | **9 / 0** |
| Invalid-output termination | 21 | **4** |
| UI Tree requests | 209 | **49** |
| Recovery trigger / strict rescue | 0 / 0 | **25 / 3** |
| Average executed actions | 6.03 | 7.13 |
| VLM calls | 209 | 386 |
| Estimated list cost | ¥1.4425 | ¥1.6521 |

What the result supports:

- V2.2 completed nine tasks that V1 did not on the 30 valid fixed pairs;
- mechanical invalid-output deaths fell substantially;
- on-demand Tree used fewer calls than the every-step V1 strategy;
- three tasks contain trace-strict Recovery-to-reward chains.

What it does **not** support:

- AndroidWorld-wide 30% accuracy;
- claiming all 36 tasks formed valid pairs;
- attributing all nine successes to Recovery;
- treating Action Contract compatibility as general reasoning improvement.

See the [frozen evaluation report](docs/final/frozen-evaluation-report.md) and [final evidence audit](docs/final/audit/audit-summary.md) for the 4 observed infrastructure failures, 2 same-family exclusions, network restart audit, commit boundary, and source hashes.

## Evidence trail

| Question | Evidence |
| --- | --- |
| Can the headline result be recomputed? | [paired-30.csv](docs/final/audit/paired-30.csv) · [audit metrics](docs/final/audit/audit-metrics.json) |
| Did Recovery really execute a different action? | [recovery-25.csv](docs/final/audit/recovery-25.csv) · [representative Trace analysis](docs/final/representative-traces.md) · [3 raw rescue traces](docs/README.md#final-evidence) |
| Why were six tasks outside the denominator? | [infrastructure exclusions](docs/final/audit/infrastructure-exclusions.md) |
| Was the network-restored suffix the same fixed suffix? | [network restart audit](docs/final/audit/network-restart-audit.md) |
| Did code change after the freeze? | [audit summary](docs/final/audit/audit-summary.md#commit-boundary) |
| Why did V2.2 still fail 21 tasks? | [20-task Trace RCA](docs/final/v22-root-cause-analysis.md) · [representative traces](docs/final/representative-traces.md) |
| Are the local tests reproducible? | [pytest evidence: 186 passed](docs/final/audit/pytest-final.txt) |

## What did not work

| Attempt | Result | Decision |
| --- | --- | --- |
| Frozen 10×10 grid | ScreenSpot-v2 Raw `332/471`; Grid `314/471` | Helped a controlled App, but hurt public generalization. Stop tuning coordinates. |
| Every-step UI Tree | AndroidWorld V1 hybrid `4/20`, below vision-only `5/20` | Tree supplies structure, not task planning. Convert it to an event-triggered tool. |
| Planner Checklist | Development `5/20`, below V2 `9/20` | More frozen plan state amplified bad assumptions. Fix state and evidence first. |

> More modules did not automatically mean a stronger agent.

## Quick start

```bash
pip install -r requirements.txt
pytest -q
```

Live AndroidWorld evaluation additionally requires an Android Emulator, the pinned AndroidWorld environment, and model API credentials. The formal commands and safety boundaries live in the [Demo and reproduction guide](docs/final/demo-script.md); the frozen benchmark should not be rerun for showcase purposes.

## Code map

```text
mobile_pilot/androidworld/
  actor.py              GUI Actor + structured action protocol
  agent.py              runtime loop, verification, Tree timing, Recovery
  runtime_state.py      subgoal state, loop signals, recovery budget
  subgoal_manager.py    frozen subgoal + completion postcondition
  progress_verifier.py  event-triggered semantic verifier
  adapter.py            AndroidWorld action and ANSWER adapter

mobile_pilot/core/
  models.py             shared Action Contract

scripts/
  run_androidworld_runtime_eval.py   paired evaluation runner
  audit_mobilepilot_v22_final.py     deterministic final evidence audit
```

The root-level `agent.py`, `agent_base.py`, and `test_runner.py` are **legacy competition compatibility entrypoints** retained for regression tests. The final MobilePilot runtime lives under [`mobile_pilot/`](mobile_pilot/).

## Current limits

- 21/30 valid frozen pairs still failed; complex forms, cross-App tasks, and map interaction remain hard.
- 25 Recovery episodes produced only 3 strict rescues; detecting trouble is easier than finding a correct alternative.
- V2.2 traded more VLM calls, tokens, and latency for fewer early protocol failures.
- Subgoal postcondition generation remains unreliable on some tasks.
- Estimated list cost is computed from recorded tokens, not billing statements.

## Documentation

The curated entrypoint is [`docs/README.md`](docs/README.md). It separates final evidence and current design from development history and archived competition material.

## License

MIT. Third-party models, datasets, Android Apps, and benchmarks remain under their respective licenses. See [NOTICE.md](NOTICE.md).
