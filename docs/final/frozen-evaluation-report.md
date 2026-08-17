# MobilePilot V2.2 最终冻结评测报告

> 评测日期：2026-08-17
>
> 冻结 Agent commit：`487f2abe7382d11a5cc15572c4902265547d42dd`
>
> AndroidWorld commit：`3e50888527ef9f29b9157ecd537e408008bb1c85`

## 1. 结论先行

最终清单原本包含 36 个未用于开发的 AndroidWorld 任务。受 Windows/模拟器基础设施限制，30 个任务形成了完整的 V1/V2.2 配对，6 个任务在 Agent 接管前无法形成公平配对。

在 30 个有效配对上：

| 指标 | V1 | V2.2 |
| --- | ---: | ---: |
| AndroidWorld 官方完整成功 | 0/30（0%） | 9/30（30%） |
| partial | 0 | 0 |
| 非法 Actor 输出终止 | 21/30 | 4/30 |
| 步数耗尽终止 | 4/30 | 5/30 |
| 平均执行动作 | 6.03 | 7.13 |
| UI Tree 请求 | 209 | 49 |
| VLM 调用 | 209 | 386 |
| Token | 916,115 | 1,507,742 |
| 模型延迟 | 1,304.77 s | 2,226.09 s |
| 估算目录价 | ¥1.4425 | ¥1.6521 |

逐题配对为：**9 题改善、0 题退化、0 题双方成功、21 题双方失败**。这个结果说明 V2.2 在固定未见任务有效子集上复现了收益，但不代表 AndroidWorld 总体成绩；4 个实际观测到的初始化失败和 2 个共享依赖同族排除必须与 9/30 同时披露。

## 2. 冻结边界

- Actor：`gui-plus-2026-02-26`
- Subgoal Manager / Progress Verifier：`qwen3.7-flash-2026-07-15`
- mode：`hybrid`
- seed：`0`
- 最大动作步数：`16`
- 原始 36 题清单 hash：`cc408d7185991b356d60531c33ca2ca1c5681aa13e62eeeae03c70983437e8b2`
- Agent source hash：`246cce8ea4a7c7edac304cac267f41e9fe59945e6de3332c284db2fe650e74cb`
- 唯一设备：`emulator-5554`

首次结果出现后，没有根据冻结任务修改 Prompt、Runtime、Recovery、Evidence 或动作策略；没有对 Agent 失败做单题重试。

运行中产生过一个“0 动作、0 成本、全部 API Connection error”的后缀批次。该批次完整保留，但判为运行基础设施无效；恢复网络权限后，对同一固定 14 题后缀整体重启，未挑题、未改代码。

Runner 的 v3 schema 只允许 `frozen_evaluation` 角色包含恰好 36 题，因此分段后缀 manifest 在元数据中使用 `development` 角色；它只承担基础设施续跑，不代表这些题被用于开发。后缀仍来自原冻结清单的连续固定区间，并保持相同 Agent source hash、模型、seed、mode 和 16 步上限。这个协议降级在报告中显式披露，不能把分段产物描述成一条无中断的 36 题 batch。

## 3. 30 题逐题配对

| 任务 | V1 | V2.2 | 结果 | V2.2 关键说明 |
| --- | --- | --- | --- | --- |
| BrowserDraw | 失败：非法输出 | 失败：非法输出 | 双败 | 协议仍未得到可执行动作 |
| BrowserMaze | 失败：非法输出 | 失败：Recovery 耗尽 | 双败 | 能继续执行，但未完成迷宫 |
| BrowserMultiply | 失败：步数耗尽 | 失败：新证据不足 | 双败 | Recovery 拒绝随机换动作 |
| ExpenseAddMultiple | 失败：非法输出 | 失败：步数耗尽 | 双败 | 多字段表单仍是 Actor 瓶颈 |
| ExpenseAddMultipleFromGallery | 失败：非法输出 | 失败：恢复后危险重复 | 双败 | 跨 App 路线没有被救回 |
| ExpenseAddMultipleFromMarkor | 失败：非法输出 | 失败：新证据不足 | 双败 | Tree 没有给出可靠新策略 |
| ExpenseDeleteDuplicates2 | 失败：非法输出 | **成功** | 改善 | 10 个动作完成，非 Recovery 救回 |
| ExpenseDeleteMultiple | 失败：动作能力缺口 | 失败：新证据不足 | 双败 | 补能力后仍缺正确多项删除策略 |
| ExpenseDeleteMultiple2 | 失败：非法输出 | 失败：步数耗尽 | 双败 | 路线过长且动作浪费 |
| FilesDeleteFile | 失败：非法输出 | 失败：步数耗尽 | 双败 | 能继续执行但未在 16 步内完成 |
| MarkorDeleteAllNotes | 失败：动作能力缺口 | 失败：Recovery 耗尽 | 双败 | LONG_PRESS 可执行，但任务规划仍失败 |
| MarkorDeleteNewestNote | 失败：动作能力缺口 | **成功** | 改善 | LONG_PRESS + Tree 的 Delete/OK，严格 Recovery 救回 |
| MarkorDeleteNote | 失败：非法输出 | 失败：Recovery 耗尽 | 双败 | 纠偏仍未形成有效删除链路 |
| MarkorMergeNotes | 失败：非法输出 | 失败：步数耗尽 | 双败 | 复杂笔记操作仍超出能力 |
| MarkorTranscribeReceipt | 失败：步数耗尽 | 失败：新证据不足 | 双败 | 跨图像抄录没有可靠路径 |
| OsmAndFavorite | 失败：非法输出 | 失败：恢复后危险重复 | 双败 | App 可运行，但地图交互失败 |
| SimpleCalendarAddOneEventRelativeDay | 失败：非法输出 | 失败：步数耗尽 | 双败 | 长表单未在 16 步内完成 |
| SimpleCalendarAnyEventsOnDate | 失败：非法输出 | **成功** | 改善 | ANSWER 提交官方答案 |
| SimpleCalendarDeleteEvents | 失败：非法输出 | **成功** | 改善 | Tree 找到确认框 Yes，严格 Recovery 救回 |
| SimpleCalendarEventsInNextWeek | 失败：非法输出 | 失败：恢复后危险重复 | 双败 | 查询理解不稳定 |
| SimpleCalendarEventsInTimeRange | 失败：非法输出 | **成功** | 改善 | ANSWER 提交官方答案 |
| SimpleCalendarFirstEventAfterStartTime | 失败：执行失败 | **成功** | 改善 | 导航后通过 ANSWER 提交答案 |
| SportsTrackerActivitiesOnDate | 失败：步数耗尽 | 失败：非法输出 | 双败 | 页面理解/答案生成失败 |
| SportsTrackerActivityDuration | 失败：模型误报完成 | 失败：新证据不足 | 双败 | V2.2 阻止误报，但没有得到正确答案 |
| SportsTrackerTotalDistanceForCategoryOverInterval | 失败：步数耗尽 | 失败：新证据不足 | 双败 | 复杂检索仍失败 |
| SystemBluetoothTurnOff | 失败：非法输出 | **成功** | 改善 | 正常动作闭环获得官方成功 |
| SystemBrightnessMin | 失败：非法输出 | 失败：非法输出 | 双败 | DRAG 能力存在，但 Actor 输出仍失败 |
| SystemWifiTurnOn | 失败：非法输出 | 失败：非法输出 | 双败 | 未得到稳定动作 |
| TasksHighPriorityTasks | 失败：非法输出 | **成功** | 改善 | 错屏后 Recovery 打开正确 App，再修正 ANSWER |
| TasksIncompleteTasksOnDate | 失败：非法输出 | **成功** | 改善 | 多次受控 ANSWER 后由官方 reward 确认 |

## 4. 失败终止统计

### V1（30 个失败）

| 终止原因 | 数量 |
| --- | ---: |
| invalid_actor_output | 21 |
| step_budget_exhausted | 4 |
| unsupported_action_capability | 3 |
| action_execution_failed | 1 |
| actor_proposed_complete | 1 |

### V2.2（21 个失败）

| 终止原因 | 数量 |
| --- | ---: |
| insufficient_new_evidence | 6 |
| step_budget_exhausted | 5 |
| invalid_actor_output | 4 |
| recovery_exhausted | 3 |
| unsafe_repeated_action_after_recovery | 3 |

V2.2 把大量“接口一坏就死”转成了更晚、更可解释的失败，但失败重心也因此转移到多步决策、页面理解和 Recovery 纠偏质量。`insufficient_new_evidence` 不是成功，却比随机换动作更安全、更可审计。

## 5. Recovery 专项

V2.2 共触发 Recovery 25 次，严格救回 3 次，救回率为 3/25；没有把“触发”包装成“有效”。

### MarkorDeleteNewestNote

1. Actor 用新增 `LONG_PRESS` 选中最新笔记；
2. 页面重访触发 Recovery；
3. UI Tree 定位 `Delete`，动作从长按改为点击删除；
4. 确认框出现后，第二级 Recovery 从 Tree 定位 `OK`；
5. 官方 reward 从 0 变为 1。

这是最完整的“失败信号 → Tree 新证据 → 改变动作 → 官方成功”案例。

### SimpleCalendarDeleteEvents

连续无变化触发 Recovery，UI Tree 找到确认框 `Yes`，更换动作后官方 reward=1。这里 Recovery 解决的是对话框确认，而不是重新规划整个任务。

### TasksHighPriorityTasks

Agent 一开始处于错误页面并尝试 DRAG。Verifier 判定 stalled 后触发 Recovery；Tree 本身没有足够元素，但冻结的任务/子目标明确要求打开 Tasks，Runtime 使用受限的 `OPEN_APP[tasks]` 回到正确上下文，随后 Actor 修正答案并获得官方成功。

其余 22 次 Recovery 没有救回。主要模式是：Tree 没有任务语义、Actor 改了动作但没解决根因，或者复杂表单/跨 App 任务在剩余步数内来不及完成。

## 6. Subgoal、Verifier 与按需 Tree

Subgoal Manager 共调用 90 次：

| Manager outcome | 次数 |
| --- | ---: |
| accepted | 48 |
| invalid_already_satisfied_regenerating | 21 |
| invalid_already_satisfied | 17 |
| revised | 2 |
| unchanged | 2 |

一次受限再生成挡住了 21 个“动作前已满足”的坏 Evidence，但仍有 17 次再生成后失败。Completion Evidence 的 postcondition 质量仍是明确局限。

VLM Progress Verifier 调用 37 次，输出 23 `completed`、8 `stalled`、4 `progress`、2 `regressed`。这些是运行行为统计，不是准确率；冻结集没有逐条人工 ground truth，不能声称 Verifier 达到某个 accuracy。

V1 hybrid 每步读取 Tree，共 209 次。V2.2 按需读取 49 次，其中 19 次改变动作。Tree 调用下降约 76.6%，并在两条严格救回中提供了直接可见元素。

## 7. 基础设施无效任务与保留证据

| 任务 | 处理 | 原因 |
| --- | --- | --- |
| OsmAndMarker | 记录 infrastructure_error，不重试 | `/data/data/net.osmand/databases` 不存在 |
| OsmAndTrack | 记录 infrastructure_error，不重试 | tracks 目录不存在，初始 reward 无法读取 |
| RecipeAddMultipleRecipes | 记录 infrastructure_error，不重试 | App 首次初始化前数据库目录不存在 |
| RecipeAddMultipleRecipesFromImage | 记录 infrastructure_error，不重试 | Windows Python SQLite 缺少 FTS4 |
| RecipeDeleteDuplicateRecipes2 | 同族排除，未运行 | 与已确认失败共享 Broccoli/FTS4 数据库验证器 |
| RecipeDeleteMultipleRecipesWithConstraint | 同族排除，未运行 | 与已确认失败共享 Broccoli/FTS4 数据库验证器 |

缺失的官方 App APK 后续只安装到 `emulator-5554`，没有修改 Windows 或 VMware。由于 FTS4 修复需要改变系统级 SQLite/Python 环境，本轮按边界停止。

## 8. 可以写什么，不能写什么

可以写：

- 在 30 个有效未见任务配对上，V1 0/30、V2.2 9/30，9 改善、0 退化；
- 非法输出终止从 21 降到 4；
- 25 次 Recovery 中有 3 次严格救回；
- 按需 Tree 从 209 次降到 49 次；
- LONG_PRESS、DRAG、ANSWER 补齐了 Runtime 与 AndroidWorld 的动作/答案契约。

不能写：

- “AndroidWorld 总体成功率 30%”；
- “36 题全部完成”；
- “Verifier 准确率很高”；
- “所有 9 个成功都来自智能 Recovery”；
- “协议兼容修复等同于通用 Agent 推理能力”。

## 9. 最直白的结论

V2.2 的确把项目从“经常因为协议或能力缺口提前死亡”推进到了“能在一部分未见任务上完成闭环”，并出现 3 条真实 Recovery 救回。它没有解决复杂表单、跨 App 长任务和稳定页面理解；21/30 仍失败。最终价值不是一个总榜分数，而是把 Trace 审计、根因定位、最小修复、开发回归、冻结配对和负结果保留串成了可复现的 Agent Runtime 工程链路。
