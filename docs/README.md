# 当前重构文档

本目录只保存 MobilePilot 重构期间仍在生效的设计、计划和阶段进展。

| 位置 | 内容 |
| --- | --- |
| [roadmap.md](roadmap.md) | 已批准的全量改造路线、阶段验收和真机边界。 |
| [progress/](progress/) | 每完成一个阶段生成一份简短、可核验的进展报告。 |
| [design/hybrid-grounding.md](design/hybrid-grounding.md) | 视觉主链路、按需 UI Tree 辅助与三种可消融模式。 |
| [design/adb-uiautomator2-decision.md](design/adb-uiautomator2-decision.md) | Phase 2 的设备自动化技术选型与重评估门。 |
| [progress/phase-03-runtime-loop.md](progress/phase-03-runtime-loop.md) | Phase 3 的真实 VLM fallback、任务闭环、Trace 与三次真机复跑证据。 |
| [evaluation/device-adapter-ab-2026-07-22.md](evaluation/device-adapter-ab-2026-07-22.md) | ADB 与 uiautomator2 的中文输入、UI Tree 和端到端耗时真机对照。 |
| [evaluation/visual-mainline-batch-01.md](evaluation/visual-mainline-batch-01.md) | 8 个任务、7 种配置、3 次重复的视觉主链路完整矩阵与失败分析。 |
| [evaluation/screenspot-v2-b0-protocol.md](evaluation/screenspot-v2-b0-protocol.md) | ScreenSpot-v2 Mobile 官方发布版本、501/502差异、划分与确定性评分协议。 |
| [evaluation/grid-development-b1-2026-07-23.md](evaluation/grid-development-b1-2026-07-23.md) | 10×10、8×16、10×20私有开发集对照及唯一网格冻结。 |
| [evaluation/screenspot-v2-b3-integration-audit.md](evaluation/screenspot-v2-b3-integration-audit.md) | 30条 integration/audit subset 上 Raw 与冻结10×10的60次调用结果。 |
| [evaluation/screenspot-v2-b4-held-out.md](evaluation/screenspot-v2-b4-held-out.md) | 471条 held-out 的942次正式调用、配对检验、501条补充汇总与失败审计。 |
| [evaluation/androidworld-integration-plan.md](evaluation/androidworld-integration-plan.md) | AndroidWorld 接入前的历史计划；当前结果以 `final/` 文档为准。 |
| [progress/public-benchmark-b4.md](progress/public-benchmark-b4.md) | 公共Benchmark阶段B4的简短工作进展。 |
| [final/frozen-evaluation-report.md](final/frozen-evaluation-report.md) | 最终36题冻结清单中的30个有效V1/V2.2配对、逐题结果、Recovery与基础设施边界。 |
| [final/interview-handbook.md](final/interview-handbook.md) | 当前架构、技术细节、三种讲法和面试追问。 |
| [final/resume-candidates.md](final/resume-candidates.md) | 与最终证据一致的简历候选描述。 |
| 后续 `architecture/`、`evaluation/` | 仅在对应能力真正实现后添加的当前设计与评测文档。 |

原离线竞赛原型的架构、实验和失败复盘已保存在 [archive/legacy-prototype/docs/](../archive/legacy-prototype/docs/)，用于追溯基线，不作为当前架构说明。
