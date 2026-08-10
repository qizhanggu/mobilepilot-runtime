# AndroidWorld Sprint 15：Action-only Actor 预测试检查点

日期：2026-08-10

状态：**代码与本地自动化测试完成，162/162 通过；尚未运行新的 AndroidWorld 真实任务，因此没有成功率提升结论。**

## 为什么改

前两条 V2.2 开发冒烟任务暴露出一个新的核心问题：GUI Plus 被要求在每一步同时输出动作、子目标和完成证据，四次调用中有三次为空输出。一次有效输出虽然完成了“打开快捷设置”子目标，并被 Qwen Verifier 确认，但下一步仍因 Actor 空输出终止。

本轮假设是：GUI Plus 更适合高频完成“当前画面 → 下一步工具动作”，不适合同时承担动作选择、子目标设计、状态写入和自我验证。减少 Actor 协议负担，可能先降低 `invalid_actor_output`，再为 Recovery 提供稳定抓手。

## 最小改造

1. V2.2 Actor 改成 action-only 工具协议，只输出一个 `mobile_action`；旧裸 JSON 仍可解析，历史 Trace 和协议兼容路径不被破坏。
2. 新增低频 `QwenSubgoalManager`。它不是完整 Planner，只提出一个当前子目标及一条完成证据，不输出点击、坐标或操作序列。
3. Subgoal Manager 仅在三个边界触发：任务开始、上一个子目标被确认、第二层 Recovery 获准修改子目标。正常 Actor 步不会调用它。
4. Runtime 接受后冻结子目标和证据。GUI Plus 只能围绕当前子目标行动，不能改写它；Verifier 仍负责确认进度，AndroidWorld official reward 仍是整题成功的唯一判定。
5. Subgoal Manager 失败时不猜测证据，也不在每一步反复调用。Actor 可以继续根据整题目标做安全动作，但该阶段不获得子目标验证能力。

## 当前调用关系

```text
关键边界 → Qwen Subgoal Manager → 一个子目标 + 完成证据
                                      ↓ Runtime 冻结
每个动作步 → GUI Plus Actor → 一个 mobile_action → AndroidWorld 执行
                                      ↓
确定性证据 / 事件触发 Qwen Verifier → 完成、继续或 Recovery 建议
                                      ↓
AndroidWorld official reward → 唯一整题成功结果
```

## Actor 协议示例

输入仍包含整题目标、当前截图、冻结子目标、短期进度和必要的 Recovery 反馈；输出收窄为：

```xml
<tool_call>
{"name":"mobile_action","arguments":{"action":"swipe","direction":"down","reason":"open quick settings"}}
</tool_call>
```

Actor 不再返回 `subgoal` 或 `completion_evidence`。

## 本地验证

- 新工具协议解析与旧 JSON 兼容；
- Qwen Subgoal Manager 的单图输入、关闭 thinking、结构化 JSON 和非法证据拒绝；
- 子目标在 Actor 决策前冻结；
- 正常多步执行不会每步调用 Manager；
- 子目标完成后，下一步边界才生成新子目标；
- 第二层 Recovery 才允许一次子目标修订；
- 全仓库：`162 passed`。

## 证据边界与下一步

这次结果只证明代码职责拆分和生命周期约束按设计工作，**不证明空输出已经消失，也不证明 AndroidWorld 通过率提升**。下一步应先在已暴露的开发任务上做少量真实协议冒烟，确认 GUI Plus 能稳定返回 `mobile_action`；通过后再重复原 20 题开发回归。任何提升只能称为开发集改善，不能称为 held-out 泛化。
