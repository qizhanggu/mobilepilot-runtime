# MobilePilot 实验结果总表

更新时间：2026-08-10

## 总览

| 证据层 | 数据与规模 | 主结果 | 可说 / 不可说 |
| --- | --- | --- | --- |
| 自建受控实验 | 8 任务 × 7 配置 × 3 次 = 168 runs | 10×10 pure vision 24/24 | 可解释网格在测试 App 有效；不可称公开泛化 |
| ScreenSpot-v2 Mobile | 471 条 held-out × Raw/Grid | Raw 332/471（70.49%），Grid 314/471（66.67%） | 可说完成公开单步评测；不可称网格优于原图 |
| AndroidWorld V1 | 历史固定 20 题 × 2 模式 = 40 runs | vision-only 5/20，hybrid 4/20 | 任务已经用于后续开发，只能作开发基线；不是完整 116 类成绩 |
| AndroidWorld V2 开发回归 | 同一暴露 20 题，hybrid | V1 4/20 → V2 9/20 | 可说开发回归改善；不可称 held-out 泛化 |
| AndroidWorld V2.1 Planner 消融 | 同一暴露 20 题，hybrid | 5/20 | Planner/Checklist 未超过 V2，保留为负结果 |
| AndroidWorld V2.2 分层执行 | 同一暴露 20 题，hybrid | 最佳 7/20；1 次真实 Recovery 救回 | 输出与审计更稳，但成功率仍低于 V2 |
| AndroidWorld 新冻结任务 | 6 个完整 V1/V2 配对后基础设施中断 | V1 2/6，V2 1/6 | 可说已完成子集未显示收益；不可称完整 12 题结果 |
| AndroidWorld 新冻结 36 题 | 36 题，V1/V2.2 共 72 次计划运行 | 尚未运行 | 清单与源码 hash 已锁定；不可提前写成功率 |

## AndroidWorld V2 开发回归

固定 `gui-plus-2026-02-26`、seed 0、hybrid、每题最多 12 个动作：

| 指标 | V1 | V2 |
| --- | ---: | ---: |
| 完整成功 | 4/20（20%） | 9/20（45%） |
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

## AndroidWorld V2.2 action-only 开发回归

固定 GUI Actor `gui-plus-2026-02-26`；Qwen Subgoal Manager 与 Progress Verifier 固定
`qwen3.7-flash-2026-07-15`，seed 0、hybrid、每题最多 12 个执行动作。

| 指标 | 最佳开发回归 | Manager 边界消融 |
| --- | ---: | ---: |
| 完整成功 | 7/20（35%） | 5/20（25%） |
| 部分完成 | 0 | 1 |
| 非法输出终止 | 1 | 1 |
| 步数耗尽 | 4 | 3 |
| 循环检测 | 16 | 27 |
| Recovery 触发 / 救回 / 误触发 | 20 / 1 / 0 | 27 / 1 / 1 |
| 平均执行动作 | 6.15 | 6.85 |
| Subgoal Manager 调用 / 失败 | 50 / 15 | 55 / 17 |
| Progress Verifier 调用 | 26 | 36 |
| VLM 总调用 | 217 | 274 |
| Token | 828,938 | 1,059,825 |
| 模型延迟合计 | 710.79 s | 846.09 s |
| 估算目录价 | ¥0.8654 | ¥1.1257 |

最佳轮次失败 taxonomy：5 次 Recovery 耗尽、4 次步数耗尽、3 次 Recovery 后仍重复、
1 次非法输出。`ExpenseDeleteSingle` 是本轮唯一满足严格定义的 Recovery 救回。

组合任务的 reward 口径已修正：`0.5` 单独标记 partial 并继续执行，只有 `>=1.0` 才计
完整成功。最佳轮次中 `TurnOnWifiAndOpenApp` 从 partial 继续执行到 1.0。

证据：

```text
artifacts/evaluation/androidworld-v22-action-only-development-20260810/
  regression-20-step12-fix2-reward-and-evidence/
  regression-20-step12-fix3-manager-boundary/
```

Manager 边界消融增加调用和恢复，却降低完整成功，代码已回退；产物不删除。V2.2 的
7/20 仍低于 V2 的 9/20，不能写成 Agent 成功率升级。

## 新冻结 36 题：只锁协议，尚无结果

`configs/androidworld/runtime_eval_36_v22.json` 固定 36 个从未出现在旧 manifest 或
`runs.jsonl` 的任务，比较 V1 与 V2.2，共计划 72 次运行。两版统一 hybrid、seed 0、
每题 16 步；Actor 固定 GUI Plus，V2.2 Manager/Verifier 固定 Qwen 快照。

- 任务 hash：`cc408d7185991b356d60531c33ca2ca1c5681aa13e62eeeae03c70983437e8b2`；
- Agent 源码 hash：`8bf7aa4260fa49eea83738dfe368248fe082c4d1282c495cacea9fbf360fe110`；
- 最大逻辑调用 2600，目录价硬上限 ¥15；
- 当前尚未初始化任务或调用模型，因此没有可报告的成功率。

## 新冻结任务：仅报告完整配对子集

最终冻结批次在 6 组完整配对后，被 `NotesTodoItemCount` 的 Joplin SQLite
`no such module: fts4` 初始化错误暂停。该错误发生在模型调用前；未重试该题，也没有
继续补跑后续任务。

| 指标 | V1（6 题） | V2（6 题） |
| --- | ---: | ---: |
| 完整成功 | 2 | 1 |
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

历史 V2 阶段估算目录价约 `¥1.58`。本次三组 V2.2 20 题开发产物合计约 `¥2.89`，
加上小规模冒烟后仍显著低于 `¥15` 硬上限。基础设施超时发生在模型调用前，费用为 0。
目录价来自 Trace Token 估算，不等于账单实扣。

完整历史协议见 `docs/progress/`。旧文件名和旧 artifact 目录中的 `held-out` 是历史
命名，当前解释以本总表为准。
