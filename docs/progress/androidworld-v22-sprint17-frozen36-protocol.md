# AndroidWorld Sprint 17：36 题 V1/V2.2 冻结评测协议

日期：2026-08-10

状态：**任务清单与协议已冻结，尚未初始化任何任务、调用模型或查看结果。**

## 为什么从 12 题扩大到 36 题

先前 6 对有效新任务和原 20 题的多轮开发回归都表明，小样本与单轮模型随机性会显著影响总分。12 题中每题约占 8.3 个百分点，不足以支撑稳定比较。新协议扩大到 36 个从未运行的任务，每题约占 2.8 个百分点，同时仍能在单台 AndroidWorld 模拟器和 ¥15 预算内完成。

## 冻结内容

| 项目 | 冻结值 |
| --- | --- |
| Manifest | `configs/androidworld/runtime_eval_36_v22.json` |
| AndroidWorld commit | `3e50888527ef9f29b9157ecd537e408008bb1c85` |
| 对照版本 | `v1` vs `v2.2` |
| GUI Actor | `gui-plus-2026-02-26` |
| V2.2 Manager / Verifier | `qwen3.7-flash-2026-07-15` |
| seed | 0 |
| mode | hybrid |
| 每题动作上限 | 16 |
| 任务数 / 配对运行数 | 36 / 72 |
| 任务 hash | `cc408d7185991b356d60531c33ca2ca1c5681aa13e62eeeae03c70983437e8b2` |
| Agent 源码 hash | `8bf7aa4260fa49eea83738dfe368248fe082c4d1282c495cacea9fbf360fe110` |
| 最大逻辑调用 | 2600 |
| 成本硬上限 | ¥15 |

## 任务选择规则

- 排除所有旧 AndroidWorld manifest 和任意 `runs.jsonl` 中出现过的 51 个任务；
- 排除已知因 SQLite `fts4` 导致初始化失败的 Joplin/Notes 任务族；
- 只根据任务名称和操作面覆盖选择，不查看结果；
- 覆盖 Browser、Expense、Files、Markor、OSM、Recipe、Calendar、SportsTracker、System 和 Tasks；
- 不因某题困难、失败或基础设施不兼容而替换任务；
- 任一任务开始后禁止单题重试，基础设施错误单独记录并暂停。

## 成功口径

- `official_reward >= 1.0`：完整成功；
- `0 < official_reward < 1.0`：部分完成，单独统计，不算成功；
- `official_reward <= 0`：失败；
- 模型自报完成只是提议，不改变官方标签。

## 必须输出的指标

- 完整成功率与 partial 数；
- 非法输出、步数耗尽、循环与每类失败原因；
- Recovery 触发、救回、误触发；
- 平均动作数；
- Subgoal Manager、Progress Verifier 与全部 VLM 调用；
- Token、延迟、估算目录价；
- 逐题 V1/V2.2 配对结果。

## 预期资源

根据已完成开发回归，72 次配对运行预计需要约 2～3 小时；目录价预计为数元，Runner 仍以 ¥15 为硬停止线。运行期间只允许 `emulator-5554`，不操作真实手机或 VMware。

## 解释边界

这 36 题在第一次运行前可以称为新冻结评测集。开始观察结果后，它们只能用于一次性配对结论；不得继续据此调 Prompt、Recovery 或子目标策略后再称 held-out。
