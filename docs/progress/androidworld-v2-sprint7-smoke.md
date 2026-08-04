# AndroidWorld Sprint 7：V2 真实冒烟与评测门禁

日期：2026-08-04

状态：**开发冒烟完成；旧 20 题仍是开发集，新 12 题尚未选择或查看结果。**

## 环境门禁

- ADB 设备列表中只有 `emulator-5554`；未连接或操作真实手机。
- 模拟器为 Android API 33；AndroidWorld commit 为
  `3e50888527ef9f29b9157ecd537e408008bb1c85`。
- 模型保持 `gui-plus-2026-02-26`。
- 新评测 Runner 会在任何任务前再次检查：唯一设备、commit、模型、任务 hash、源码 hash、调用预算和成本上限。

## 冒烟过程与真实结论

开发任务：`ClockStopWatchRunning`，`hybrid`，V2，最多 6 个真实动作。

| Trace | 结果 | 发现 |
| --- | --- | --- |
| `ClockStopWatchRunning--v2-hybrid.jsonl` | 基础设施失败 | 受限执行环境阻断网络；未取得 Token、未产生目录价、未执行动作 |
| `...--network-retry1.jsonl` | 失败 | GUI-Plus 返回明确的原生 `SYSTEM_FUNCTION(open_app)`；重试为空响应 |
| `...--protocol-alias.jsonl` | 失败 | Agent 检测三次 `SWIPE up` 循环并触发一次 Recovery；模型仍重复相同动作，未救回 |
| `...--recovery-guidance.jsonl` | 官方成功 | `OPEN_APP clock → CLICK Stopwatch → CLICK Start`，3 个动作后官方 reward=1 |

前三条失败 Trace 均保留，没有覆盖或删除。最后一条成功没有触发 Recovery，因此只能证明正常 V2 闭环可运行，**不能**包装成恢复救回案例。

## 根据真实 Trace 做出的两项通用修正

1. 将 GUI-Plus 明确的 `SYSTEM_FUNCTION(function_name=open_app, app_name=...)`
   归一化为 `OPEN_APP`。这是无歧义 Protocol Guard，不是 Agent 推理。
2. Recovery Prompt 明确写入被阻止的动作，并要求改变动作类型；当重复导航形成循环时，通用提示优先考虑直接 `OPEN_APP`。若模型仍重复原动作，Runtime 在执行前停止。

## 成本

三条实际联网冒烟的累计估算目录价约 **¥0.0498**。基础设施失败 Trace 的 Token 和费用均为 0。该成本计入本轮 ¥15 硬上限。

## 评测 Runner

新增独立 Runtime 评测 Runner，职责包括：

- 显式区分 `development` 与 `frozen_evaluation`；
- V1/V2、任务、mode 构成唯一运行键，禁止覆盖或重复；
- 基础设施失败后暂停，不自动重试单题；
- 统计官方成功、非法终止、步数耗尽、循环、Recovery、UI Tree、动作数、VLM 调用、Token、延迟和费用；
- 冻结评测强制检查源码 hash 和干净的 tracked workspace。

当前完整离线测试：`124 passed`。下一步先提交并冻结这套代码，再运行已暴露 20 题的 V2 开发回归。
