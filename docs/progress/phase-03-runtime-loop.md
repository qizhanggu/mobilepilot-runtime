# Phase 3：可验证任务闭环、Critic、Verifier 与 Recovery

日期：2026-07-22

## 1. 新增的真实能力

- 接受一条受控自然语言任务：“在 MobilePilot Lab 搜索 coffee，筛选评分 4.5 以上，进入确认页并停下，不要提交。”；
- 将任务编译为 5 个可验证步骤，每步执行 `observe → ground → critic → act → verify`，不会复用上一页面的旧坐标；
- 动作和判断逐事件写入 JSONL Trace，并默认清理常见 API key、token、password、secret 和 authorization 字段；
- 接入 GUI-Plus 作为真实视觉候选策略，完成一次 UI Tree 不可见 Canvas 控件的视觉定位与点击验证；
- 增加 ASCII 文本输入，并用真机证据触发 ADB / `uiautomator2` 重评估门。

这仍是面向 `MobilePilot Lab` 的受控基准 Runtime，不是可泛化到任意 App 的通用自然语言 Planner。

## 2. 架构和关键代码变化

- `mobile_pilot/policy/gui_plus.py`：截图转 data URL、调用 GUI-Plus、兼容其实际输出并生成视觉候选点；模型只提议动作，不直接控制设备；
- `mobile_pilot/runtime/lab_task.py`：受控任务编译与五步纵向闭环；
- `mobile_pilot/runtime/critic.py`：执行前检查越界，以及视觉候选是否错误覆盖当前可点击语义元素；
- `mobile_pilot/runtime/verifier.py`：有限次数重读页面，避免单次陈旧 UI dump 造成假失败；
- `mobile_pilot/runtime/recovery.py`：为视觉策略构造更小且可审查的 viewport，再将局部坐标映射回物理屏幕；
- `mobile_pilot/tracing/jsonl.py`：带 run id、UTC 时间和递归脱敏的 JSONL Trace；
- `DeviceAdapter.type_text`：统一文本输入边界，ADB 与 Fake Adapter 均实现。

## 3. Critic、Verifier、Recovery 的真实作用

| 组件 | 真机上真实发生的问题 | 实际处理结果 |
| --- | --- | --- |
| Pre-action Critic | GUI-Plus 第一次在整屏预测 `(636,932)`，与 UI Tree 中的搜索按钮重叠，不是目标 Canvas 控件 | 点击前拒绝，错误动作未执行 |
| Recovery | 目标位于 UI Tree 不可访问的 Canvas；整屏视觉预测受上方控件干扰 | 截取语义调试按钮以下的视觉 viewport，GUI-Plus 重新定位到物理坐标 `(630,1335)` |
| Verifier | 视觉点击后第一次 UI dump 过早，误判成功弹窗未出现 | 改为有限轮询后读取到“视觉定位验证成功”，纠正假失败并成功关闭弹窗 |

因此已经能宣称“真实 UI Tree 主路径 + 真实 VLM fallback 在受控控件上跑通”，但不能据此宣称任意 App 的混合感知成功率。

## 4. 测试与真机结果

- `python -m pytest -q`：49 passed；
- `git diff --check`：通过；
- 真实 VLM fallback：1 次错误整屏候选被 Critic 拦截，1 次裁剪恢复后点击成功并验证弹窗；
- 同一自然语言任务连续运行 3 次，成功 3 次，均完成 5/5 步并停在提交前；
- Trace 内端到端耗时分别为 56.96 秒、56.66 秒、56.17 秒，平均约 56.60 秒；
- 最终 UI Tree 仍存在 `submit_action_button`，三条 Trace 均无该按钮的点击动作。
- `Uiautomator2DeviceAdapter` 对照同样完成三次 5/5，平均约 16.74 秒；该结果仍只表示同任务重复运行稳定性。

## 5. 一条完整 Demo Trace

代表性文件：`artifacts/traces/phase3-lab-run-01.jsonl`，共 30 条事件。

事件主线：

```text
task_started
→ focus_search: observation / critic / click / step_completed
→ type_keyword: observation / type coffee / verification / step_completed
→ run_search: observation / critic / click / verification / step_completed
→ apply_filter: observation / critic / click / verification / step_completed
→ open_confirmation: observation / critic / click / verification / step_completed
→ task_finished(success=true, completed_steps=5/5)
```

另外两条重复运行 Trace 为 `phase3-lab-run-02.jsonl` 和 `phase3-lab-run-03.jsonl`。原始文件包含本机设备 serial，公开仓库提交前应生成脱敏副本或将设备标识替换为匿名 ID。

## 6. 已知失败案例与技术债

1. 直接整屏视觉定位曾给出错误候选，说明 VLM 输出不能绕过 Critic；
2. 单次动作后读取曾造成假失败，说明页面等待必须采用有界轮询；
3. ADB 输入中文仍失败；已验证 `Uiautomator2DeviceAdapter` 可以输入并读回 `咖啡`，因此运行时需要保留两种设备通道；
4. uiautomator2 将同一 5 步任务从 ADB 平均约 56.60 秒降至约 16.74 秒，但仍需通过视觉主链路减少不必要观察与模型调用；
5. 当前 Planner 是受控任务编译器，尚无任意目标拆解、checkpoint 回退、循环检测或通用局部重规划；
6. Recovery 已真实修复视觉 fallback，但尚未形成覆盖所有 Runtime 失败类型的完整恢复阶梯。

## 7. 当前可运行程度

连接已授权真机并启动 `com.mobilepilot.lab` 后，当前代码能够真实完成一条 ASCII 搜索、筛选、进入确认页并停止的多步任务，且有逐步 Trace 证明。它可以作为面试 Demo 的第一条纵向闭环，但暂时不能包装成“通用手机 Agent”。

## 8. 下一阶段

设备 A/B 已完成。停止继续扩建底层基础设施，转向视觉主链路和受控视觉任务集：比较原图、网格、粗到细裁剪与 UI Tree 辅助检查，并统一记录成功率、错误点击率、调用次数、延迟和 Token。当前三次任务结果只作为重复运行稳定性证据。
