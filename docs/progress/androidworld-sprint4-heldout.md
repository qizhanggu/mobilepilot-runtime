# AndroidWorld Sprint 4：20题 Held-out 结果

日期：2026-07-31  
状态：**完成固定20题子集的40条正式运行；不是AndroidWorld完整116类成绩。**

## 冻结条件

- AndroidWorld commit：`3e50888527ef9f29b9157ecd537e408008bb1c85`；
- 模型：`gui-plus-2026-02-26`；seed=0；每题最多12个真实动作步；
- 清单：[configs/androidworld/held_out_20.json](../../configs/androidworld/held_out_20.json)，与10条开发任务零重叠；
- 比较 `vision_only` 与 `hybrid`；每个 `(task_id, mode)` 仅一次，AndroidWorld 官方 reward 是唯一成功判定。

## 结果

| 指标 | vision_only | hybrid |
| --- | ---: | ---: |
| 官方成功数 / 20 | 5 / 20（25%） | 4 / 20（20%） |
| 平均已执行动作步 | 6.30 | 4.05 |
| VLM 调用数 | 140 | 94 |
| 总 Token | 412,430 | 421,748 |
| 模型延迟（每题均值） | 24.68 s | 15.35 s |
| 估算目录价 | ¥0.6609 | ¥0.6596 |
| 非法模型输出数 | 9 | 13 |
| 有 UI Tree 的观察次数 | 0 | 94 |
| Critic 拦截 / Recovery 触发 | 0 / 0 | 0 / 0 |

配对结果：两者都成功2题、仅纯视觉成功3题、仅混合成功2题、都失败13题。以不一致配对 `3 vs 2` 做双侧 exact McNemar 检验，`p=1.0`；在此固定20题子集上，不能声称混合感知优于纯视觉。

## 成功与失败

- 纯视觉成功：`SystemBluetoothTurnOn`、`TurnOnWifiAndOpenApp`、`ClockStopWatchPausedVerify`、`MarkorCreateFolder`、`SimpleSmsResend`。
- 混合成功：`TurnOnWifiAndOpenApp`、`ClockStopWatchPausedVerify`、`ContactsNewContactDraft`、`ExpenseDeleteSingle`。
- 主要失败不是AndroidWorld环境故障：40条均有终态，0条 infrastructure error。长表单/笔记/日历任务常耗尽步数；模型协议非法输出是另一主要失败源，混合模式本轮有13次、纯视觉9次。
- Critic和Recovery在这批正式运行中没有实际拦截或修复事件，说明当前实现主要完成了可观测性与安全边界，尚未形成对复杂多步失败的有效恢复能力。

## 真实性边界与产物

原始逐任务记录、完整 Prompt/动作响应、官方reward和指标保存在本地 `artifacts/evaluation/androidworld-held-out-20260731/`（不提交Git，防止将大体积含任务数据的运行产物混入源码）。该目录含 `runs.jsonl`、`summary.json`、`preflight.json` 和40份 JSONL Trace。

结论只适用于该模型、该预算、该20题子集和当前实现版本。不能把5/20或4/20写成AndroidWorld总体成绩，也不能把模型能力全部归因于MobilePilot。
