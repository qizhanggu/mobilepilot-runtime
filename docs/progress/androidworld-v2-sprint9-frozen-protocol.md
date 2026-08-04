# AndroidWorld Sprint 9：全新 12 题冻结协议

冻结日期：2026-08-04

状态：**清单与协议已在查看任何结果、调用模型之前冻结。**

## 这批任务与旧 20 题的关系

旧 20 题及更早的 10 个开发任务已经参与过分析，全部进入
`development_task_exclusions`。它们今后只用于开发和回归。

新的 `configs/androidworld/runtime_eval_12_v2.json` 包含 12 个此前未出现在本仓库
配置、文档或实验产物中的 AndroidWorld task ID。选择时只查看 registry 中的任务名
并考虑交互面覆盖，没有运行任务、查看参数实例或调用模型。

覆盖面包括：系统设置、跨设置操作、录音命名、文件移动、文本编辑、日历新增/删除/
查询、短信回复/信息转用和记账列表编辑。

## 冻结项

- 任务清单及顺序：12 题，task hash
  `2025754c0561ca1ab1e19afe1f5624cea4cb7e159fab60a83084ed143fbdd9f3`
- 对照顺序：每题先 V1、后 V2，均为 `hybrid`
- Agent 源码 hash：
  `456cf27698409fedd3b093f7398743f747c9bce24dea754bc332fefdd50a1194`
- AndroidWorld commit：`3e50888527ef9f29b9157ecd537e408008bb1c85`
- 模型：`gui-plus-2026-02-26`
- seed：`0`
- 最大动作步数：`12`
- 最大 VLM 逻辑调用：`350`
- 本批目录价硬上限：`¥12`
- 设备：只允许 `emulator-5554`

冻结指标包括官方成功率、非法输出终止率、步数耗尽率、循环检测、Recovery 触发/
救回/误触发、平均动作数、调用数、Token、延迟、成本和 failure taxonomy。

## 防止结果污染的执行规则

1. Runner 在第一题前检查唯一设备、模型、AndroidWorld commit、任务 hash、源码 hash
   和 tracked workspace 是否干净。
2. `(task, variant, mode)` 是唯一运行键，禁止覆盖已有 Trace。
3. 单题不因失败而重试；基础设施失败会暂停整批并保留现场。
4. 冻结后不根据新 12 题结果调整 Prompt、代码、任务清单或步数。
5. 官方 reward 是唯一最终成功判定。

新 12 题结果将与开发集结果分表呈现；即使 V2 无提升或退化，也保留并如实报告。
