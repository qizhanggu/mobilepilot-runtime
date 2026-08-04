# 简历候选描述

## 推荐版本

**MobilePilot｜可审计 Android GUI Agent Runtime（个人项目）**

**技术栈：** Python、AndroidWorld、ADB、Android Emulator、uiautomator2、
Accessibility UI Tree、OpenAI-compatible VLM API、JSONL Trace、pytest、Git/GitHub

- 基于 AndroidWorld 构建 Android GUI Agent Runtime，设计 Actor、短期状态跟踪、
  Verifier、Loop Detection、有限 Recovery 与按需 UI Tree 工具调用，实现
  “观察—决策—执行—验证—恢复”多步闭环。
- 审计 40 条基线 Trace 并建立 failure taxonomy，定位非法输出、无进展循环、状态丢失
  和误报完成；将 Protocol Guard 与 Agent Recovery 分层，引入 schema 校验、一次安全
  结构化重试及失败后有限 replan。
- 在已暴露的 20 题开发回归集上，hybrid reward-positive 从 4/20 提升至 9/20，非法
  输出终止率由 65% 降至 35%；Recovery 触发 10 次、真实救回 3 次，并审计 Token、
  延迟、成本和失败原因。

## 简短版本

- 构建可审计 Android GUI Agent Runtime，通过短期状态、循环检测、按需 UI Tree 与
  有限 Recovery 改进失败处理；在 20 题开发回归集将 reward-positive 从 4/20 提升至
  9/20，记录 3 次“失败信号→replan→官方成功”救回链路。

## 面试时必须主动补充

- 20 题已经用于失败分析，因此 `4/20 → 9/20` 是开发回归，不是 held-out 泛化；
- 新冻结批次完成 6 对后因 AndroidWorld/Joplin 基础设施错误停止，V1 2/6、V2 1/6，
  没有复现成功率收益；
- V2 在该新子集将动作 49→22、调用 51→32，但 Recovery 2 次触发、0 次救回；可以
  解释为更会止损，不能说更会完成任务；
- Protocol Guard 是格式与接口可靠性，不能包装成通用推理能力；
- ScreenSpot-v2 上 Raw 70.49% 高于 Grid 66.67%，网格没有公开泛化收益。

## 一句话项目故事

我没有继续堆手机 UI 技巧，而是从 40 条失败 Trace 出发，把一个遇到异常就直接退出的
GUI Agent 改造成能记录进度、检测循环、按需调用工具、有限重规划并接受官方环境验证
的 Runtime；开发集有效，但新任务没有证明泛化，因此完整保留了退化和基础设施证据。
