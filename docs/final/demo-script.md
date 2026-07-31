# 可复现 Demo 与三分钟讲解脚本

## 运行边界

真实手机 Demo 必须先确认 device serial、测试 App 与动作；AndroidWorld Demo 只针对 `emulator-5554`，不连接用户真机。

```powershell
# 离线回归
D:\anaconda3\python.exe -m pytest

# AndroidWorld 单题（需已完成本地官方环境配置）
$env:MOBILEPILOT_ACTOR_MODEL='gui-plus-2026-02-26'
$env:MOBILEPILOT_ANDROIDWORLD_DOWNLOAD_CACHE=(Resolve-Path '.local').Path + '\androidworld-download-cache'
.\.local\conda\androidworld-py312\python.exe scripts\run_mobilepilot_androidworld.py --task ClockStopWatchRunning --mode hybrid --max-steps 5 --adb-path C:\Users\Admin\AppData\Local\Android\Sdk\platform-tools\adb.exe --trace-path artifacts\traces\demo-clock.jsonl --seed 0
```

## 三分钟讲解

1. **问题（30秒）**：截图到模型动作并不等于能完成手机任务，还要解决执行、状态变化、异常输出和成功验证。
2. **架构（60秒）**：展示 README 图；Actor 只提议动作，Critic 检查，DeviceAdapter 真执行，Verifier/官方 reward 决定是否完成，所有过程进 JSONL。
3. **证据（60秒）**：先展示真机“咖啡”受控 Trace，再展示 AndroidWorld 秒表成功；强调复杂日历任务失败 Trace 也被保留。
4. **评测（30秒）**：自建实验、ScreenSpot、AndroidWorld三层分开；公开结果没有证明网格或混合必然更优。
