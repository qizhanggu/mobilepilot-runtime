# AndroidWorld Sprint 8：V2 开发回归结果

日期：2026-08-04

状态：**已完成暴露 20 题上的 V1/V2 配对开发回归；该结果不是 held-out 泛化成绩。**

## 先说结论

在同一批已经用于分析和开发的 20 个任务上，V2 hybrid 的官方成功数从 V1 的
`4/20` 提升到 `9/20`。逐题配对后，6 题由失败变为成功，1 题由成功退化，3 题
两版都成功，10 题两版都失败。

V2 的 Recovery 共触发 10 次，其中 3 次最终得到 AndroidWorld 官方 reward，形成
了真实的“失败信号 -> 重新观察/重规划 -> 改变动作 -> 官方成功”链路。其余 7 次
没有救回，不能记作 Agent 能力收益。

这些数字只能说明开发集上的定向改进有效，不能说明对未见任务具有同等提升。

## 固定条件

- AndroidWorld commit：`3e50888527ef9f29b9157ecd537e408008bb1c85`
- 模型：`gui-plus-2026-02-26`
- 模式：`hybrid`
- seed：`0`
- 最大动作步数：`12`
- 设备：仅 `emulator-5554`
- V2 运行期间未改 Prompt、未挑题重试、未覆盖旧产物
- V2 源码 hash：`456cf27698409fedd3b093f7398743f747c9bce24dea754bc332fefdd50a1194`

V1 来自 `artifacts/evaluation/androidworld-held-out-20260731/`。该目录名是历史命名；
因为任务结果已经被用于 V2 开发，它从本 Sprint 起只作为开发/回归证据。

V2 来自 `artifacts/evaluation/androidworld-v2-development-20260804/regression-20/`。

## 配对结果

| 指标 | V1 hybrid | V2 hybrid | 变化 |
| --- | ---: | ---: | ---: |
| 官方成功 | 4/20（20%） | 9/20（45%） | +5 题 / +25 个百分点 |
| 非法输出终止 | 13/20（65%） | 7/20（35%） | -6 题 / -30 个百分点 |
| 步数耗尽终止 | 2/20（10%） | 1/20（5%） | -1 题 / -5 个百分点 |
| 平均执行动作数 | 4.05 | 5.60 | +1.55 |
| VLM 调用数 | 94 | 144 | +50 |
| Token | 421,748 | 493,719 | +71,971 |
| 模型延迟合计 | 307.00 s | 425.34 s | +118.34 s |
| 估算目录价 | ¥0.6596 | ¥0.7969 | +¥0.1373 |

V2 新增的可审计行为：9 次循环检测、10 次 Recovery 触发、3 次救回、0 次已记录
误触发、23 次按需 UI Tree 请求。`0 次误触发` 只代表当前判定规则下没有观察到，
不代表恢复策略不存在副作用。

逐题变化：

- V1 失败、V2 成功：`SystemBluetoothTurnOn`、`SystemWifiTurnOff`、
  `MarkorCreateFolder`、`SimpleSmsReply`、`SimpleSmsResend`、
  `SimpleSmsSendClipboardContent`。
- V1 成功、V2 失败：`TurnOnWifiAndOpenApp`。
- 两版都成功：`ClockStopWatchPausedVerify`、`ContactsNewContactDraft`、
  `ExpenseDeleteSingle`。
- 其余 10 题两版都失败。

## 三条真实 Recovery 救回

| 任务 | 失败信号 | Recovery 后变化 | 官方判定 |
| --- | --- | --- | --- |
| `SystemBluetoothTurnOn` | 重复相似动作形成循环 | 请求 Tree，改变动作路线 | reward = 1 |
| `SystemWifiTurnOff` | 重复 `SWIPE down` | 请求 Tree，改为不同动作 | reward = 1 |
| `MarkorCreateFolder` | 重复 `SWIPE up` | 请求 Tree，离开重复滚动路线 | reward = 1 |

每条 Trace 都含 `agent_recovery_triggered`、后续动作、逐步 `official_reward` 和
`agent_recovery_outcome(rescued=true)`。这里的“救回”由 Runtime 事件链和官方
reward 共同认定，不依赖模型自报完成。

## 仍然失败在哪里

V2 的 11 条失败终止包括：

- 7 次 `invalid_actor_output`；
- 2 次 `unsafe_repeated_action_after_recovery`；
- 1 次 `recovery_exhausted`；
- 1 次 `step_budget_exhausted`。

Calendar 多字段任务和 Markor 编辑任务仍是主要困难。Recovery 能阻止部分无意义
重复，但一次轻量 replan 还不足以稳定完成需要长程记忆和多字段核对的任务。

## 如何解释这次提升

不能把全部增益都写成“推理能力提升”。V2 同时包含三类作用：

1. Protocol Guard 减少机械格式问题导致的直接退出；这是协议可靠性，不是推理。
2. 官方 reward 每步检查避免模型漏报或误报完成；这是评测与终止控制。
3. 循环检测、短期状态、按需 Tree 和一次有限 replan 带来了 3 条可验证救回；
   这部分才是 Agent Runtime 的恢复能力证据。

下一步在全新 12 题上冻结 V1/V2 配对评测。冻结后不再根据结果调整 Prompt 或策略，
用于检验这套改进是否能迁移到未参与开发的任务。
