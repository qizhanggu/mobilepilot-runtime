# Phase 2：混合感知与策略 Adapter

日期：2026-07-21

## 1. 新增的真实能力

- 真实 UI XML 被解析为带 `resource-id`、文本、描述、边界和可点击状态的 `ScreenState`；
- `Grounder` 优先使用 UI Tree 的稳定语义元素，`HybridGrounder` 仅在语义目标缺失时调用视觉 fallback；
- `LegacyVisionPolicy` 将旧视觉 Agent 输出转为新协议，视觉坐标在 policy 层由 `[0,1000]` 严格换算为当前截图像素；
- ADB 可对已批准的像素点执行 tap，并返回结构化 `ActionResult`。

## 2. 关键模块与接口

- `mobile_pilot/perception/ui_tree.py`、`screen_state.py`：XML 解析、元素边界与屏幕指纹；
- `mobile_pilot/policy/grounding.py`：语义元素定位；
- `mobile_pilot/policy/hybrid.py`：UI Tree → LegacyVisionPolicy 的两级 fallback；
- `mobile_pilot/policy/legacy_vision.py`：旧 Agent 兼容层；
- `mobile_pilot/device/adb.py`：临时 UI XML 回退与受控 tap。

## 3. 测试与实际结果

- `python -m pytest -q`：28 passed；
- 覆盖 XML 解析、语义匹配优先级、显式视觉点、旧策略错误传播、视觉 fallback 调用时机、归一化坐标换算、越界拒绝及 Fake tap；
- `git diff --check` 通过。

## 4. 真机验证

设备为已显式指定 serial 的授权测试机，测试 App 为 `com.mobilepilot.lab`。

1. 成功读取真实截图、Activity 和 8 个首页语义元素；
2. 按 `com.mobilepilot.lab:id/debug_dialog_button` 的 UI Tree 定位，执行“显示测试弹窗”；
3. 读取到弹窗与 `android:id/button1`（“关闭”）；按该稳定 ID 定位并点击；
4. 点击前后屏幕指纹变化，重新读取到首页的 `debug_dialog_button`，验证页面恢复。

最后一次关闭动作的记录：`source=UI_TREE`、`point=(1018,1657)`、`confidence=0.99`、`executed=true`、`home_restored=true`。没有输入文字、没有点击“模拟提交”，没有操作其他 App。

## 5. Trace / 评测产物

- 本报告保存了真机动作范围、定位来源、像素点、状态指纹与结果；
- 正式 JSONL Trace 和可批量运行的评测集仍属于 Phase 3/6，尚未实现。

## 6. 当前可运行 Demo

可在本地运行离线测试；连接已授权真机后，可通过 ADB Adapter 完成“观察首页 → 按 UI Tree 打开测试弹窗 → 重读 → 按 UI Tree 关闭 → 重读验证”的受控闭环。

## 7. 已知问题、技术债与风险

- 真实 VLM API 尚未接入：视觉 fallback 的接口和坐标安全转换已测，但没有真实模型成功率数据；
- 没有 Task Runtime、Pre-action Critic、Verifier、重试/恢复或统一 SafetyGate，不能接受自然语言任务后自主执行；
- 曾观察到界面状态与预期不一致时，语义目标会在新 UI Tree 中缺失而被拒绝；这说明每次动作前必须以新状态重新定位，不能复用旧坐标；
- ADB 临时 XML 删除已在本次设备上检查无残留，但异常退出场景还需在后续设备测试中持续覆盖。

## 8. 相对原离线原型的真实增量

原型只有“截图 → 旧模型坐标”的离线决策；现在已有真实 Android 的 UI Tree 语义定位、受控 ADB 执行、动作后观察验证，以及不破坏旧模型接口的视觉降级通道。

## 9. 下一阶段

进入 Phase 3：建立任务状态机、轻量 Pre-action Critic、执行后 Verifier、有限恢复和 JSONL Trace，才能把单步证明升级为可解释的端到端任务闭环。
