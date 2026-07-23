# Phase 1：设备 Adapter 与测试环境选择

日期：2026-07-20 至 2026-07-21

## 1. 新增的真实能力

- `ADBDeviceAdapter` 可绑定明确 serial，读取设备状态、机型、分辨率、前台 Activity 和内存截图；`FakeDeviceAdapter` 可在不连接手机时复现这些观察结果。
- 已选择并构建安装 `MobilePilot Lab`：它完全本地运行，没有登录、网络、相机或真实订单，可反复作为 Agent 验收环境。

## 2. 关键模块与接口

- `mobile_pilot/device/base.py`：统一 `DeviceAdapter` 抽象；
- `mobile_pilot/device/adb.py`：显式附带 `-s <serial>` 的 ADB 实现；
- `mobile_pilot/device/fake.py`：离线测试替身；
- `mobilepilot_lab/`：原生 Android 测试 App，提供稳定 `resource-id`、搜索、弹窗和确认页。

## 3. 测试与实际结果

- Phase 1 完成时，`python -m pytest -q`：18 passed；其中设备解析与 Fake 观察均不依赖真机。后续 Phase 2 新增的点击测试计入其独立报告。
- `MobilePilot Lab` 已由 Gradle 8.7 / AGP 8.5.2 成功构建，并安装为包 `com.mobilepilot.lab`。

## 4. 真机验证

- 已授权测试设备：vivo V2352A，Android 16，物理分辨率 1260×2800；公开文档不保存真实 serial；
- ADB `get-state` 返回 `device`，截图和当前 Activity 读取成功；
- 测试 App 已安装并可启动。后续真实点击不属于本阶段的只读目标，已在 Phase 2 以单独记录验证。

## 5. Trace / 评测产物

- 本报告记录设备、包名、构建和验证证据；正式 JSONL Trace 仍属于 Phase 3。

## 6. 当前可运行 Demo

- 可构建并安装 `mobilepilot_lab`，并通过 `ADBDeviceAdapter.observe()` 读取真实手机截图和元数据；
- 可不接手机运行全部离线测试。

## 7. 已知问题、技术债与风险

- vivo Android 16 上 `uiautomator dump /dev/tty` 只返回提示，不直接回传 XML；
- 原用户的旧扫码 App 没有可维护源代码且依赖相机/二维码，不适合作为核心评测环境；
- 不允许根据“默认设备”执行动作，所有真机命令必须绑定 serial。

## 8. 相对原离线原型的真实增量

原项目只能离线消费截图和参考状态图；现在项目已能识别一台明确授权的 Android 真机，并拥有可控、可重置的测试 App。

## 9. 下一阶段

进入 Phase 2：解决 UI Tree 获取兼容性，建立 UI Tree 优先、视觉降级的语义定位链路，并做最小真实点击闭环。
