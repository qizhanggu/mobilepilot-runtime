# AndroidWorld Sprint 3：开发冒烟进展

日期：2026-07-27
状态：**开发任务正在扩展；所有结果均为单次开发证据，不构成评测成绩。**

## 已运行的任务

| 任务 | 模式 | 官方 reward | 解释 |
| --- | --- | --- | --- |
| `OpenAppTaskEval`（seed=0，目标 Settings） | vision_only | 1.0 / 1 步 | 模型输出 `OPEN_APP settings`，官方检查当前 Activity 后成功。 |
| `ClockStopWatchRunning`（seed=0） | hybrid | 1.0 / 3 步 | 模型依次打开 Clock、进入 Stopwatch、点击开始；成功由官方 reward 判定。 |
| `SystemWifiTurnOnVerify`（seed=0） | vision_only | 初始即 1.0 / 0 步 | 这是预条件验证题，Wi-Fi 已开启；Runner 已修正为零调用退出，不能算 Agent 能力成功。 |
| `ClockTimerEntry`（seed=0，12:48:56） | hybrid | 0.0 / 8 步 | 已进入 Timer 并进行数字点击，但后续发生重复/回退，耗尽步数失败。 |
| `SimpleSmsSend`（seed=0） | hybrid | 0.0 / 1 步 | 模型上滑进入抽屉后返回空内容；无执行层异常，保留为输出稳定性失败。 |
| `ContactsAddContact`（seed=0） | hybrid，snapshot | 0.0 / 0 步 | 首步即空模型响应。 |
| `ContactsAddContact`（seed=0） | hybrid，主版本 `gui-plus` | 0.0 / 8 步 | 能打开 Contacts 并持续执行，但反复滑动/重开应用，未进入创建表单。 |
| `MarkorCreateNote`（seed=0） | hybrid，snapshot | 0.0 / 8 步 | 当时 AndroidWorld 的预置 Markor Activity 启动失败；该条标注为环境兼容性与后续导航失败，不能单独归因模型。 |
| `SimpleCalendarAddOneEventTomorrow`（seed=0） | hybrid，snapshot | 0.0 / 10 步 | 完成打开 Calendar、新建事件、填写标题，但在日期、描述、时长和保存前耗尽步数；官方数据库验证未发现目标事件。 |
| `ExpenseAddSingle`（seed=0） | hybrid，snapshot | 0.0 / 8 步 | 修复多 JSON 输出解析后，已填写名称、金额、备注并尝试切换分类；未选定 Transportation 或保存，耗尽步数。 |
| `MarkorCreateNote`（seed=0） | hybrid，snapshot，完成官方 App setup 后 | 0.0 / 8 步 | 环境启动问题消除，模型打开 Markor 并进入新建文件入口，但未输入目标文件名/正文即耗尽步数。 |
| `SimpleSmsSend`（seed=0） | hybrid，snapshot，完成官方 App setup 后 | 0.0 / 6 步 | 模型最终成功打开 Simple SMS Messenger，下一步返回空内容；不是应用缺失。 |

## 开发期间发现并修复的通用问题

- AndroidWorld 的 `OPEN_APP` 对官方 app key 严格匹配。新增显示名英文冠词规范化，并把动作执行异常落为结构化 Trace，避免进程崩溃。
- JSONL 原有脱敏规则误遮蔽 `prompt_tokens` 等核算字段；现仅脱敏真实凭证键名，保持 Token 审计可用。
- 多步 Actor 对可无歧义的截断/未转义 `reason` 点击输出，有限恢复 `CLICK` 坐标；不恢复损坏的 `TYPE` 文本。
- Runner 在首步前读取官方 reward，避免把已满足预条件的任务误记为 Agent 成功；刚好达到最大步数时 Agent 也会返回明确终止原因。
- 主版本 `gui-plus` 与 snapshot 的点击坐标约定不同：前者在本次开发运行中输出截图像素坐标，后者输出 0--1000 归一化坐标。AndroidWorld 专用解析器现在先记录并严格校验两者，ScreenSpot 冻结解析器未改动。
- snapshot 曾在 Calendar 中以坐标加 `reason: swipe up` 的形式遗漏 `direction`。只在理由明确写出 `swipe up/down/left/right` 时，解析器才恢复该方向；其他模糊 SWIPE 输出仍失败。
- 模型偶尔在一个响应中连续输出多个 JSON。Actor 现在严格选择第一个完整 JSON 对象，保证每个 Agent step 最多执行一个动作；例如 Expense 的首个 `TYPE 179.68` 可被保留，后续多余输出不执行。
- 若模型提议 `PROPOSE_COMPLETE`，Runner 会立即查询 AndroidWorld 官方 reward。reward 仍为 0 时，该提议会被记录为 `official_completion_rejected`，作为下一步的失败上下文并在剩余预算内继续；模型自报完成不再能提前结束任务。

## 真实性边界

- 上表每个任务均只是一条开发运行，不能写成成功率或纯视觉/混合感知对比结论。
- `ClockTimerEntry` 的两次协议失败 Trace 与一次真实多步失败 Trace、短信空输出 Trace、联系人失败 Trace、Markor 环境失败/重跑 Trace、Calendar 失败 Trace 和 Expense 失败 Trace 均保留在本地；未覆盖、未删除。
- 目前 Critic 仍只做越界检查，Verifier 仅记录页面变化；两者不替代官方 reward。

## 下一步

继续扩展到剩余开发任务，优先覆盖中文/文本输入、联系人、日历、笔记、记账和跨 App 流程；每题保持固定 seed、步数上限、官方 reward 与 JSONL Trace。
