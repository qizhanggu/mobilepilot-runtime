# AndroidWorld Sprint 1 环境记录（阻塞于 Windows Hypervisor）

日期：2026-07-27
基线：`827632c474c4315a3e44bb26c05842c8fd3d6119`
状态：**Sprint 1 环境已跑通；保留 Windows 兼容性偏差与复现命令。**

## 2026-07-27 完成更新

- 重启后已确认 `WHPX(10.0.19045) is installed and usable`；模拟器在约 78 秒内完成冷启动。
- `emulator-5554` 已真实在线，`sys.boot_completed=1`，Android API 为 `33`；模拟器日志确认
  gRPC server 已在 `8554` 启动。
- 上游 `minimal_task_runner.py` 已经成功完成环境、Accessibility Forwarder 和
  `ClockStopWatchRunning` 任务初始化；随后仅因其硬编码的 OpenAI GPT-4 默认 Agent 没有
  `OPENAI_API_KEY` 而停止。该停止不被计为环境失败。
- 项目侧 `scripts/androidworld_official_smoke.py` 使用 AndroidWorld 内置 `RandomAgent`
  完成一轮真实交互：目标 `Run the stopwatch.`、截图尺寸 `2400x1080x3`、UI 元素数 `6`、
  官方 reward 前后均为 `0.0`。随机 Agent 未完成任务是预期结果；它证明动作、状态和
  官方 reward 通路均可调用。

## 已完成

- AndroidWorld 官方仓库已克隆到本机忽略目录 `.local/android_world`，固定提交：
  `3e50888527ef9f29b9157ecd537e408008bb1c85`。
- 已建立隔离环境 `.local/conda/androidworld`：Python `3.11.8`；官方
  `requirements.txt` 和 editable `android_world` 均安装并通过导入检查。
- 已确认本机有 Android SDK、ADB、ffmpeg 和可用的硬件加速层。
- 因现有 SDK 缺少命令行工具，补充安装官方 command-line tools；仅在当前安装进程中使用
  Android Studio 内置 JBR `D:\Program Files\Android\Android Studio\jbr`，未修改系统
  `JAVA_HOME` 或 PATH。
- 已安装 Android 13 / API 33 `google_apis;x86_64` 系统镜像，创建官方要求的
  `AndroidWorldAvd`：Google Pixel 6、API 33、x86_64。
- 已按官方要求尝试以
  `emulator -avd AndroidWorldAvd -no-snapshot -grpc 8554 -no-boot-anim`
  启动；没有连接任何用户真机。

## 阻塞证据

新版本 Android Emulator (`36.6.11.0`) 在启动日志中明确退出：

```text
FATAL | Your current hypervisor HAXM is no longer supported by the Android Emulator.
Using WHPX is recommended.
```

本机已确认旧驱动 `intelhaxm` 正在运行。模拟器因此没有注册为 `emulator-5554`，
`sys.boot_completed` 在 6 分钟内无法变为 `1`，所以 gRPC / 官方 runner 尚未有机会运行。

对 WHPX、Virtual Machine Platform、Hyper-V 的只读 DISM 查询也被当前受限会话拒绝
（`Error 740: Elevated permissions are required`）；该查询没有改变系统状态。

## 下一步（需要用户确认）

需要在 Windows "启用或关闭 Windows 功能" 中启用 **Windows Hypervisor Platform (WHPX)**
（必要时同时启用 Virtual Machine Platform），并按 Windows 提示重启。重启后应停止/禁用旧
HAXM，让 Android Emulator 使用 WHPX；然后重新执行本记录中的启动命令，再运行官方
`minimal_task_runner.py`。

在此之前：

- MobilePilot AndroidWorld Adapter 未开始实现；
- 官方任务、官方 reward、10 题开发集和 20 题 held-out 均未运行；
- 现有 ScreenSpot-v2 产物和真机链路未改动。

## 已解决的 Windows 兼容性与当前约束

- 旧 HAXM 已由 WHPX 取代；这一项曾要求手动重启，但目前已解决。
- 上游最小 Runner 在 Windows 上会在解析 `--adb_path` 前查找无 `.exe` 后缀的 Unix ADB
  路径。项目侧 `scripts/run_androidworld_official_minimal.py` 只桥接这一个导入时检查，
  不修改固定的 AndroidWorld 源码，实际执行仍传入真实 `adb.exe`。
- `android_env==1.2.3` 在 Python 3.11 的 Windows 临时文件语义下无法把下载的 APK 交给
  ADB。最终运行环境改为独立 Python `3.12.13`，触发该库的 Windows 兼容分支；官方固定的
  `matplotlib==3.6.1` 没有 Python 3.12 Windows 轮子，因此替换为 `matplotlib==3.10.9`。
  AndroidWorld、`android_env` 和其余官方依赖版本保持不变。
- 首次获取 UI Tree 时可见一次 a11y retry，以及系统 Clock 没有快照文件的提示；任务仍可
  初始化、观测、执行动作并返回官方 reward。后续 Adapter Trace 会单独记录这些事件，不能
  将其静默视为成功。

## 下一步

环境验收已完成，进入 Sprint 2：实现 MobilePilot AndroidWorld Adapter，并以
`ClockStopWatchRunning` 跑通第一条 MobilePilot Agent 任务。无需连接真机。
