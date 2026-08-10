# 代表性成功与失败 Trace

所有 JSONL 原始产物保存在本地 `artifacts/`。以下案例按官方 reward 和 Trace 事件链
选择，不根据 Git 历史推断运行过程。

## 真实 Recovery 救回

开发回归中有 3 条 Trace 同时满足：存在失败信号、触发一次 Recovery、后续动作改变、
最终 AndroidWorld 官方完整 reward=1.0。

| 任务 | 失败信号 | Recovery 行为 | 最终证据 |
| --- | --- | --- | --- |
| `SystemBluetoothTurnOn` | 重复相似动作 | 请求 Tree 并改变动作路线 | `agent_recovery_outcome.rescued=true`，reward=1 |
| `SystemWifiTurnOff` | 重复 `SWIPE down` | 按需 Tree，停止重复滚动并改路 | `rescued=true`，reward=1 |
| `MarkorCreateFolder` | 重复 `SWIPE up` | 按需 Tree，离开无进展路线 | `rescued=true`，reward=1 |

路径：

```text
artifacts/evaluation/androidworld-v2-development-20260804/regression-20/traces/
  SystemBluetoothTurnOn--v2--hybrid.jsonl
  SystemWifiTurnOff--v2--hybrid.jsonl
  MarkorCreateFolder--v2--hybrid.jsonl
```

这里的“救回”不是因为模型说完成，而是 Trace 最终出现官方 reward，并由 Runtime 将
对应 Recovery 标记为 `rescued=true`。

### V2.2 的 action-only 真实救回

`ExpenseDeleteSingle` 是 V2.2 最佳开发回归中唯一严格救回：

```text
两次点击后页面视觉近似
→ two_consecutive_unchanged_screens
→ 按需 UI Tree 暴露 Expense Detail / Taxi Fare / btn_delete
→ Actor 改变点击位置，changed_action=true
→ 后续确认删除
→ official_reward=1.0
→ agent_recovery_outcome.rescued=true
```

路径：

```text
artifacts/evaluation/androidworld-v22-action-only-development-20260810/
  regression-20-step12-fix2-reward-and-evidence/traces/
  ExpenseDeleteSingle--v2.2--hybrid.jsonl
```

该轮 Recovery 触发 20 次、只救回 1 次，因此只能证明链路真实存在，不能说 Recovery
已经稳定有效。

## Recovery 触发但没有救回

| 任务 | Trace 结果 | 说明 |
| --- | --- | --- |
| 开发集 `MarkorEditNote` | Recovery 后改变动作，reward 仍为 0 | 有 replan 行为，不等于救回 |
| 开发集 `SystemBrightnessMax` | Recovery 后仍重复原动作 | 执行前以 `unsafe_repeated_action_after_recovery` 停止 |
| 新子集 `SimpleSmsReplyMostRecent` | Recovery 触发 1 次，最终非法输出 | 新任务未复现开发收益 |
| 新子集 `SimpleDrawProCreateDrawing` | 两次页面无变化后 Recovery，仍重复 | 5 个动作后止损；V1 则耗尽 12 步 |

## 官方判定覆盖模型自报

- `SimpleCalendarLocationOfEvent--v2--hybrid.jsonl`：模型提议完成，但官方 reward=0，
  最终记失败。
- `SimpleSmsSendReceivedAddress--v2--hybrid.jsonl`：同样为错误 completion 提议，记失败。
- 开发集 `SimpleSmsReply`、`SimpleSmsResend`、`SimpleSmsSendClipboardContent`：模型未先
  自报完成，但逐步检查得到官方 reward，记成功。

## 基础设施失败不是 Agent 失败

`artifacts/evaluation/androidworld-v2-frozen-final2-20260805/runs.jsonl` 中
`NotesTodoItemCount--v1` 为 `infrastructure_error`：Joplin SQLite 初始化缺少 `fts4`，
发生在模型调用前。它不进入 6 对有效任务的成功率，也没有被重试。

ScreenSpot-v2 的 Raw/Grid 成功与失败可视化仍保存在
`artifacts/evaluation/screenspot-v2-20260723/held-out/visualizations/`，只用于单步
grounding 结论，不与多步 Agent 成功率混合。
