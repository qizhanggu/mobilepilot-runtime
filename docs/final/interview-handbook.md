# MobilePilot 面试讲解手册

这份文件不是背诵稿。面试共享屏幕时，按“问题 → 证据 → 改法 → 结果 → 边界”讲，听起来会更像你真的做过项目。

## 0. 项目事实卡

| 项目 | 事实 |
| --- | --- |
| 定位 | 可审计 Android GUI Agent Runtime，不训练 GUI 模型 |
| 技术栈 | Python、AndroidWorld、ADB、Android Emulator、uiautomator2、UI Tree、GUI-Plus/Qwen API、JSONL、pytest |
| Actor | `gui-plus-2026-02-26`，高频 action-only |
| Manager / Verifier | `qwen3.7-flash-2026-07-15`，低频事件触发 |
| 历史开发基线 | 同一暴露 20 题：V1 hybrid 4/20 |
| V2 开发 | 9/20；只证明定向开发收益 |
| Planner V2.1 | 5/20；负结果 |
| V2.2 最终开发 | 9/20；追平 V2，不是 held-out |
| 最终冻结清单 | 36 题中 30 个有效配对：V1 0/30，V2.2 9/30；9 改善、0 退化 |
| Recovery | 冻结有效配对中触发 25 次，严格救回 3 次 |
| 基础设施边界 | 6 题因 OsmAnd/Windows SQLite FTS4 无法形成有效配对 |
| 测试 | 186 passed |

## 1. 三种开场说法

### 30 秒

> MobilePilot 是一个可审计的 Android GUI Agent Runtime。我没有训练模型，而是把 GUI-Plus、AndroidWorld、ADB、按需 UI Tree、进度验证、有限 Recovery 和官方 reward 串成多步闭环。项目最早大量任务会因为坏输出、动作能力缺口或循环直接失败；我先审计 Trace 找到根因，再补齐 LONG_PRESS、DRAG、ANSWER，修正状态顺序和 evidence，最后在冻结清单 30 个有效配对上做到 V1 0/30、V2.2 9/30，其中 3 次是可追溯的真实 Recovery 救回。

### 1 分钟

> 我最开始以为手机 GUI Agent 的核心是坐标和视觉，所以做过网格、纯视觉和每步 UI Tree。但公开 ScreenSpot 上 Grid 反而从 70.49% 降到 66.67%，AndroidWorld hybrid 也只有 4/20。我回到 40 条多步 Trace，发现更大的问题是 Runtime：Actor 输出不稳定、动作契约缺 long press/drag/answer、模型自报完成、旧状态污染以及 Recovery 没有新证据。
>
> 后来我把 Actor 收窄成只输出下一动作，让 Runtime 管 subgoal 生命周期；确定性 Verifier 每步跑，视觉语义不确定时才让 Qwen 比较前后截图；UI Tree 只在失败或循环时按需调用；Recovery 最多两级，而且新动作必须有 Tree 或冻结任务证据。最终冻结 36 题中有 30 题形成有效配对，V2.2 完成 9 题、V1 完成 0 题，非法输出终止 21 降到 4，UI Tree 209 次降到 49 次。剩下 21 题仍失败，所以我不会说它解决了复杂长任务。

### 3 分钟

按下面六步展开：

1. **困难**：40 条 V1 Trace 有 31 条失败，其中 21 条非法输出；
2. **根因**：协议缺口、状态顺序、坏 postcondition、Recovery 无新证据；
3. **方案**：action-only Actor + Runtime State + 两层 Verifier + 按需 Tree + 两级 Recovery；
4. **关键实现**：LONG_PRESS/DRAG/ANSWER、官方 reward、JSONL Trace、冻结 Runner；
5. **结果**：开发 9/20；冻结有效 30 对为 0/30→9/30，3 次严格救回；
6. **边界**：6 题基础设施无效、21/30 仍失败、成本和延迟上升。

## 2. 一次动作怎样走完

1. Runtime 获取当前截图、package/activity 和便宜的 UI text；
2. 没有 active subgoal 时，低频 Manager 提出局部目标和 postcondition evidence；
3. GUI-Plus Actor 只看总目标、当前 subgoal、状态和截图，输出一个工具调用；
4. Protocol Guard 校验 schema；动作没执行时最多安全重试一次；
5. Critic 做坐标、文本和动作安全检查；
6. Adapter 映射成 AndroidWorld/ADB 动作；
7. 确定性 Verifier 比较 package、UI text、exact/visual/semantic fingerprint；
8. 证据不足或疑似异常时，Qwen 对比前后图输出五分类；
9. Runtime 先消费 confirmed progress/completed，再检查 loop，防止旧状态误杀；
10. 无进展时触发有限 Recovery，必要时读取 UI Tree；
11. 每步查询 official reward，只有 reward>=1.0 才结束为成功；
12. 所有事件进入 JSONL Trace。

## 3. 模块介绍

| 模块 | 解决的问题 | 关键边界 |
| --- | --- | --- |
| Actor | 当前页面下一步做什么 | action-only，不承担长计划和状态所有权 |
| Protocol Guard | JSON/schema/别名等接口不稳定 | 仅未执行动作时重试；不改变动作语义 |
| Action Contract | Runtime 能否表达模型意图 | LONG_PRESS/DRAG/ANSWER 有独立 schema 和 Adapter |
| Subgoal Manager | 当前局部要达到什么状态 | 低频调用；evidence 必须是 postcondition |
| Runtime State | 已完成什么、卡在哪里、验证什么 | subgoal 生命周期由 Runtime 冻结 |
| Deterministic Verifier | 便宜、确定的变化/完成证据 | 每步运行，不额外调用模型 |
| VLM Progress Verifier | 页面变了但方向是否正确 | 只分类/建议处置，不直接输出动作 |
| Loop Detector | 重复页面、重复动作、ABAB 循环 | confirmed progress 先 reset 旧 streak |
| Recovery | 失败后有限改路 | 最多动作级+子目标级；没有新证据就停 |
| UI Tree Tool | 失败时补结构信息 | 按需调用，不假设 Tree 等于任务理解 |
| Official Reward | 最终任务是否真的完成 | 唯一成功判据 |
| Trace / Runner | 审计、配对和成本统计 | 固定任务/model/seed/hash，保留负结果 |

## 4. 五个最重要的技术设计

### 4.1 Protocol Guard 不等于 Recovery

Protocol Guard 修“还没执行”的接口错误，例如：

- 多余自然语言包裹 JSON；
- 动作别名；
- 字段格式错误；
- 一次安全结构化重试。

Recovery 修“执行之后没有进展”的策略问题，例如：

- 点了没反应；
- 回到同一页面；
- 动作开始重复；
- 当前 subgoal 不成立。

如果面试官问亮点，别把 Protocol Guard 说成模型推理增强。它的价值是工程可靠性。

### 4.2 子目标内容软，生命周期硬

Manager 可以提出：

```text
goal: 进入目标短信会话
evidence: ui_text = 138xxxx1234
status: active
```

但一旦 Runtime 接受，Actor 不能下一步随意更换。只有三种出口：completed、Recovery 明确修订、整个任务结束。

这比每步把一大段 Planner 建议塞给 Actor 更稳：它不强迫模型照死计划走，但给 Verifier 和 Recovery 一个稳定抓手。

### 4.3 Completion Evidence 为什么只有三种

- `package_activity`：硬证据，适合“打开目标 App”；
- `ui_text`：次硬证据，适合标题、联系人、确认文字；
- `visual_state`：软证据，适合编辑页/详情页等语义状态。

能用确定性规则就不问 VLM。Evidence 描述“完成后新出现什么”，不是“下一步点什么”。电话号码会做空格、连字符等归一化。

冻结运行中 Manager 90 次调用仍有 38 次 already-satisfied failure，说明这个问题没有完全解决，正好可以作为局限讲。

### 4.4 Fingerprint 为什么保留两层

- exact SHA-256：判断字节级相同、审计复现；
- visual similarity：过滤状态栏时间、动画等轻微变化；
- semantic/UI Tree fingerprint：结构或可见文本是否变化；
- package/activity：是否发生上下文切换。

只用 SHA-256 太敏感；只用感知哈希又会丢失确定性。多信号组合更合理。

### 4.5 Recovery 为什么只有两级

第一次保持 subgoal 不变，换动作；第二次才允许修当前 subgoal。继续无限恢复会带来：

- 危险副作用重复；
- 成本不可控；
- Trace 难解释；
- 模型在错误上下文里越走越远。

冻结配对触发 25 次，只严格救回 3 次。这个数字不高，但比“触发了很多次”更有可信度。

## 5. 三条必须会讲的成功 Trace

### MarkorDeleteNewestNote

`LONG_PRESS → 页面重访 → Tree 找到 Delete → 确认框 → Tree 找到 OK → reward=1`

说明：动作契约、按需 Tree、两级 Recovery 和官方 reward 同时生效。

### SimpleCalendarDeleteEvents

连续无变化后，Tree 找到确认框 `Yes`，更换动作后 reward=1。

说明：Recovery 是局部对话框恢复，不必吹成全局规划。

### TasksHighPriorityTasks

错误页面 DRAG → Verifier stalled → Recovery 打开 Tasks → 多次 ANSWER 被 reward 校验 → 正确答案成功。

说明：Verifier 给处置，Runtime 换上下文，官方 reward 拒绝错误答案。

## 6. 实验结果怎么讲

### 开发集

同一暴露 20 题：

| 版本 | 成功 |
| --- | ---: |
| V1 hybrid | 4/20 |
| V2 | 9/20 |
| V2.1 Planner | 5/20 |
| V2.2 RCA 前 | 7/20 |
| V2.2 最终 | 9/20 |

这里能讲“定向修复有效”，不能讲泛化。

### 冻结任务

36 题清单在运行前固定，30 题形成有效配对：

| 指标 | V1 | V2.2 |
| --- | ---: | ---: |
| 官方成功 | 0/30 | 9/30 |
| invalid output | 21 | 4 |
| 平均动作 | 6.03 | 7.13 |
| UI Tree | 209 | 49 |
| VLM 调用 | 209 | 386 |
| 成本 | ¥1.4425 | ¥1.6521 |

配对为 9 改善、0 退化、21 双败。6 题因 OsmAnd 目录与 Windows SQLite FTS4 无法形成公平配对。

### 最诚实的解释

V2.2 的收益来自两部分：

1. **工程能力补齐**：long press、drag、answer、协议重试、官方判定；
2. **Agent Runtime 改进**：状态 reset、事件触发 Verifier、按需 Tree、有限 Recovery，形成 3 次严格救回。

不能把 9 个成功全算成“智能恢复”。21 个双败说明 Actor 页面理解和复杂任务规划仍是主要上限。

## 7. 高频面试问题

### Q1：这和 Appium 脚本有什么区别？

> 脚本预先知道控件和流程；MobilePilot 面对自然语言目标和动态截图，每步由模型决策。我的工作重点不是自动化 API，而是 Runtime 如何管理不稳定模型、验证进展和控制恢复风险。

### Q2：为什么不直接用 LangGraph？

> 当前核心难点是 AndroidWorld 动作语义、页面状态和 Trace 审计，不是图编排。自研轻量 loop 更容易控制每一步 official reward、动作是否执行和 Recovery 预算。未来流程更复杂时可以迁移，但现在上框架收益不高。

### Q3：为什么不用 Planner？

> 我做过 V2.1 Checklist 消融，只有 5/20，低于无 Planner 的 V2 9/20。原因是底层 Actor/evidence 不稳时，Planner 会把错误计划冻结得更久。所以先把 subgoal 生命周期、Verifier 和 Recovery 做扎实。

### Q4：V2.2 为什么调用更多？

> 它增加了低频 Manager 和事件触发 Verifier，并让更多任务不再因首个坏输出早死，所以执行更久。冻结成本从 ¥1.44 到 ¥1.65，约多 ¥0.21；这是可靠性换调用量的代价。

### Q5：9/30 仍然不高，价值在哪里？

> 第一，它是固定未见任务有效子集上的配对提升，不是只挑成功 Demo；第二，非法输出 21 降到 4，并出现 3 条可审计救回；第三，21 个失败也留下模块归因和负结果。项目价值是能定位、修复和验证 Agent 失败，不是声称达到 SOTA。

### Q6：为什么 V1 是 0/30？是不是故意做弱？

> V1 是冻结前已有的历史 Runtime，不支持 LONG_PRESS/ANSWER 等动作，且未知动作/坏输出会直接终止；模型、任务、seed 和步数都保持相同。我没有为了冻结集改 V1，也没有隐藏它的协议短板。对比证明的是 Runtime 工程补齐，不等于基础模型能力提升。

### Q7：Recovery 25 次为什么只救 3 次？

> 发现异常比找到正确替代策略容易。Tree 只能提供控件结构，不能理解完整任务；复杂表单和跨 App 错误往往不是换一个点击能修好。我保留 3/25，是为了区分“检测到了”与“真的救回了”。

### Q8：Verifier 准确率是多少？

> 冻结运行有 37 次调用，行为分布是 23 completed、8 stalled、4 progress、2 regressed。但没有对这 37 条逐条人工标注，所以我不报 accuracy。RCA 阶段人工审计表明它不是首要瓶颈，但这不等于正式准确率。

### Q9：为什么 UI Tree 调用少了还更好？

> V1 每步 Tree 共 209 次，但 Tree 不会自动规划。V2.2 只在非法输出、失败、循环或不确定时调用 49 次，其中 19 次改变动作，并直接支撑两条救回。减少的是无差别上下文，不是删除结构工具。

### Q10：12 步是不是太少？

> 开发回归为了历史可比保持 12 步；我只对 RCA 高度怀疑的重复日历任务做一次 20 步诊断，它仍失败。冻结任务在运行前统一固定 16 步。结果说明很多步数耗尽其实来自路线错误，不是简单加预算就能解决。

### Q11：怎么保证没在冻结集上调参？

> 先固定清单、顺序、任务 hash、Agent source hash、commit、模型、seed、步数和预算。首条结果后不改 Prompt/Runtime/Recovery。基础设施坏批次原样保留；网络恢复只重启完整固定后缀，不按成败挑题。

### Q12：6 个无效任务为什么不算失败？

> 它们在 Agent 接管前就因 App 目录或 SQLite FTS4 初始化失败，两个版本无法公平运行。把基础设施失败记成 Agent 失败会污染结论，所以单独披露，不进入 30 对分母。

### Q13：如果继续做，最优先改什么？

> 不再加模块。第一，降低 Manager already-satisfied evidence；第二，用失败 Trace 提升 Actor 对复杂表单/跨 App 页面的动作选择；第三，让 Recovery 在有新证据时形成更少但更有效的策略。重新开发后需要再冻结新任务，不能继续吃这 36 题。

## 8. 面试时不要说错

| 不要说 | 应该说 |
| --- | --- |
| AndroidWorld 成功率 30% | 冻结 36 题清单中 30 个有效配对，V2.2 9/30 |
| 36 题全部跑完 | 30 对有效，6 题基础设施无效/排除 |
| Recovery 成功 25 次 | 触发 25 次，严格救回 3 次 |
| 9 个成功都是 Agent 推理提升 | 部分来自 Action Contract/ANSWER，3 个来自严格 Recovery |
| UI Tree 让模型理解任务 | Tree 提供结构证据，但不提供完整任务语义 |
| Verifier 准确率很高 | 统计了 37 次行为，没有冻结集人工 accuracy |
| V2.2 提升了模型能力 | 模型固定，改进来自 Runtime 和动作契约 |
| 开发 20 题是 held-out | 已参与 RCA，只是 development/regression set |

## 9. 共享屏幕展示顺序

1. README 架构图：30 秒讲清闭环；
2. `docs/final/frozen-evaluation-report.md`：展示 0/30→9/30 和边界；
3. MarkorDeleteNewestNote Trace：搜索 `LONG_PRESS`、`ui_tree_decision`、`recovery_outcome`、`official_reward`；
4. `mobile_pilot/androidworld/agent.py`：展示 official reward、completed-before-loop、Recovery；
5. `mobile_pilot/androidworld/actor.py`：展示 action-only schema；
6. `mobile_pilot/androidworld/adapter.py`：展示 LONG_PRESS/DRAG/ANSWER；
7. `docs/final/v22-root-cause-analysis.md`：展示如何从 termination reason 追到 root cause；
8. pytest 结果：186 passed。

## 10. 面试前至少理解的 10 个词

1. Protocol Guard
2. Action Contract
3. Runtime State
4. Subgoal lifecycle
5. Completion Evidence / postcondition
6. Deterministic Verifier
7. VLM Progress Verifier
8. Loop Detection
9. Recovery budget
10. Official reward

## 11. 收尾话术

> 这个项目让我真正学到的不是怎么让模型多点几下，而是怎么把一个不稳定模型放进可控 Runtime：什么时候相信它，什么时候验证，什么时候给工具，什么时候恢复，什么时候必须停。最终 9/30 不算高，但它来自冻结配对，并且我能把 3 次救回和 21 次失败都回到 Trace 解释清楚。我觉得这比只展示几个成功 Demo 更接近 Agent 工程。
