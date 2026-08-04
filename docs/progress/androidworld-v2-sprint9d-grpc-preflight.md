# AndroidWorld Sprint 9D：模拟器 gRPC 根因与最终重冻

日期：2026-08-05

## 根因确认

启用官方本地缓存后，冻结任务仍在模型调用前超时。只读进程审计发现模拟器启动参数
缺少 AndroidWorld 文档要求的 `-grpc 8554`。ADB 因 `-port 5554` 正常而显示设备
在线，但 AndroidWorld 控制通道无法完成初始化。

模拟器随后只在 `emulator-5554` 上以以下关键参数重启：

```text
-avd AndroidWorldAvd -port 5554 -grpc 8554 -no-snapshot-save
```

使用仓库已有官方缓存、且不创建任务或调用模型的连接探针在 25.5 秒内得到
`androidworld_env_connected=1`。因此缓存和 gRPC 两项环境条件均已验证。

## 最终清单

由于超时任务不重试，`configs/androidworld/runtime_eval_12_v2d.json` 排除已经启动环境
初始化的 `SimpleCalendarDeleteOneEvent`，保留未启动的后 11 题，并补入此前从未列出
或运行的 `AudioRecorderRecordAudio`。

- task hash：`b75c899aa31745abea02b32087ae8f8eeb24ca5e3daefc0870af09c7c2aab7a9`
- source hash：`6ae0d4935bb7c37c219eacf2c787d63e2054847aa4791278a6e385787d417c36`
- AndroidWorld、模型、V1/V2 顺序、seed、步数、mode 和指标均不变

此前中断产物继续保留，只作为基础设施审计证据，不参与最终成功率。
