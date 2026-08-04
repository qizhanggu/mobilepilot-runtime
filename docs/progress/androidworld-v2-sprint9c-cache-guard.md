# AndroidWorld Sprint 9C：冻结评测缓存保护与最终清单

日期：2026-08-05

## 根因

第二批冻结评测的第一条运行在模型调用前等待 600 秒并超时。仓库已经缓存了
AndroidWorld 官方 Accessibility Forwarder APK，但启动命令没有设置
`MOBILEPILOT_ANDROIDWORLD_DOWNLOAD_CACHE`，AndroidWorld 因而重新访问 GCS。

这属于评测基础设施配置遗漏，不是 Agent、任务动作或模型输出失败。超时记录保留在
`artifacts/evaluation/androidworld-v2-frozen-refreeze-20260804/`，该任务不重试。

## 修复

冻结 Runner 现在把官方 APK 本地缓存设为强制预检项：

- 环境变量未设置时立即拒绝运行；
- 缓存 APK 不存在或为空时立即拒绝运行；
- 缓存绝对路径写入 preflight，并参与断点协议一致性检查。

缓存只改变 AndroidWorld 官方组件的下载传输方式，不改变 AndroidWorld commit、Agent
代码、Prompt、任务、reward 或模拟器系统环境。

## 最终清单

`configs/androidworld/runtime_eval_12_v2c.json` 包含第二批中尚未启动的 11 题，
以及此前从未出现的 `CameraTakeVideo`。已开始环境初始化的任务全部进入排除项。

- task hash：`6399aed80b4c50bd925b1cb883b47f4707fc7d52303ac21bc5214d8865441d30`
- frozen source hash：
  `6ae0d4935bb7c37c219eacf2c787d63e2054847aa4791278a6e385787d417c36`
- 模型、V1/V2 顺序、mode、seed、步数和指标不变
- 正式命令必须使用仓库现有 `.local/androidworld-download-cache`

本次重新冻结只依据任务是否已经启动，不依据任何成功或失败结果。最终报告会同时列出
两次基础设施中断，不把未完成批次隐藏起来。
