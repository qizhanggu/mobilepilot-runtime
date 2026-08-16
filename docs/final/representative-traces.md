# 代表性成功与失败 Trace

本文只选可回到 JSONL 逐事件核对的案例。最终完成统一以 AndroidWorld `official_reward >= 1.0` 为准。

## 1. 最完整的 Recovery 救回：MarkorDeleteNewestNote

Trace：

`artifacts/evaluation/androidworld-v22-final-frozen36-20260817/traces/MarkorDeleteNewestNote--v2.2--hybrid.jsonl`

关键链路：

1. step 3：Actor 输出 `LONG_PRESS`，Adapter 通过 AndroidWorld 执行；
2. step 4：页面重访触发动作级 Recovery，blocked action 为 `LONG_PRESS:6:15`；
3. UI Tree 给出 `Delete`，Runtime 记录 chosen element 和 changed action；
4. step 5：确认框出现，第二级 Recovery 从 Tree 找到 `OK`；
5. step 6：点击 `OK` 后 official reward=1；
6. `agent_recovery_outcome.rescued=true`。

这条 Trace 同时证明：

- LONG_PRESS 不是被 Protocol Guard 偷偷改成 CLICK；
- UI Tree 是事件触发工具，不是每步上下文；
- Recovery 不是“换个随机动作”，而是引用了 `Delete`/`OK` 两个可见元素；
- 最终成功来自官方 reward，不是模型口头宣布。

## 2. 对话框级 Recovery：SimpleCalendarDeleteEvents

Trace：

`artifacts/evaluation/androidworld-v22-final-frozen36-continuation5-network-restored-20260817/traces/SimpleCalendarDeleteEvents--v2.2--hybrid.jsonl`

关键链路：

- 前 9 步完成定位和删除动作；
- 连续无变化触发 Recovery；
- UI Tree 在确认框中定位 `Yes`；
- 动作改为点击 `Yes`；
- 下一步 official reward=1，Recovery 标记 rescued。

这不是“重新规划整个日历任务”，而是一次范围清楚的局部恢复。它体现了有限 Recovery 比无限重试更可审计。

## 3. 错误上下文恢复：TasksHighPriorityTasks

Trace：

`artifacts/evaluation/androidworld-v22-final-frozen36-continuation5-network-restored-20260817/traces/TasksHighPriorityTasks--v2.2--hybrid.jsonl`

关键链路：

1. Agent 起初处于错误页面并尝试 DRAG；
2. Progress Verifier 判定 stalled；
3. Tree 没给出足够元素，Runtime 没有伪造 Tree grounding；
4. 冻结任务/子目标明确指向 Tasks，受限 fallback 选择 `OPEN_APP[tasks]`；
5. Actor 连续提交候选 ANSWER，官方 reward 直到正确答案才从 0 变为 1；
6. Recovery outcome 记录 rescued=true。

这条案例展示了：Verifier 只给处置分类，真正动作仍由 Actor/Runtime 产生；官方 reward 能拒绝错误答案并接受后续修正。

## 4. Action Contract 直接带来成功：SimpleCalendarAnyEventsOnDate

Trace：

`artifacts/evaluation/androidworld-v22-final-frozen36-continuation5-network-restored-20260817/traces/SimpleCalendarAnyEventsOnDate--v2.2--hybrid.jsonl`

执行链路是：

`OPEN_APP → CLICK_POINT → ANSWER("Board meeting, Weekend trip, Birthday party") → official reward=1`

这个案例应归因于 **ANSWER/interaction_cache 契约补齐 + Actor 正确读取页面**，不能包装成 Recovery 推理提升。

同类成功还有：

- `SimpleCalendarEventsInTimeRange`：ANSWER `Cooking Class`；
- `SimpleCalendarFirstEventAfterStartTime`：导航后 ANSWER `Haircut`；
- `TasksIncompleteTasksOnDate`：官方 reward 拒绝前两个候选答案，接受第三个答案。

## 5. 能表达动作，但仍不会完成：MarkorDeleteAllNotes

Trace：

`artifacts/evaluation/androidworld-v22-final-frozen36-20260817/traces/MarkorDeleteAllNotes--v2.2--hybrid.jsonl`

V1 因 `unsupported_action_capability` 早停；V2.2 已能执行 LONG_PRESS 并继续 12 个动作，但最终 Recovery 耗尽。

它说明 Action Contract 把任务从“系统性不可表达”推进到“可以尝试”，却没有自动增强复杂列表操作规划。这个负例用于约束简历表述。

## 6. Recovery 正确拒绝随机动作：BrowserMultiply

Trace：

`artifacts/evaluation/androidworld-v22-final-frozen36-20260817/traces/BrowserMultiply--v2.2--hybrid.jsonl`

V2.2 触发 Recovery 后，Tree 没有提供能支持新路线的语义元素。Runtime 以 `insufficient_new_evidence` 停止，没有为了 changed_action=true 去随机点击。

这不是成功，但属于安全改进：失败原因从“动作重复到步数耗尽”变成“缺少可验证新证据”。

## 7. 模型误报完成仍被官方 reward 拒绝

`SportsTrackerActivityDuration` 的 V1 以 `actor_proposed_complete` 结束，但 official reward=0。V2.2 没有采信口头完成，而是继续验证，最终因缺少新证据失败。

两版都没完成任务，但 V2.2 保持了正确的成功判定边界。

## 8. 基础设施错误不是 Agent 失败

以下记录发生在 Agent 接管前，不进入 30 个有效配对：

- `OsmAndMarker`：databases 目录不存在；
- `OsmAndTrack`：tracks 目录不存在；
- Recipe 任务：Windows SQLite 缺少 FTS4。

另一个固定后缀批次因受限网络环境产生 28 条 `Connection error`，全部是 0 动作、0 成本。原目录保留，网络恢复后的整批结果单独存储，不能用坏批次填入 Agent failure taxonomy。

## 9. Trace 阅读顺序

面试展示一条 Trace 时，建议只看这些事件：

1. `observation`：当时页面、package、Tree 是否被请求；
2. `actor_decision`：模型原始输出与解析结果；
3. `critic` / `protocol_guard`：动作是否安全、有没有结构化重试；
4. `execution`：真正执行了什么；
5. `deterministic_progress_verifier` / `vlm_progress_verifier`：进展证据；
6. `agent_recovery_triggered` / `ui_tree_decision` / `agent_recovery_replan`：为什么恢复、依据什么换动作；
7. `official_reward`：最终环境判定；
8. `agent_recovery_outcome`：是否形成严格救回。
