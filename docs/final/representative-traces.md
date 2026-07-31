# 代表性成功与失败 Trace

所有原始 JSONL 保存在本地 `artifacts/`，路径如下；它们未被删改或为提高分数重跑。

| 类型 | 任务 | 证据 | 说明 |
| --- | --- | --- | --- |
| 成功 | AndroidWorld `ClockStopWatchRunning` | `artifacts/traces/androidworld-clock-stopwatch-hybrid-snapshot-run*.jsonl` | `OPEN_APP Clock`→Stopwatch→开始，官方 reward=1。 |
| 成功 | AndroidWorld held-out `ContactsNewContactDraft` | `artifacts/evaluation/androidworld-held-out-20260731/traces/ContactsNewContactDraft--hybrid.jsonl` | 官方 reward=1；只代表该固定 seed 单次运行。 |
| 失败 | AndroidWorld `SimpleCalendarAddOneEventTomorrow` | `artifacts/traces/androidworld-calendar-event-hybrid-snapshot-run3-protocol-fix.jsonl` | 填写标题后在日期/保存前耗尽步数。 |
| 失败 | AndroidWorld held-out | `.../runs.jsonl` | 20题对照中13题两种模式均失败，主要为超步数或非法输出。 |
| 单步视觉 | ScreenSpot-v2 | `artifacts/evaluation/screenspot-v2-20260723/held-out/visualizations/` | 含 Raw/Grid 成功与失败的标注可视化。 |

Trace 中的模型原始输出、动作、页面指纹、Token、费用与官方 reward 共同构成审计证据；本项目不以模型自报完成替代官方成功。
