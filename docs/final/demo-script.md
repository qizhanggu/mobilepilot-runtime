# 可复现 Demo 与三分钟讲解脚本

## 运行边界

本轮 Demo 只允许 `emulator-5554`，不连接或操作真实手机。AndroidWorld 固定 commit
`3e50888527ef9f29b9157ecd537e408008bb1c85`，模型固定
`gui-plus-2026-02-26`。

## 启动模拟器

AndroidWorld 除 ADB 端口外还需要 gRPC 端口。遗漏 `-grpc 8554` 会出现“ADB 在线但
环境初始化一直不返回”的假象。

```powershell
$emulator='C:\Users\Admin\AppData\Local\Android\Sdk\emulator\emulator.exe'
Start-Process -FilePath $emulator -ArgumentList @(
  '-avd','AndroidWorldAvd',
  '-port','5554',
  '-grpc','8554',
  '-no-snapshot-save'
)
```

确认 `adb devices -l` 中只有 `emulator-5554` 后再运行：

```powershell
$env:MOBILEPILOT_ACTOR_MODEL='gui-plus-2026-02-26'
$env:MOBILEPILOT_ANDROIDWORLD_DOWNLOAD_CACHE=(Resolve-Path '.local\androidworld-download-cache').Path

# 离线测试
.\.local\conda\androidworld-py312\python.exe -m pytest

# 已暴露开发任务 Demo；不要把结果写成新评测
.\.local\conda\androidworld-py312\python.exe scripts\run_mobilepilot_androidworld.py `
  --task ClockStopWatchRunning `
  --mode hybrid `
  --runtime-version v2 `
  --max-steps 6 `
  --adb-path C:\Users\Admin\AppData\Local\Android\Sdk\platform-tools\adb.exe `
  --trace-path artifacts\traces\demo-clock-v2.jsonl `
  --seed 0
```

不要重新运行 `runtime_eval_12_v2*.json` 中已经产生结果或 infrastructure error 的
任务；冻结 Runner 会拒绝覆盖 Trace 和自动重试。

## 三分钟讲解

1. **问题（35 秒）**：多步 GUI Agent 不只是识别坐标。V1 的主要失败是非法输出、
   循环、状态丢失和模型误报完成。
2. **方法（70 秒）**：指 README 架构图，区分 Protocol Guard 与 Agent Recovery；
   解释短期状态、循环检测、按需 Tree、一次有限 replan 和官方 reward。
3. **证据（45 秒）**：展示 `SystemWifiTurnOff` 的 Recovery 救回 Trace，再展示
   `SystemBrightnessMax` 或新子集绘图任务的未救回 Trace。
4. **结果与边界（30 秒）**：开发回归 4/20→9/20、非法终止 65%→35%；但新冻结
   子集 V1 2/6、V2 1/6，未证明泛化。说明为什么仍保留这个结果。

## 面试追问准备

- **为什么不继续换模型？** 当前目标是隔离 Runtime 改动；换模型会混入新的变量。
- **UI Tree 有用吗？** 每步附带没有证明收益；作为失败时的按需工具更节省上下文，
  但新子集也没有产生救回。
- **为什么可信？** 任务、源码、模型、seed、步数和预算先冻结；官方 reward 唯一判定；
  Trace 和基础设施错误均保留，不为单题重试。
