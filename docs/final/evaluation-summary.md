# MobilePilot 实验结果总表

更新时间：2026-08-05

## 总览

| 证据层 | 数据与规模 | 主结果 | 可说 / 不可说 |
| --- | --- | --- | --- |
| 自建受控实验 | 8 任务 × 7 配置 × 3 次 = 168 runs | 10×10 pure vision 24/24 | 可解释网格在测试 App 有效；不可称公开泛化 |
| ScreenSpot-v2 Mobile | 471 条 held-out × Raw/Grid | Raw 332/471（70.49%），Grid 314/471（66.67%） | 可说完成公开单步评测；不可称网格优于原图 |
| AndroidWorld V1 | 历史固定 20 题 × 2 模式 = 40 runs | vision-only 5/20，hybrid 4/20 | 任务已经用于后续开发，只能作开发基线；不是完整 116 类成绩 |
| AndroidWorld V2 开发回归 | 同一暴露 20 题，hybrid | V1 4/20 → V2 9/20 | 可说开发回归改善；不可称 held-out 泛化 |
| AndroidWorld 新冻结任务 | 6 个完整 V1/V2 配对后基础设施中断 | V1 2/6，V2 1/6 | 可说已完成子集未显示收益；不可称完整 12 题结果 |

## AndroidWorld V2 开发回归

固定 `gui-plus-2026-02-26`、seed 0、hybrid、每题最多 12 个动作：

| 指标 | V1 | V2 |
| --- | ---: | ---: |
| reward-positive | 4/20（20%） | 9/20（45%） |
| 非法输出终止 | 13/20（65%） | 7/20（35%） |
| 步数耗尽终止 | 2/20（10%） | 1/20（5%） |
| 平均执行动作 | 4.05 | 5.60 |
| 循环检测 | 0 | 9 |
| Recovery 触发 / 救回 | 0 / 0 | 10 / 3 |
| 按需 UI Tree 请求 | V1 每步共 94 次 | 23 次 |
| VLM 调用 | 94 | 144 |
| Token | 421,748 | 493,719 |
| 模型延迟合计 | 307.00 s | 425.34 s |
| 估算目录价 | ¥0.6596 | ¥0.7969 |

配对结果：6 题改善、1 题退化、3 题都成功、10 题都失败。V2 的 11 条失败终止为
7 次非法输出、2 次 Recovery 后仍重复危险动作、1 次 Recovery 耗尽、1 次步数耗尽。

证据：
`artifacts/evaluation/androidworld-v2-development-20260804/regression-20/`。

## 新冻结任务：仅报告完整配对子集

最终冻结批次在 6 组完整配对后，被 `NotesTodoItemCount` 的 Joplin SQLite
`no such module: fts4` 初始化错误暂停。该错误发生在模型调用前；未重试该题，也没有
继续补跑后续任务。

| 指标 | V1（6 题） | V2（6 题） |
| --- | ---: | ---: |
| reward-positive / full reward | 2 / 2 | 1 / 1 |
| 非法输出终止 | 1 | 2 |
| 步数耗尽终止 | 3 | 0 |
| 循环检测 | 0 | 2 |
| Recovery 触发 / 救回 | 0 / 0 | 2 / 0 |
| 平均执行动作 | 8.17 | 3.67 |
| VLM 调用 | 51 | 32 |
| Token | 201,775 | 107,590 |
| 模型延迟合计 | 218.27 s | 90.08 s |
| 估算目录价 | ¥0.3195 | ¥0.1739 |

配对结果：`CameraTakePhoto` 两版成功；`ExpenseDeleteDuplicates` 仅 V1 成功；其余
4 题两版失败。V2 降低动作、调用、Token、延迟和估算成本，但没有提升成功数。

证据：`artifacts/evaluation/androidworld-v2-frozen-final2-20260805/`。目录没有
`summary.json` 是预期行为：Runner 在基础设施错误后暂停，原始 `runs.jsonl` 保留。

## 基础设施中断记录

两次冻结尝试因模型调用前的环境问题中断，均未删除或覆盖：

- `androidworld-v2-frozen-20260804/`：AndroidWorld 重新下载 Accessibility Forwarder
  时 TLS EOF；10 条有效运行后暂停。
- `androidworld-v2-frozen-refreeze-20260804/` 与
  `androidworld-v2-frozen-final-20260805/`：模拟器重启遗漏 `-grpc 8554`，首条在模型
  调用前超时。

随后增加官方缓存强制预检、恢复正确 gRPC 启动参数，并用零模型调用探针确认环境连接。
最终批次中的 Joplin `fts4` 错误是新的任务初始化问题。

## 成本边界

本轮 V2 冒烟、20 题开发回归、首次中断批次和最终有效子集的估算目录价合计约
`¥1.58`，低于 `¥15` 硬上限。基础设施超时发生在模型调用前，费用为 0。目录价来自
Trace Token 估算，不等于账单实扣。

完整历史协议见 `docs/progress/`。旧文件名和旧 artifact 目录中的 `held-out` 是历史
命名，当前解释以本总表为准。
