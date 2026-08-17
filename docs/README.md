# MobilePilot 文档导航

这里按“先看结论，再看证据，最后看开发历史”整理文档。第一次了解项目不需要从 Sprint 记录开始翻。

## Start Here

| 你想了解什么 | 推荐入口 |
| --- | --- |
| 两分钟看懂项目 | [项目首页](../README.md) |
| 面试时怎么讲 | [面试手册](final/interview-handbook.md) |
| 如何演示与复现 | [Demo 与复现指南](final/demo-script.md) |
| 代码从哪里读 | [首页 Code Map](../README.md#code-map) |
| Showcase 整理结果 | [Repository packaging report](final/showcase-packaging-report.md) |

## Final Evidence

这些材料对应最终冻结实验，优先级高于早期 Sprint 总结。

- [冻结评测报告](final/frozen-evaluation-report.md)：预冻结 36 题清单、30 个有效配对、边界与成本。
- [最终证据审计](final/audit/audit-summary.md)：结论、分母、源码边界和 Trace 证据的独立复核。
- [30 个有效配对](final/audit/paired-30.csv)：V1 与 V2.2 的逐题官方结果。
- [25 次 Recovery](final/audit/recovery-25.csv)：触发、动作变化和严格救回定义。
- 3 条严格救回 Trace：[Markor](final/audit/MarkorDeleteNewestNote--v2.2--hybrid.jsonl)、[Simple Calendar](final/audit/SimpleCalendarDeleteEvents--v2.2--hybrid.jsonl)、[Tasks](final/audit/TasksHighPriorityTasks--v2.2--hybrid.jsonl)。
- [pytest 证据](final/audit/pytest-final.txt)：冻结实现的 186 项本地测试结果。
- [简历候选描述](final/resume-candidates.md)：与最终证据口径一致的表达。

## Architecture & Design

- [Runtime 架构图](assets/architecture.svg)：Actor、Guard、Action Contract、Verifier、Tree、Recovery 与 Trace 的关系。
- [项目演进图](assets/project-journey.svg)：V1、V2、V2.1 负结果、V2.2、RCA 与冻结评测。
- [混合感知设计](design/hybrid-grounding.md)：视觉主链路与按需 UI Tree 的设计依据。
- [ADB / uiautomator2 选型](design/adb-uiautomator2-decision.md)：执行层取舍与边界。
- [重构路线](roadmap.md)：从旧竞赛原型到 MobilePilot Runtime 的阶段拆分。

## Evaluation

- [最终结果摘要](final/evaluation-summary.md)：当前有效的总览口径。
- [冻结评测报告](final/frozen-evaluation-report.md)：V1/V2.2 公平配对、基础设施排除与逐题结果。
- [AndroidWorld 冻结协议](evaluation/androidworld-held-out-protocol.md)：早期协议文档；最终口径以前一项为准。
- [ScreenSpot-v2 公开评测](evaluation/screenspot-v2-b4-held-out.md)：Raw 与冻结网格的单步定位结果。
- [视觉主链路矩阵](evaluation/visual-mainline-batch-01.md)：自建受控 App 的 168 条实验记录。
- [设备适配 A/B](evaluation/device-adapter-ab-2026-07-22.md)：ADB 与 uiautomator2 的输入、Tree 与耗时对照。

## RCA & Negative Results

- [V2.2 20 题逐 Trace RCA](final/v22-root-cause-analysis.md)：从首次偏离而不是最终死法追溯根因。
- [代表性 Trace](final/representative-traces.md)：成功、失败与 Recovery 案例。
- [冻结结果图](assets/frozen-results.svg)：只展示可审计的 paired metrics。
- [Markor Recovery 案例图](assets/recovery-case-study.svg)：stuck → 新证据 → 改变动作 → official reward。
- [10×10 网格开发实验](evaluation/grid-development-b1-2026-07-23.md) 与 [公开 held-out 结果](evaluation/screenspot-v2-b4-held-out.md)：受控环境有效，公开评测退化。
- [V2.1 Planner 负结果](progress/androidworld-v21-sprint12-development-result.md)：开发集 `5/20`，低于 V2 的 `9/20`。

## Development History

- [阶段进展索引](progress/README.md)：按 Phase / Sprint 追踪实现与实验。
- [V1 AndroidWorld 开发](progress/androidworld-sprint3-development.md) 与 [早期 20 题运行](progress/androidworld-sprint4-heldout.md)。
- [V2 Runtime](progress/androidworld-v2-sprint6-runtime.md)：Protocol Guard、状态、循环与 Recovery。
- [V2.2 Progress Verifier](progress/androidworld-v22-sprint14-progress-verifier.md) 与 [开发结果](progress/androidworld-v22-sprint16-development-result.md)。
- [最终定向修复](progress/androidworld-v22-final-directed-fixes.md)：冻结前的最小实现修正。

## Archive

旧离线竞赛原型的[架构、实验与失败复盘](../archive/legacy-prototype/README.md)仅用于追溯基线，不代表当前 Runtime。

展示资产的来源与生成说明见 [assets/README.md](assets/README.md)。
