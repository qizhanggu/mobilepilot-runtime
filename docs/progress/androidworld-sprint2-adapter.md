# AndroidWorld Sprint 2 Adapter 进度

日期：2026-07-27
状态：**Adapter 基础桥接已真实验证；多步 Actor Loop 尚未完成。**

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
- 目前尚未接入会根据完整目标、历史、Verifier和剩余步数连续决策的多步 Actor；下一步实现
  该 Loop 与结构化多动作Prompt，再以 `OpenAppTaskEval`、`ClockStopWatchRunning`、
  `SystemWifiTurnOnVerify` 三题作为开发冒烟集。
- 本文件不报告成功率，也不把这一条Adapter smoke描述为AndroidWorld成绩。
