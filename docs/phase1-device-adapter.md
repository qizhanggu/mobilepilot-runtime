# Phase 1：设备 Adapter 与测试环境选择

## 当前目标

将真实 Android 的观察能力从命令行脚本封装为 `DeviceAdapter`，并保持同一接口可由 `FakeDeviceAdapter` 在不连接手机时复现。Phase 1 的 Adapter 只提供读取设备信息和内存截图的能力，不实现点击、输入、启动 App 或修改系统设置。

## 已知真机信息

- serial：`10CE8Q0P8U000B1`；
- 型号：vivo V2352A，Android 16；
- 屏幕物理分辨率：1260×2800；
- 当前 USB 调试已授权。

## UI Tree 兼容性发现

该 vivo Android 16 设备执行 `uiautomator dump /dev/tty` 后只返回“已写入 /dev/tty”的提示，不把 XML 回传至 ADB stdout。因此 Phase 1 的 Adapter 会显式报告 `ui_tree_error`，不把它伪装成空 UI。

Phase 2 将比较两种实现：

1. 在设备临时目录生成 XML、读取后立即清理；此方案会产生短暂文件，执行前需用户明确同意；
2. 增加可选的 `uiautomator2` Adapter。

最终选择以元素定位、输入稳定性、等待能力和维护成本的真实验证为准。

## 测试 App 决策

不使用用户旧扫码 App 作为核心测试环境：它缺少源码、依赖相机/权限/二维码，不能可靠初始化、重置或注入故障。

已创建 `mobilepilot_lab/` 下的 `MobilePilot Lab`，一个无后端、无登录、无隐私数据的本地 Android 测试 App。首版包含：

- 首页与明确的 resource-id；
- 搜索输入框、结果列表和评分筛选；
- 一个可控弹窗；
- 一个“提交前确认”页面；
- 可由启动参数或页面按钮重置到初始状态。

它的目标是评估 Agent Runtime，而不是展示 Android 客户端开发能力。

## 本地构建证据

- package：`com.mobilepilot.lab`；
- SDK：compileSdk 34，minSdk 26，targetSdk 34；
- 构建命令：Gradle 8.7 + Android Gradle Plugin 8.5.2 的 `assembleDebug`；
- 实际结果：2026-07-20 构建成功，32 个 Gradle task 执行完成；
- 产物：`mobilepilot_lab/app/build/outputs/apk/debug/app-debug.apk`。

APK 尚未安装到真机。安装和后续启动前，仍需用户针对 serial `10CE8Q0P8U000B1`、目标 package `com.mobilepilot.lab` 和“安装 debug 测试 App”这一动作给出明确确认。
