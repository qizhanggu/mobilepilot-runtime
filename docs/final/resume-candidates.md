# MobilePilot 简历候选描述

## 技术栈

Python、AndroidWorld、ADB、Android Emulator、uiautomator2、Accessibility UI Tree、GUI-Plus/Qwen VLM API、JSONL Trace、pytest、Git/GitHub

## 推荐版本：Agent 应用开发 / Agent 工程岗

**MobilePilot｜可审计的 Android GUI Agent Runtime**

- 面向 Android 多步任务构建 Actor—Runtime—Verifier—Recovery 闭环；基于 40 条历史 Trace 将 31 次失败从表层终止追溯到协议缺口、状态污染、Completion Evidence 和 Recovery 纠偏不足，形成 failure taxonomy 与逐题 RCA。
- 将 GUI Actor 收窄为 action-only，Runtime 维护冻结 subgoal、postcondition evidence 和循环状态；实现确定性优先、事件触发 VLM 的两层 Verifier，以及最多两级、必须引用新证据的有限 Recovery。
- 补齐 LONG_PRESS、定点 DRAG、ANSWER/interaction_cache 动作契约，统一 schema、边界校验、AndroidWorld Adapter、官方 reward 判定和 JSONL Trace；完成 186 项 pytest 与真实模拟器 smoke。
- 在预先冻结 36 题清单的 30 个基础设施有效配对上，V1/V2.2 官方成功由 0/30 提升至 9/30，paired 9 改善/0 退化，非法输出终止由 21 降至 4；25 次 Recovery 中 3 次形成“失败信号→新证据→换动作→官方成功”的严格救回。
- 将 UI Tree 从每步上下文改为按需工具，冻结评测调用由 209 次降至 49 次，其中 19 次改变动作；完整保留 Planner、网格、Recovery 失败及 Windows SQLite/模拟器基础设施负结果，严格区分开发回归与未见任务评测。

## 两行压缩版

基于 AndroidWorld 构建可审计 Android GUI Agent Runtime，以 Trace 驱动协议、状态、Verifier、按需 UI Tree 与有限 Recovery 的根因修复；补齐 LONG_PRESS/DRAG/ANSWER 并以官方 reward 统一判定。

在冻结清单 30 个有效 V1/V2.2 配对上实现 0/30→9/30、非法输出终止 21→4、paired 9 改善/0 退化；25 次 Recovery 严格救回 3 次，完成 186 项测试。

## 更保守版本

开发 Android GUI Agent Runtime，围绕协议校验、短期状态、进度验证、按需 UI Tree、有限 Recovery 和官方 reward 建立可审计闭环；通过 Trace RCA 定位 Action Contract 与状态流转缺陷，并完成 186 项自动化测试。

在未参与开发的固定任务清单中获得 30 个有效配对，V2.2 完成 9 题、V1 完成 0 题；同时披露 21 个双方失败和 6 个基础设施无效任务，不将有效子集包装为 AndroidWorld 总体成绩。

## 面试时必须主动补充

1. `0/30 → 9/30` 是**冻结 36 题清单里的 30 个基础设施有效配对**，不是 AndroidWorld 总榜；
2. 6 个无效任务来自 OsmAnd 目录缺失与 Windows SQLite FTS4，不是 Agent 失败；
3. 9 个成功里只有 3 个是严格 Recovery 救回，其余主要来自动作/答案契约和正常执行闭环；
4. V2.2 仍有 21/30 失败，复杂表单、跨 App 长任务和页面理解没有解决；
5. V2.2 用更多调用换可靠性：目录价约 ¥1.65 vs ¥1.44；
6. 开发 20 题的 9/20 只用于回归，不能再称 held-out。

## 一句话项目故事

我不是给手机界面多加了几个按钮工具，而是把 GUI Agent “从什么时候开始走错、为什么后面的模块没救回来”做成了可追踪、可修复、可配对验证的 Runtime 工程流程。
