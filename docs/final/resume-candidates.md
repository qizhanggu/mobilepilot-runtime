# 简历候选描述

**MobilePilot｜Android GUI Agent Runtime 与可审计评测（个人项目）**

- 设计视觉优先的 Android GUI Agent Runtime：将 GUI-Plus 的结构化动作接入 ADB/uiautomator2 与 AndroidWorld，支持多步点击、输入、滑动、返回、启动 App、状态验证和 JSONL Trace 审计。
- 建立 Raw、网格、UI Tree 辅助的可消融评测链路；完成 ScreenSpot-v2 Mobile 471 条 held-out 单步 grounding 与 AndroidWorld 固定20题多步官方 reward 评测，严格分离自建、公开单步和多步结果。
- 处理坐标体系差异、Unicode 输入、模型非法 JSON、`PROPOSE_COMPLETE` 误完成和断点续跑；以官方 reward 而非模型自报完成判定任务成功。

面试时主动说明：ScreenSpot 上 Raw 70.49% 高于10×10 Grid 66.67%；AndroidWorld 仅为固定20题的纯视觉5/20、混合4/20，体现的是完整评测与失败分析能力，不是通用成功率宣传。
