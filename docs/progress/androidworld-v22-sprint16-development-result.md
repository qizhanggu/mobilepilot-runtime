# AndroidWorld Sprint 16：V2.2 开发回归与负结果审计

日期：2026-08-10

状态：**V2.2 最佳开发回归 7/20，出现 1 次真实 Recovery 救回；仍低于 V2 的 9/20。后续 Manager 边界消融回落到 5/20+1 partial，已回退代码并保留产物。**

## 本轮问题与假设

Action-only 冒烟证明 GUI Plus 能稳定输出动作，但第一轮 20 题开发回归暴露了两个 Runtime 问题：

1. AndroidWorld 组合任务的 `reward=0.5` 被旧 Runner 当作完整成功，导致 Agent 提前结束；
2. Subgoal Manager 会猜测未来 App 的 package，并把猜测当成硬证据。App 实际打开后，VLM 虽能看出完成，Runtime 仍因硬证据不匹配而长期冻结旧子目标。

本轮最小假设是：严格区分 full/partial reward，并禁止无来源 package 硬证据，可以让 Agent 正确推进剩余目标，而不改变 GUI Actor 模型或视觉方案。

## 代码改动

- official reward 统一分为 `success`（`>=1.0`）、`partial`（`0<reward<1.0`）和 `failure`；
- partial 不终止 Agent、不计 Recovery 救回，也不进入完整成功率；
- Subgoal Manager 猜出的 package 若无法由 Runtime 当前 package 信号支撑，自动降级为 `visual_state`，交给事件触发 Verifier 判断；
- 原始 package、截图 SHA-256、视觉相似度、UI 文本和 Trace 均保留，不用软判断覆盖硬证据；
- 历史 Runner 同步修正 partial 状态，避免后续复跑再次混淆口径；
- 全仓库 `170 passed`。

## 三组开发证据

所有任务都来自已暴露的原 20 题，只能用于开发与回归。

| 版本 / 产物 | 完整成功 | 部分完成 | 环境错误 | 结论 |
| --- | ---: | ---: | ---: | --- |
| V2.2 初始 action-only（拆分批次） | 5/20 | 1/20 | 1/20 | 非法终止显著减少，但任务能力未提升；旧 summary 曾误把 partial 算成功 |
| V2.2 reward+evidence 修复 | 7/20 | 0 | 0 | 当前最佳开发回归；1 次真实 Recovery 救回 |
| 操作型 subgoal 严格拒绝消融 | 5/20 | 1/20 | 0 | 调用、循环和 Recovery 增加，完整成功下降；不合入主线 |

当前主结果产物：

```text
artifacts/evaluation/androidworld-v22-action-only-development-20260810/
  regression-20-step12-fix2-reward-and-evidence/
```

边界消融负结果：

```text
artifacts/evaluation/androidworld-v22-action-only-development-20260810/
  regression-20-step12-fix3-manager-boundary/
```

## 当前最佳 V2.2 指标

| 指标 | 数值 |
| --- | ---: |
| 完整成功率 | 7/20（35%） |
| 部分完成 | 0 |
| 非法输出终止 | 1/20 |
| 步数耗尽 | 4/20 |
| Recovery 触发 / 救回 / 误触发 | 20 / 1 / 0 |
| 循环检测 | 16 |
| 平均执行动作 | 6.15 |
| Subgoal Manager 调用 / 失败 | 50 / 15 |
| Progress Verifier 调用 | 26 |
| VLM 总调用 | 217 |
| Token | 828,938 |
| 模型延迟合计 | 710.79 s |
| 估算目录价 | ¥0.8654 |

失败 taxonomy：5 次 `recovery_exhausted`、4 次 `step_budget_exhausted`、3 次 `unsafe_repeated_action_after_recovery`、1 次 `invalid_actor_output`。

## 真实 Recovery 救回

`ExpenseDeleteSingle` 的 Trace 满足严格救回定义：

1. 两次点击后页面视觉近似，触发 `two_consecutive_unchanged_screens`；
2. Runtime 请求一次 UI Tree，Tree 显示 `Expense Detail`、`Taxi Fare` 和 `btn_delete`；
3. Actor 将动作从原点击区域改为新的删除控件位置，`changed_action=true`；
4. 后续确认动作后 AndroidWorld 返回 `official_reward=1.0`；
5. `agent_recovery_outcome.rescued=true`，且 Recovery 动作确实执行过。

Trace：

```text
artifacts/evaluation/androidworld-v22-action-only-development-20260810/
  regression-20-step12-fix2-reward-and-evidence/traces/
  ExpenseDeleteSingle--v2.2--hybrid.jsonl
```

这条证据可以描述为“按需 Tree 支撑动作级 Recovery 的真实救回”，不能扩大为“Recovery 普遍有效”：20 次触发只救回 1 次。

## 组合任务口径修复

`TurnOnWifiAndOpenApp` 在旧 Runner 中打开 Wi-Fi 后得到 `0.5` 就提前结束。修复后同一开发任务继续执行第二个条件，最终得到 `1.0`。这证明口径修复改变了 Agent 控制流，不只是改报表。

## 为什么不保留更严格的 Manager 边界

实验版拒绝 `click / swipe / open app drawer` 等操作型 subgoal，并尝试把 Verifier 失败说明传给第二级 Recovery。架构意图合理，但真实结果为：

- 完整成功从 7 降到 5，另有 1 个 partial；
- Recovery 从 20 次增至 27 次，误触发从 0 增至 1；
- VLM 调用从 217 增至 274，估算成本从 ¥0.8654 增至 ¥1.1257；
- 多数任务只是更晚终止，没有转化为官方成功。

因此代码回退到前一开发快照，负结果和 Trace 保留。该结论说明“边界更严格”不自动等于“Agent 更强”。

## 最终判断

- V2.2 相比早期版本，Actor 输出可靠性、子目标审计、partial reward 处理和真实 Recovery 证据都更完整；
- V2.2 最佳 7/20 仍低于 V2 的 9/20，不能作为成功率升级；
- Markor、日历和剪贴板短信的主要问题已从协议失败转为页面理解、子目标质量和 Recovery 纠偏不足；
- 原 20 题不再继续调规则。下一步必须冻结全新任务，做 V1/V2/V2.2 的公平配对或消融，不能用最佳开发轮次证明泛化。
