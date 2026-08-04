# AndroidWorld Sprint 5：V2 失败审计与改进假设

日期：2026-07-31
状态：**实现前冻结；统计来自既有 40 条 Trace，不使用 Git 历史代替运行证据。**

## 证据边界

- Trace 来源：`artifacts/evaluation/androidworld-held-out-20260731/traces/`，共 20 题 × `vision_only/hybrid` = 40 条。
- 这 20 题的结果已经被查看，从本 Sprint 起只作为**开发/回归集**，不再称为 held-out。
- AndroidWorld 固定 commit：`3e50888527ef9f29b9157ecd537e408008bb1c85`。
- 模型固定为 `gui-plus-2026-02-26`；官方 `task.is_successful(env)` reward 是唯一最终成功判定。
- 原始 Trace、`runs.jsonl`、`summary.json` 和 `preflight.json` 均保持不变。

## 40 条运行的事实基线

| 指标 | vision_only | hybrid | 合计 |
| --- | ---: | ---: | ---: |
| 运行数 | 20 | 20 | 40 |
| 官方成功 | 5 | 4 | 9 |
| 执行动作 | 126 | 81 | 207 |
| 平均动作步数 | 6.30 | 4.05 | 5.18 |
| VLM 调用 | 140 | 94 | 234 |
| Token | 412,430 | 421,748 | 834,178 |
| 模型延迟总和 | 493.60 s | 307.00 s | 800.60 s |
| 估算目录价 | ¥0.660903 | ¥0.659601 | ¥1.320504 |

31 条失败的终止原因：

| 终止原因 | 数量 | 占失败比例 | Trace 解释 |
| --- | ---: | ---: | --- |
| `invalid_actor_output` | 21 | 67.7% | 当前 Runtime 在首次非法输出后直接结束 |
| `step_budget_exhausted` | 7 | 22.6% | 4 条明显重复导航/动作循环；3 条为长表单低效或步数不足 |
| `actor_proposed_complete` | 2 | 6.5% | 模型提议完成，但官方 reward 仍为 0；一次拒绝后仍未完成 |
| `action_execution_failed` | 1 | 3.2% | `OPEN_APP Note` 被 AndroidWorld 当作无效 app/package 执行 |

> 另有一条 `SimpleSmsResend--vision_only` 在最后一次非法输出后读取到官方 reward=1，
> 因而属于官方成功，不计入 21 条非法输出终止。所有成功数都以官方 reward 为准。

## Failure taxonomy

### F1：输出协议可靠性

40 条运行中共有 22 个未解析 decision：

| 子类 | 数量 | 是否可在本轮通用处理 |
| --- | ---: | --- |
| 空响应 | 11 | 可以；在尚未执行动作时进行至多一次结构化重试 |
| 模型请求超时 | 1 | 可以；与空响应一样做一次有界重试 |
| 未支持动作：`PRESS_ENTER`×2、`SAVE`、`SLIDE` | 4 | 只重试，不猜测执行语义 |
| CLICK 坐标缺单侧方括号 | 4 | 可以；仅在恰有两个数值且动作无歧义时归一化 |
| OPEN_APP 的可选 `reason` 引号破坏 JSON | 1 | 可以；仅独立提取并校验 `action/app_name` |
| SWIPE 缺少方向 | 1 | 不猜方向；进行一次结构化重试 |

边界：Protocol Guard 只做无歧义格式归一化、schema 校验和一次安全重试。
它不是 Agent 推理或规划能力，不计为 Agent Recovery。

### F2：无进展导航与动作循环

7 条步数耗尽中，以下 4 条有明显循环：

- `SystemBrightnessMax--vision_only`：反复 `OPEN_APP settings` 和相反方向 SWIPE；
- `SystemCopyToClipboard--vision_only`：错误 App、app drawer、WAIT/BACK 之间往返；
- `SimpleSmsReply--hybrid`：连续 SWIPE 搜索 App，最后才重新 `OPEN_APP`；
- `SimpleSmsSendClipboardContent--hybrid`：左右/向上 SWIPE、错误 Messages App 与返回之间循环。

另外 3 条是长表单/长流程未在 12 步内完成：

- `ContactsNewContactDraft--vision_only`；
- `SimpleCalendarAddOneEvent--vision_only`；
- `SimpleCalendarAddRepeatingEvent--vision_only`。

本轮只针对可通用检测的“相似动作重复、页面无变化、近期页面回访”做一次有限
replan；不通过增加步数掩盖长任务能力不足。

### F3：错误完成提议

`SimpleCalendarEventOnDateAtTime--vision_only` 与
`SimpleCalendarNextEvent--vision_only` 均出现模型自报完成但官方 reward=0。
继续保持“模型只提议、官方 reward 唯一裁决”，且每个任务最多允许一次拒绝后的继续。

### F4：动作执行失败

`SystemCopyToClipboard--hybrid` 的 `OPEN_APP Note` 执行失败。V2 在执行结果不确定时
重新观察并允许一次 replan，但禁止原样重复失败动作，尤其不重复 TYPE 等可能修改数据的动作。

## 最多两个优先改进目标

1. **输出可靠性**：覆盖最多失败，且可用离线 parser/Agent 测试稳定验证。
2. **无进展后的有限 replan**：覆盖第二大失败簇，体现状态管理、循环检测和工具按需调用；
   只允许一次，不把无限重试包装成恢复能力。

## V2-A 实现前假设

### H1：Protocol Guard

- 触发：解析失败、空响应或模型调用失败，且本轮尚未执行任何设备动作。
- 行为：
  1. 先尝试无歧义本地归一化；
  2. 若仍失败，按需重新观察并获取 UI Tree；
  3. 带原错误反馈做至多一次结构化模型重试；
  4. 重试仍失败则以 `invalid_actor_output` 结束。
- 指标：首次非法 decision 数、归一化数、重试数、重试后得到合法动作数、重试后官方成功数。
- 风险：重试增加 VLM 调用、延迟和成本；格式合法不等于动作正确。

### H2：有限 Agent Recovery

- 触发：动作明确执行失败、连续两次页面无变化、相似动作达到循环阈值或近期页面反复回访。
- 行为：重新观察、按需请求 UI Tree、注入 blocker/短期进度，最多触发一次 replan；
  不自动重放失败动作，不猜测性重复 TYPE、删除、发送等可能产生副作用的动作。
- 指标：循环次数、Recovery 触发数、获得不同动作数、官方救回数、误触发数。
- 风险：过早 replan 可能打断有效重复动作；因此阈值、一次上限和完整 Trace 是验收条件。

## V2-A / V2-B 验收指标

- 官方成功率；
- 非法输出终止率；
- 步数耗尽率；
- 无进展循环次数；
- Protocol Guard 归一化/重试/合法化/官方成功数；
- Agent Recovery 触发数、救回数、误触发数；
- 平均动作步数；
- VLM 调用数、Token、模型延迟、估算目录价；
- 每类失败原因；
- UI Tree 触发原因、元素摘要、是否改变下一动作、是否最终由官方 reward 救回。

开发完成后先在上述已暴露 20 题上回归。新评测集必须从未用于开发的任务中重新冻结，
并在查看结果前固定任务清单、代码 commit、Prompt、模型、seed、步数上限、指标和预算。
