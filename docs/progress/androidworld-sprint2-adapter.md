# AndroidWorld Sprint 2 Adapter 进度

日期：2026-07-27
状态：**多步 Actor / Agent Loop 已接入；首条模型驱动任务待运行。**

## 本次完成

- 新增 `mobile_pilot.androidworld.AndroidWorldAdapter`，不改写既有真机 Runtime。
- `observe(include_ui_tree=False)` 只向 MobilePilot 暴露截图；`True` 时才转换
  AndroidWorld Accessibility 元素，保留 `vision_only` 与混合感知的边界。
- 已映射通用动作：坐标点击、文本输入、滑动、滚动、返回、打开App、等待和
  `PROPOSE_COMPLETE`。
- `PROPOSE_COMPLETE` 只映射为 `done` 信号，绝不映射为本地 `SUCCEEDED`；调用方必须以
  AndroidWorld `task.is_successful(env)` 的官方 reward 判定最终成功。

## 真机替代环境的真实烟测

在 `ClockStopWatchRunning` 的官方模拟器任务中，Adapter 已完成：

```text
goal = Run the stopwatch.
image_size = 1080 x 2400
ui_elements = 19
action = WAIT
action_executed = true
official_reward_before = 0.0
official_reward_after = 0.0
```

这是一条环境和Adapter闭环证据，不是任务成功：`WAIT` 并没有完成秒表任务，所以官方reward
保持 `0.0`。选择它是为了验证通用映射而不对该任务硬编码“点击开始”。

## 已知约束与下一步

- AndroidWorld首次获取 Accessibility Tree 仍可能出现一次 retry；Trace 与评测中将记录它，
  不能将其吞掉。
- 新增独立的 `mobile_pilot.androidworld.AndroidWorldGuiPlusPolicy`，支持 `CLICK`、`TYPE`、
  `SWIPE`、`BACK`、`OPEN_APP`、`WAIT` 与 `PROPOSE_COMPLETE`。它与冻结的 ScreenSpot 单点
  Prompt 完全分离，不能影响已发布的 ScreenSpot 结果。
- `MobilePilotAndroidWorldAgent` 每一步都输入完整目标、截图、最近动作、Verifier、失败信息与
  剩余步数；仅 Hybrid 模式传入 UI Tree。它复用 JSONL Trace，并记录原始模型响应、解析、
  Critic、执行、页面变化 Verifier 与一次通用等待恢复。
- 当前 Critic 只做坐标边界安全检查；当前 Verifier 只记录页面指纹是否变化；两者都不是成功
  判定，最终仍必须由 `task.is_successful(env)` 的官方 reward 决定。
- 下一步先运行 `ClockStopWatchRunning`，随后才以 `OpenAppTaskEval`、
  `SystemWifiTurnOnVerify` 组成前三题开发冒烟集。
- 本文件不报告成功率，也不把这一条Adapter smoke描述为AndroidWorld成绩。

## 首条模型驱动任务（开发证据，不是评测结论）

在相同的 `ClockStopWatchRunning`、seed=0、最多 6 步和 GUI-Plus snapshot 配置下：

- `vision_only` 首次运行：模型连续两次上滑后第三次返回空内容；解析器终止运行，官方 reward
  为 `0.0`。这条失败 Trace 保留在本地，不以成功覆盖。
- `hybrid` 首次运行：模型在第二步产生 `OPEN_APP: The Clock`。AndroidWorld 只接受官方 app
  key（`clock`），旧 Adapter 把展示名当 package 执行而触发 ADB 异常。该机械兼容问题保留了
  Trace 后修复：通用地移除英文冠词并将执行异常转成结构化失败，不引入任何任务动作序列。
- `hybrid` 修复后重跑：模型输出 `OPEN_APP Clock`、两次 `CLICK`，外层 Runner 在第 3 步检测到
  官方 reward=`1.0` 并停止（Agent 本身仍不会把页面变化或 `PROPOSE_COMPLETE` 当成功）。三次
  模型调用合计 11,638 tokens，目录价估算约 ¥0.0183，端到端 43.062 秒。

这些都是开发集单次证据，不是成功率，也不能用于声称纯视觉和混合感知的性能差异。
