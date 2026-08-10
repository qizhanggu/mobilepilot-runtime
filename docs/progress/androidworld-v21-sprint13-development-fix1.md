# AndroidWorld Sprint 13：V2.1 协议兼容修复后的开发回归

日期：2026-08-05

状态：**同一组已暴露 20 题上，V2.1 从 2/20 提升到 5/20，但仍低于既有 V2 的 9/20。**

## 本轮改了什么

- 缩短 V2.1 Actor Prompt；direct 模式不再暴露检查点完成动作；
- 将 Planner 的 `direct + checkpoints` 归一化为 checklist，而不是丢弃整份计划；
- 兼容无歧义 evidence 类型，并在计划恢复时复用同目标的冻结证据；
- direct 模式下误提检查点完成时，允许一次无动作的安全纠正；
- V2.1 的 Protocol Guard 改为每个未执行动作的决策点最多安全重试一次；V2 保持冻结行为不变；
- package/activity 证据允许用稳定 App 名后缀匹配，仍不把 Actor 自报当作完成证据。

代码修改后，AndroidWorld 相关完整单元测试为 **131/131 通过**。

## 公平条件

- 任务：`configs/androidworld/held_out_20.json`，已暴露，只作为开发回归集；
- 模型：`gui-plus-2026-02-26`；
- AndroidWorld commit：`3e50888527ef9f29b9157ecd537e408008bb1c85`；
- mode / seed / 动作上限：`hybrid` / `0` / `12`；
- 设备：仅 `emulator-5554`；
- 不为单题重试，不在运行中调 Prompt 或策略；
- 新产物：`artifacts/evaluation/androidworld-v21-development-20260805/regression-20-step12-fix1/`。

## 三版开发结果

| 指标 | V2 | V2.1 首轮 | V2.1 修复后 |
| --- | ---: | ---: | ---: |
| 官方成功 | 9/20 | 2/20 | 5/20 |
| 非法输出终止 | 7 | 11 | 6 |
| 步数耗尽 | 1 | 0 | 3 |
| Recovery 触发 / 救回 | 10 / 3 | 12 / 0 | 16 / 1 |
| 执行动作 | 112 | 53 | 116 |
| VLM 调用 | 144 | 116 | 182 |
| Token | 493,719 | 382,727 | 642,276 |
| 目录价成本 | ¥0.7969 | ¥0.6059 | ¥1.0298 |

修复后成功任务为：

- `SystemBluetoothTurnOn`
- `SystemWifiTurnOff`
- `ClockStopWatchPausedVerify`
- `SimpleSmsReply`
- `SimpleSmsResend`

它们都是 V2 已经成功过的任务。V2.1 本轮没有新增 V2 从未成功的任务，并退化了
`ContactsNewContactDraft`、`MarkorCreateFolder`、`SimpleSmsSendClipboardContent`、
`ExpenseDeleteSingle` 四题。因此，不能把 2/20→5/20 写成相对 V2 的能力提升。

## 修复真正改善了什么

本轮 Protocol Guard 触发 17 次，其中 11 次在未执行设备动作前取得了合法动作；非法输出终止
由首轮 11 次降到 6 次。说明兼容修复有效降低了协议层误杀，但这是输出可靠性工程，不是通用
推理能力提升。

代价是 Agent 存活更久：动作、Planner/Actor 调用、Token 和成本均上升。成功率仍低于 V2，
说明 Planner 和两层 Recovery 目前增加了运行负担，却没有稳定增强页面理解和正确任务推进。

## 真实 Recovery 救回 Trace

`SimpleSmsReply` 出现了本项目 V2.1 的第一条可审计救回链路：

1. 第 2 步检测到连续两次页面无进展；
2. Runtime 触发 action-level Recovery，并按需请求 UI Tree；
3. Actor 选择与受阻动作不同的动作，Runtime 记录 `changed_action=true`；
4. 后续继续执行，直到第 9 步 AndroidWorld official reward 变为 1；
5. Trace 记录 `recovery_rescue_count=1`。

证据：`artifacts/evaluation/androidworld-v21-development-20260805/regression-20-step12-fix1/traces/SimpleSmsReply--v2.1--hybrid.jsonl`。

需要如实说明：该任务在既有 V2 中也成功，因此这条 Trace 证明 Recovery 发生了真实行为并与最终
成功形成链路，但不能单独证明 V2.1 比 V2 更强。

## 失败分类与结论

15 个失败任务的终止原因：

- 非法 Actor 输出：6；
- 无进展后 Recovery 耗尽：3；
- 12 步耗尽：3；
- 模型过早提议完成、官方 reward 拒绝：3。

两道官方参考路径超过 12 步的日历任务均在 12 步耗尽，说明最终新冻结配对评测应让 V1 和
V2.1 统一使用 18 步；但当前更大的问题仍是空输出、错误导航和过早完成。

结论：本轮最小修复有效改善协议可靠性并首次产生可审计的 V2.1 Recovery 救回案例，但没有证明
Planner/Checklist 带来任务能力提升。现阶段不应直接跑新的冻结集，也不应把 5/20 写进简历正向
成绩。下一步应先减少 Planner 对简单任务的干扰，并让计划只在多约束、跨页面任务中启用，再做
一次小规模开发验证；只有明显接近或超过 V2 的 9/20，才值得进入更大的未见任务配对评测。
