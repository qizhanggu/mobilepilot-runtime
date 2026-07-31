# AndroidWorld 20 题 Held-out 协议

## 边界

本协议使用 AndroidWorld 固定提交 `3e50888527ef9f29b9157ecd537e408008bb1c85` 的 **20 条冻结任务子集**。它不是 AndroidWorld 全部 116 类任务的成绩，更不能替代官方完整 benchmark。

开发阶段已使用的 10 个任务 ID 被明确排除。清单在任何 held-out 模型调用前固定为 [configs/androidworld/held_out_20.json](../../configs/androidworld/held_out_20.json)，其中保存 AndroidWorld commit、模型、seed、步数上限、任务顺序、选择规则和任务 ID 哈希。

## 两种对照

| 配置 | 动作决策输入 | 保留的共同机制 |
| --- | --- | --- |
| `vision_only` | 截图和任务目标；不读取或序列化 Accessibility/UI Tree | 同一 GUI-Plus snapshot、Actor Prompt、解析器、Critic、Verifier、Recovery、最大步数与官方 reward。 |
| `hybrid` | 截图、任务目标和按需读取的 Accessibility/UI Tree | 同上；Trace 记录每步 UI 元素数量，不能把树本身当作官方成功判定。 |

正式阶段每个 `(task_id, mode)` 仅运行一次，seed 固定为 0，单条最大 12 个真实动作步。网络超时、空输出、非法协议和超步数均保留为失败；不为单题重试。AndroidWorld 的 `task.is_successful(env)` 是唯一成功判定，MobilePilot 本地 Verifier 只能提供诊断。

## 运行前门禁

1. 20 条任务 ID 与开发清单零重叠，哈希匹配；
2. 固定 AndroidWorld commit、模型 `gui-plus-2026-02-26`、Prompt/解析器代码和 Git commit；
3. 只使用已通过官方 setup 的 App，Joplin 等 Windows 环境缺失依赖不纳入；
4. 完整测试与 `git diff --check` 通过；
5. 先执行无模型调用的 manifest/audit 检查，再允许批量 Runner。

## 输出与解释

每条运行保存原始 JSONL Trace、官方 reward、步数、VLM 调用数、UI Tree 使用次数、延迟、Token、估算成本和终止原因。汇总分别报告两配置成功数、平均步数、无效输出、Critic 拦截、Recovery 触发和失败类别。

如果其中一种配置更高，只能表述为“在该固定 20 题子集、该模型和该预算下的结果”；不能归因全部给 MobilePilot，也不能推广为 116 类官方总成绩。
