# MobilePilot 实验结果总表

> 最后更新：2026-08-17。成功统一指 AndroidWorld `official_reward >= 1.0`；partial 不算完整成功。

## 1. 一页总览

| 实验 | 规模 | 结果 | 结论边界 |
| --- | ---: | --- | --- |
| MobilePilot Lab | 8 任务 × 7 配置 × 3 次 = 168 runs | 冻结 10×10 Grid 24/24 | 自建受控 App，不代表公开泛化 |
| ScreenSpot-v2 Mobile | 471 条 | Raw 332/471（70.49%）；Grid 314/471（66.67%） | 网格未带来公开泛化收益 |
| AndroidWorld V1 历史 | 20 题 × vision/hybrid = 40 runs | vision 5/20；hybrid 4/20 | 已暴露，现为开发基线 |
| AndroidWorld V2 开发回归 | 同一暴露 20 题 | 4/20 → 9/20 | 定向开发收益，不是 held-out |
| AndroidWorld V2.1 Planner 消融 | 同一暴露 20 题 | 5/20 | Planner 没有带来收益 |
| AndroidWorld V2.2 RCA 前 | 同一暴露 20 题 | 7/20 | 分层职责更清楚，但未超过 V2 |
| AndroidWorld V2.2 最终开发回归 | 同一暴露 20 题 | 9/20 | 补动作契约与状态顺序后追平 V2 |
| AndroidWorld 最终冻结清单 | 36 题中 30 个有效配对 | V1 0/30；V2.2 9/30 | 固定未见任务有效子集；6 题基础设施无效/排除 |

## 2. V1 失败审计

历史固定 20 题的两个模式共 40 条运行：9 条成功、31 条失败。

| 表层终止 | 次数 |
| --- | ---: |
| invalid_actor_output | 21 |
| step_budget_exhausted | 7 |
| 模型误报完成 | 2 |
| action_execution_failed | 1 |

后续逐 Trace RCA 表明，表层终止不是根因。更早的问题包括 Actor 页面/动作判断错误、Action Contract 缺口、坏 completion evidence、旧状态污染和 Recovery 没有新证据。

## 3. 暴露 20 题开发结果

### V2 相对 V1

固定同一模型、seed、12 步和 hybrid：

| 指标 | V1 | V2 |
| --- | ---: | ---: |
| 官方成功 | 4/20 | 9/20 |
| 非法输出终止 | 13 | 7 |
| 步数耗尽 | 2 | 1 |
| 平均动作 | 4.05 | 5.60 |
| VLM 调用 | 94 | 144 |
| 估算目录价 | ¥0.6596 | ¥0.7969 |

配对：6 改善、1 退化、3 双方成功、10 双方失败。该结果驱动了后续 RCA，因此只属于 development/regression evidence。

### V2.1 Planner 消融

结构化 Checklist、检查点和两级 Recovery 的开发结果为 5/20，低于 V2 的 9/20。结论不是“Planner 永远无用”，而是当前 Actor、evidence 和验证基础不足时，额外计划状态会放大错误约束。

### V2.2 最终开发回归

最终 V2.2 固定 12 步：

| 指标 | 数值 |
| --- | ---: |
| 官方成功 | 9/20（45%） |
| partial | 0 |
| 非法输出终止 | 0 |
| step_budget_exhausted | 6 |
| Recovery 触发 / 严格救回 | 14 / 1 |
| 循环检测 | 8 |
| 平均动作 | 6.85 |
| Manager 调用 / failure | 62 / 32 |
| Progress Verifier 调用 | 23 |
| UI Tree 请求 | 25 |
| VLM 调用 | 241 |
| Token | 947,909 |
| 模型延迟 | 1,303.72 s |
| 估算目录价 | ¥1.0106 |

单题 20-step diagnostic：`SimpleCalendarAddRepeatingEvent` 仍失败，执行 20 个动作，未触发 loop/recovery。该结果否定“它只是 12 步不够”的简单解释，不进入成功率。

## 4. 最终冻结配对

### 协议

- 原始清单：36 个未用于上述开发/RCA 的任务；
- Actor：`gui-plus-2026-02-26`；
- Manager/Verifier：`qwen3.7-flash-2026-07-15`；
- AndroidWorld：`3e50888527ef9f29b9157ecd537e408008bb1c85`；
- seed 0、hybrid、16 actions；
- 冻结 commit：`487f2abe7382d11a5cc15572c4902265547d42dd`；
- source hash：`246cce8ea4a7c7edac304cac267f41e9fe59945e6de3332c284db2fe650e74cb`。

### 有效 30 对结果

| 指标 | V1 | V2.2 | 变化 |
| --- | ---: | ---: | ---: |
| 官方成功 | 0/30 | 9/30 | +9 题 |
| partial | 0 | 0 | 0 |
| 非法输出终止 | 21 | 4 | -17 |
| 步数耗尽终止 | 4 | 5 | +1 |
| 执行动作 | 181 | 214 | +33 |
| 平均动作 | 6.03 | 7.13 | +1.10 |
| 循环检测 | 0 | 17 | +17（V1 无此模块） |
| Recovery 触发 / 救回 | 0 / 0 | 25 / 3 | — |
| Manager 调用 / failure | 0 / 0 | 90 / 38 | — |
| Progress Verifier 调用 | 0 | 37 | +37 |
| UI Tree 请求 | 209 | 49 | -160 |
| Tree 改变动作 | 0 | 19 | +19 |
| VLM 调用 | 209 | 386 | +177 |
| Token | 916,115 | 1,507,742 | +591,627 |
| 模型延迟 | 1,304.77 s | 2,226.09 s | +921.32 s |
| 估算目录价 | ¥1.4425 | ¥1.6521 | +¥0.2097 |

配对结果：9 improved、0 regressed、0 both success、21 both fail。

V2.2 的 21 个失败：

| 终止原因 | 次数 |
| --- | ---: |
| insufficient_new_evidence | 6 |
| step_budget_exhausted | 5 |
| invalid_actor_output | 4 |
| recovery_exhausted | 3 |
| unsafe_repeated_action_after_recovery | 3 |

### 9 个成功与 3 次严格救回

成功任务：

`ExpenseDeleteDuplicates2`、`MarkorDeleteNewestNote`、`SimpleCalendarAnyEventsOnDate`、`SimpleCalendarDeleteEvents`、`SimpleCalendarEventsInTimeRange`、`SimpleCalendarFirstEventAfterStartTime`、`SystemBluetoothTurnOff`、`TasksHighPriorityTasks`、`TasksIncompleteTasksOnDate`。

严格 Recovery 救回：

1. `MarkorDeleteNewestNote`：LONG_PRESS → Tree `Delete` → Tree `OK` → reward 1；
2. `SimpleCalendarDeleteEvents`：连续无变化 → Tree `Yes` → reward 1；
3. `TasksHighPriorityTasks`：错误页面 → Recovery 打开 Tasks → 修正 ANSWER → reward 1。

### 基础设施无效/排除 6 题

- `OsmAndMarker`：OsmAnd databases 目录缺失；
- `OsmAndTrack`：tracks 目录缺失；
- `RecipeAddMultipleRecipes`：首次初始化前数据库目录缺失；
- `RecipeAddMultipleRecipesFromImage`：Windows SQLite 缺少 FTS4；
- 两个 Recipe delete 任务：与已确认失败共享 Broccoli/FTS4 验证器，未继续制造重复错误。

另有一次固定 14 题后缀在受限网络沙箱中启动，28 条记录均为 0 动作、0 成本、API Connection error。该目录保留为基础设施事故，不进入成绩；恢复网络权限后对完整固定后缀整体重启，没有按结果挑题。

由于 Runner v3 schema 规定 `frozen_evaluation` 必须恰好 36 题，基础设施分段后的后缀 manifest 元数据使用 `development` 角色；它只用于原清单连续后缀的操作性续跑，没有用于调参。该限制意味着最终结果应表述为“原冻结清单的 30 个有效配对”，不能声称一次无中断的 36 题 frozen batch 全部完成。

## 5. 成本与结论边界

正式 V2.2 开发回归 + 最终有效冻结运行的估算目录价合计约 ¥2.6628；加入对应 V1 冻结运行后约 ¥4.1052，仍在本轮总预算 ¥15 内。目录价是根据记录 Token 的估算值，不等于账单实扣。

最终可以说：V2.2 在 30 个有效固定未见任务配对上从 0/30 提升到 9/30，并出现 3 次可审计 Recovery 救回。

最终不能说：AndroidWorld 总体成功率为 30%、36 题全部完成、9 个成功全部来自 Agent Recovery，或协议补齐等同于通用推理能力。

逐题表与 Trace 证据见 [最终冻结评测报告](frozen-evaluation-report.md)。
