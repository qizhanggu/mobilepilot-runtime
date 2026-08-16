# MobilePilot V2.2 开发回归 Root Cause Analysis

更新时间：2026-08-10

## 审计范围与结论边界

本报告只审计以下已暴露的 20 题开发回归，不修改 Runtime 代码，也不运行或查看新冻结 36 题的结果：

```text
artifacts/evaluation/androidworld-v22-action-only-development-20260810/
  regression-20-step12-fix2-reward-and-evidence/
```

审计依据是 20 条 JSONL Trace、`runs.jsonl`、Actor 原始输出、Subgoal Manager 输出、确定性与 VLM Verifier 事件、UI Tree 摘要、Runtime State、Recovery 事件和逐步 official reward。Git 历史和汇总文件只用于确认版本边界，不替代 Trace 审计。

固定条件：AndroidWorld `3e50888527ef9f29b9157ecd537e408008bb1c85`，GUI Actor `gui-plus-2026-02-26`，Manager/Verifier `qwen3.7-flash-2026-07-15`，hybrid，seed 0，最多 12 个已执行动作。

本轮是开发/回归结果，不是 held-out；V2.2 为 7/20，仍低于 V2 的 9/20，不能包装成成功率提升。

## A. Executive Summary

1. **最大瓶颈不是普通 JSON 格式错误，而是 Actor 动作接口与任务需求不完整匹配。** 13 个失败中，4 个的 primary root cause 是当前动作契约无法可靠表达任务所需能力：`MarkorMoveNote` 需要长按，`SystemBrightnessMax` 需要精确拖动，两个 Calendar 信息检索任务需要把文本答案写入 AndroidWorld 的 `interaction_cache`。这四题增加步数也不会自然解决。
2. **Actor 在复杂页面上的下一步选择仍不稳定。** 3 个失败的 primary root cause 是已经到达正确页面后选错字段、错控件或重复局部策略：`MarkorChangeNoteContent`、`MarkorCreateFolder`、`SimpleCalendarAddOneEvent`。
3. **Subgoal Manager 的“格式可靠”不等于“语义可靠”。** 50 次调用没有 API/JSON 生成失败，但 15 次（30%）被 Runtime 判为 `invalid_already_satisfied`；另外仍有多次格式合法但把“当前可见控件”当成“动作完成证据”、猜错 App/Package、把操作步骤写成子目标的情况。
4. **Progress Verifier 不是当前第一瓶颈。** 26 次 VLM 判断中，本次人工复核为 23 次明显合理、1 次明显错误、2 次需要人工复核。最明显的错误是 `ContactsNewContactDraft` step 1：Contacts 已打开且右下角有新增按钮，却被判为 `regressed`。不过这次误判触发的点击恰好进入了新建联系人页，未成为最终根因。
5. **Verifier 的正确结论没有被 Runtime 正确消费。** `SystemBrightnessMax` step 4 和 `MarkorAddNoteHeader` step 7，VLM 已判定当前子目标 `completed`，同一步仍被 Loop Detection 按“连续无变化”处理并耗尽 Recovery。事件优先级和状态重置存在明确缺陷。
6. **Fingerprint 对小范围文字变化过于迟钝。** `MarkorEditNote` 已显示追加后的完整文本，`MarkorAddNoteHeader` 也已显示正确的新首行，但感知哈希仍给出 `visually_similar`，连续无变化计数没有被 UI Tree 文本变化或子目标完成重置。
7. **20 次 Recovery 只有 1 次严格救回，不是因为它“没触发”，而是因为它经常拿不到新策略。** 7 个 episode 直接重复被阻止动作，1 个在步数耗尽时来不及执行；12 个虽换了动作，但多数没有解决原始根因。只有 `ExpenseDeleteSingle` 的 UI Tree 暴露了明确的 `btn_delete`，新动作直接命中局部错误并最终 official reward=1。
8. **UI Tree 是有价值的局部纠错证据，但不是自动救命药。** 本轮请求 26 次，12 次改变候选动作；只有 1 次形成严格救回。Tree 能告诉 Agent“页面上有什么”，不能替代正确子目标、缺失工具或多步恢复策略。
9. **12 步对个别长表单任务偏紧，但不是 7/20 的主要解释。** 13 个失败中只有 4 个跑满 12 步，其中只有 `SimpleCalendarAddRepeatingEvent` 显示出较强的“仍在合理推进、可能只差步数”证据；其余三题分别被脆弱 evidence、缺失长按和缺失答案通道卡住。

## B. 20 个任务逐题 RCA

表中的 step 使用 Trace 的零基执行 step；“首次偏离”指第一处对最终失败有因果贡献的关键偏离，而不是最后的终止事件。

| Task | 结果 | 首次关键偏离与当时状态 | 表层终止 | Primary root cause | 主要责任模块 | 后续是否有机会救回 / 关键 Trace 证据 |
| --- | --- | --- | --- | --- | --- | --- |
| `SystemBluetoothTurnOn` | 成功，1.0，5 动作 | 无关键偏离；step 0 直接 `OPEN_APP Settings`，step 1 VLM 确认 Settings 已打开 | official success | 成功模式：离散开关、入口清晰 | Actor 主导 | Manager 的第二个 subgoal 因 evidence 已在当前页而失效，但 Actor 仍自行进入 Connected devices 并打开 Bluetooth；Verifier 主要做记录，未证明有因果提升 |
| `SystemBrightnessMax` | 失败，0.0，5 动作 | step 2 已在完整 Quick Settings，Actor 原始输出是无法解析的带坐标 `swipe`，安全重试改成点击滑条右端但未生效 | `recovery_exhausted` | 精确滑块拖动不在当前可靠动作接口内 | Actor/Adapter 动作契约 | step 4 VLM 正确判定“Quick Settings 子目标完成”，同一步 Loop 仍触发；Recovery 2 改成点击而非拖动，step 5 VLM 正确判 stalled。加步数只会继续猜滑条 |
| `SystemCopyToClipboard` | 失败，0.0，4 动作 | step 1 Chrome 已打开，Manager 却转向不存在/无法打开的 Keep Notes，而不是在现有输入区完成复制 | `recovery_exhausted` | 错误子目标与不可用 App 假设 | Subgoal Manager | step 2～4 Verifier 连续正确发现未进入 Notes；Tree 只看到 System UI；Recovery 2 又提出 `com.android.systemui` 是 Notes 并重试 Keep Notes，没有回到 Chrome 输入与复制路线 |
| `SystemWifiTurnOff` | 成功，1.0，4 动作 | 无关键偏离；Settings → Network & internet → Internet → toggle | official success | 成功模式：离散开关、路径短 | Actor 主导 | Manager 第二个 evidence 已满足而被拒，但 Actor 自行完成；与亮度任务对照说明离散点击可做、连续拖动不可做 |
| `TurnOnWifiAndOpenApp` | 成功，1.0，4 动作 | 无关键偏离；step 1 official reward=0.5，Runtime 没误当完整成功，继续到 1.0 | official success | 正确处理 partial reward | Runtime + Actor | step 3 Actor 遭遇 403，Protocol Guard 在未执行动作前安全重试并得到点击动作；这是协议可靠性价值，不是通用推理提升 |
| `ClockStopWatchPausedVerify` | 成功，1.0，2 动作 | 无关键偏离；打开 Clock 后点击 Stopwatch 区域，official reward=1 | official success | 成功模式：短路径、显著 tab | Actor 主导 | VLM 正确确认 Clock 打开；下一 subgoal 的 `ui_text=Stopwatch` 已在屏幕上而被拒，Actor 仍兜底成功 |
| `ContactsNewContactDraft` | 失败，0.0，12 动作 | step 6 已输入电话，但 frozen evidence 要求精确文本 `141-365-9376`；UI 格式化后一直无法匹配，subgoal 不再推进到 `Phone Label: Work` | `step_budget_exhausted` | 脆弱 Completion Evidence 冻结了错误生命周期 | Subgoal Manager / Runtime State | step 1 Verifier 把已打开的空 Contacts 页误判为 regressed，但 Recovery 点击“+”反而进入正确表单。之后 Grace/Lee 都完成；电话 evidence 连续 6 步不匹配，Actor在字段/标签弹层间点击。20 步可能偶然成功，但不解决根因 |
| `MarkorAddNoteHeader` | 失败，0.0，7 动作 | step 1 “打开文件”的 evidence 是列表里本来就有的文件名，Manager 被拒；决定性问题在 step 7：新首行和空行已正确出现，VLM 判 `completed`，Loop 仍立即终止 | `recovery_exhausted` | 子目标完成与 Loop/Recovery 的事件顺序错误 | Runtime State / Loop Detection | Recovery 2 实际把 header 输入正确，但未获得新的无循环窗口，也没继续重命名；这是“Recovery 有局部进展但未形成 official rescue”的典型 |
| `MarkorChangeNoteContent` | 失败，0.0，10 动作 | step 2 在没有清空旧文本时直接输入新文本，形成旧内容+新内容 | `recovery_exhausted` | Actor 选择了追加而非替换 | Actor | Manager 的“打开文件”却用目标新文本作 evidence，导致新文本一出现就错误完成该 subgoal；之后又提出已满足的“select all”证据。Recovery 能改变动作，但没有重新建立“清空→输入→重命名→保存”的正确链路 |
| `MarkorCreateFolder` | 失败，0.0，4 动作 | step 2 已进入新建文件/文件夹对话框，step 3 又点击原 FAB 区域，没有填写名称或切换 Folder | `unsafe_repeated_action_after_recovery` | Actor 对对话框状态与可操作控件理解失败 | Actor，Recovery 次责 | Recovery Tree 已明确给出 `Name`、`FOLDER`、`CANCEL`、`OK`；两级 Recovery 都重复同一坐标。Manager 的 `FOLDER` evidence 又是当前已可见控件，不是完成状态 |
| `MarkorEditNote` | 失败，0.0，7 动作 | step 4 已把句子追加到底部，UI Tree 与最终截图均能看到完整正确文本；pHash 仍判 visually similar，step 5 开始错误 Recovery | `recovery_exhausted` | 文字变化未进入进度信号，Loop 误杀 | Loop Detection / Runtime State | Recovery 2 反而把子目标改成“把光标放到底部”，而文字已经写入；step 7 VLM 只判断光标位置并给 progress，Runtime 随即耗尽，未点击 Save |
| `MarkorMoveNote` | 失败，0.0，12 动作 | step 2 Actor 正确请求 `long_press` 选中文件，但当前 tool enum 不支持；Protocol Guard 重试把它变成普通 click，直接打开文件 | `step_budget_exhausted` | 缺失 long-press 动作导致语义被改写 | Actor/Adapter 动作契约 | 后续 Actor 在编辑页和菜单间往返；step 10 Tree 仍显示编辑器。多 8 步不能补回缺失的长按能力，且“结构化重试得到合法动作”不等于语义安全 |
| `SimpleCalendarAddOneEvent` | 失败，0.0，8 动作 | step 5 已在 New Event 表单，但 Actor 连续点同一区域，没有可靠选择 Description、13:00、15 分钟 | `unsafe_repeated_action_after_recovery` | 复杂表单中的字段选择与局部策略重复 | Actor，Recovery 次责 | step 8 Tree 明确显示 Title、Description、日期、当前 `16:00`、Save；Manager Recovery 给出合理 description subgoal，但两次 replan 仍返回被阻止的同一点击 |
| `SimpleCalendarAddRepeatingEvent` | 失败，0.0，12 动作 | 没有明确单步“走错”；标题和描述已输入，后续在时间/重复设置对话框中连续导航 | `step_budget_exhausted` | 目前最像真实步数不足的任务 | Step budget，Manager 次责 | 12 个动作中大部分产生 UI 变化，0 次 Recovery、0 次 Loop；但 Trace 没保存最终完整页面，不能断言只差几步。需要单独 20 步诊断验证，而不是直接记作可救回 |
| `SimpleCalendarEventOnDateAtTime` | 失败，0.0，12 动作 | 根因从任务开始就存在：这是信息检索题，最终需提交文本答案；当前 tool/runner 只有 UI action 和无答案的 `PROPOSE_COMPLETE` | `step_budget_exhausted` | 缺失 AndroidWorld answer 回传通道 | Actor/Runner 集成 | Actor 在日历详情间来回点击，step 8 还出现非法 swipe 并被修复；即使找到标题，也没有可让 `interaction_cache` 接收答案的动作。20 步无效 |
| `SimpleCalendarNextEvent` | 失败，0.0，1 动作 | step 1 已打开 Calendar，Actor 尝试输出文本 `Meeting`，重试又明确输出 `action=answer` | `invalid_actor_output` | 模型意图正确但 `answer` 不在动作协议内 | Actor/Runner 集成 | Protocol Guard 只能把合法 UI 动作修复出来，不能凭空增加 answer channel；这不是普通 JSON 兼容问题 |
| `SimpleSmsReply` | 成功，1.0，5 动作 | 无关键偏离；打开 App、进入指定会话、输入、发送 | official success | 成功模式：目标对象和发送动作明显 | Actor + Protocol Guard | step 2 主调用 timeout，未执行动作时重试，随后完成。Manager 的会话 subgoal 因号码已在列表可见而失效，Actor 自行兜底 |
| `SimpleSmsResend` | 成功，1.0，2 动作 | 无关键偏离；当前已在正确会话，直接输入上一条文本并发送 | official success | 成功模式：当前页面即可完成 | Actor | 初始 Manager evidence 因上一条消息已存在而被拒；成功主要来自 Actor，不应归功于 Manager/Verifier |
| `SimpleSmsSendClipboardContent` | 失败，0.0，2 动作 | step 0 Manager 把“打开已知 App”过度操作化为“打开 app drawer 找图标”，Actor 连续 swipe up 但页面不变 | `unsafe_repeated_action_after_recovery` | 错误且过度操作化的 subgoal | Subgoal Manager，Actor/Recovery 次责 | Prompt 本来允许 `OPEN_APP`；两级 Recovery 和 Manager revision 仍坚持 app drawer，Tree 已显示 launcher 但没有改变策略。更多步数只会继续重复 |
| `ExpenseDeleteSingle` | 成功，1.0，5 动作 | step 1～2 两次点击未产生进展，step 3 Loop 正确触发 | official success | 唯一严格 Recovery rescue | Recovery + UI Tree | Tree 暴露 `Expense Detail`、`Taxi Fare`、`btn_delete`；Recovery 从旧点击改成删除按钮，随后确认，step 5 official reward=1，`rescued=true` |

## C. 根因统计

每个失败任务只指定一个 primary root cause；secondary factor 不计入下表分母。

| Primary root cause | 任务数 | 占 13 个失败 | Tasks |
| --- | ---: | ---: | --- |
| Actor/Runner 动作接口缺口 | 4 | 30.8% | `SystemBrightnessMax`、`MarkorMoveNote`、`SimpleCalendarEventOnDateAtTime`、`SimpleCalendarNextEvent` |
| Actor 复杂页面决策错误 | 3 | 23.1% | `MarkorChangeNoteContent`、`MarkorCreateFolder`、`SimpleCalendarAddOneEvent` |
| Subgoal / Completion Evidence 错误 | 3 | 23.1% | `SystemCopyToClipboard`、`ContactsNewContactDraft`、`SimpleSmsSendClipboardContent` |
| Runtime State / Loop 误杀 | 2 | 15.4% | `MarkorAddNoteHeader`、`MarkorEditNote` |
| 真实或高度疑似步数不足 | 1 | 7.7% | `SimpleCalendarAddRepeatingEvent` |

Secondary factors：

- 11 个失败任务触发过 Recovery，但没有一个最终形成 official rescue；唯一救回来自成功任务 `ExpenseDeleteSingle`。
- Manager/evidence 问题广泛参与了失败，即使它不是每题的 primary root cause。
- 3 次主 Actor 模型/API 异常（timeout 或 403）都被安全重试获得动作，因此环境/API 异常不是本轮成功率主因。
- 只有 1 个任务最终以 `invalid_actor_output` 结束；“普通格式错误”已从 V1 的主要死法退化为次要问题。但 unsupported action 暴露的**动作契约缺口**仍是主要问题，不能把两者混为一谈。
- 20 条 run 的 `infrastructure_error_count=0`；没有证据把本轮失败归因于 emulator 或 AndroidWorld 初始化。

## D. 7 个成功任务的共同模式

### 共同条件

1. 成功任务短：7 题平均 3.86 个动作；13 个失败平均 7.38 个动作。
2. 任务多为离散、可见、一次点击即可确认的状态变化：开关 Bluetooth/Wi-Fi、切换 Stopwatch tab、发送短信、删除单条 expense。
3. 不依赖长按、精确拖动、文本替换、跨多个表单字段或回答回传。
4. Actor 多数直接 `OPEN_APP`，而不是在 Launcher 上搜索；`SimpleSmsSendClipboardContent` 正好形成反例。
5. official reward 在 UI 副作用后自动判断成功，Actor 不需要自报答案。本轮 123 个执行动作只有 `OPEN_APP`、`CLICK_POINT`、`TYPE_TEXT`、`SWIPE` 四类，没有一次 `PROPOSE_COMPLETE`。

### 哪些模块真的有正向价值

- **Recovery：**只有 `ExpenseDeleteSingle` 具备严格的“失败信号 → Tree → 新动作 → official success”证据。
- **Protocol Guard：**`SimpleSmsReply` 的 timeout 和 `TurnOnWifiAndOpenApp` 的 403 都在未执行动作时安全重试并继续成功。这是输出/调用可靠性价值，不是推理能力提升。
- **Runtime reward 语义：**`TurnOnWifiAndOpenApp` 在 reward=0.5 时继续执行到 1.0，证明 partial/full 边界生效。
- **Verifier：**多次正确确认“目标 App 已打开”，使 subgoal 生命周期可审计；但成功任务通常本来就能继续，现有 Trace 不能证明这些 VLM 调用带来额外成功率。
- **Subgoal Manager：**最稳定的正向作用是把 Launcher 状态收敛为“打开目标 App”；之后 7 个成功任务中有 6 个出现 Manager subgoal 被 `invalid_already_satisfied` 拒绝，最终仍靠 Actor 完成。因此不能把 7/20 归功于 Manager。

### 成败配对

- `SystemWifiTurnOff` / `SystemBluetoothTurnOn` 对 `SystemBrightnessMax`：同为系统设置，离散开关成功，连续滑块失败，分叉点是动作能力而不是 App 导航。
- `SimpleSmsReply` 对 `SimpleSmsSendClipboardContent`：同一 App、同类发送任务；前者直接 `OPEN_APP`，后者被 Manager 引导到 app drawer 并在 Launcher 重复 swipe。
- `ExpenseDeleteSingle` 对 `MarkorCreateFolder`：两者 Recovery 都拿到 Tree；前者 Tree 暴露一个明确 `btn_delete`，后者是多字段对话框，Recovery 仍重复旧坐标。说明当前 Recovery 只擅长“局部、单步、入口明确”的修复。
- `SimpleSmsResend` 对 Markor 文本任务：同样有文字输入，短信的文本变化大且发送按钮明确；Markor 的小范围文本变化被 pHash 判为 visually similar，Loop 把正确输入当成无进展。

## E. Recovery 专项分析

本轮共有 20 个 Recovery episode，分布在 12 个任务；12 次候选动作改变，7 次重复被阻止动作，1 次因 step budget 到点没有执行 replan。严格救回 1 次。

| Task / episode | Trigger / blocked | UI Tree 与 replan | 最终结果 | 为什么成功或失败 |
| --- | --- | --- | --- | --- |
| Contacts #1 | step 1 `progress_verifier_regressed` / `OPEN_APP contacts` | Tree 已有 `Create contact`、`No contacts yet`；改点右下角 `+` | 0.0 | 局部动作有效，进入表单；后续被电话 evidence 卡住，所以不是严格 rescue |
| Expense #1 | step 3 两次无变化 / 错误点击 | Tree 有 `Expense Detail`、`Taxi Fare`、`btn_delete`；改点 Delete | 1.0 | 新动作直接解决局部根因，随后确认，唯一严格 rescue |
| AddHeader #1 | step 5 两次无变化 / 底部区域点击 | Tree 已在编辑器且有 Save；改点文本左侧 | 0.0 | 没解决“输入 header + 重命名”的任务级问题 |
| AddHeader #2 | step 6 再次无变化 | Manager 改为输入 header；replan 为 TYPE | 0.0 | 文本实际输入成功，VLM 也判 completed，但同一步 Loop 继续累计并终止 |
| ChangeContent #1 | step 4 Verifier stalled / 重复 TYPE | Tree 显示编辑器；改点文本 | 0.0 | 帮助重新聚焦，但未建立“清空旧文”约束 |
| ChangeContent #2 | step 7 两次无变化 | Manager 又提“select all”，evidence 已满足；改点 More | 0.0 | 子目标/evidence 仍错误，后续重复 TYPE |
| CreateFolder #1 | step 4 alternating loop | Tree 明确有 Name/FOLDER/OK；replan 仍是同一点击 | 0.0 | 没利用 Tree 的语义标签 |
| CreateFolder #2 | step 4 repeated blocked action | Manager 提 FOLDER，但 evidence 是当前已可见的 `FOLDER`；仍重复同一点击 | 0.0 | 第二级恢复没有产生新策略 |
| EditNote #1 | step 5 两次无变化 / TYPE | Tree 已显示追加后的正确全文；改点底部工具栏 | 0.0 | Recovery 建立在错误的“输入失败”判断上 |
| EditNote #2 | step 6 再次无变化 | Manager 改成“把光标放到底部”；改点正文 | 0.0 | 原任务内容已经完成，恢复反而回退到无关子目标，随后耗尽 |
| MoveNote #1 | step 10 revisited screen | Tree 显示仍在编辑器；改点 More | 0.0 | 根因是 long-press 工具缺失，页面内换点击无法补救 |
| CalendarAddOne #1 | step 8 两次无变化 | Tree 显示 New Event、Title、Description、16:00、Save；replan 重复同一点 | 0.0 | Tree 信息充分但 Actor 没改变动作 |
| CalendarAddOne #2 | step 8 repeated blocked action | Manager 正确改成填写 Description；replan 仍重复同一点 | 0.0 | Recovery 状态没有约束新动作必须落实新 subgoal |
| CalendarAtTime #1 | step 12 revisited screen | 已到 step budget，无 Tree/replan 执行 | 0.0 | 根因是缺失 answer channel，且恢复触发过晚 |
| SmsClipboard #1 | step 2 Verifier stalled / swipe up | Tree 仍是 Launcher；replan 仍 swipe up | 0.0 | 明知无变化仍重复动作 |
| SmsClipboard #2 | step 2 repeated blocked action | Manager 把 subgoal 改写成同义的“打开 app drawer”；仍 swipe up | 0.0 | 计划级恢复只是换句话，没有换路线 |
| Brightness #1 | step 4 两次无变化 / swipe down | Tree 已有 `Display brightness`；replan 仍 swipe down | 0.0 | VLM 同一步已确认旧 subgoal 完成，Runtime 却先按 Loop 恢复 |
| Brightness #2 | step 4 repeated blocked action | Manager 改成调到最大；点击滑条区域 | 0.0 | 目标修正合理，但工具只能 click/方向 swipe，无法可靠拖动；VLM 正确判 stalled |
| CopyClipboard #1 | step 2 Verifier regressed / open Keep Notes | Tree 只有 System UI；改点左上 | 0.0 | 没回到可用的 Chrome 输入路线 |
| CopyClipboard #2 | step 3 Verifier stalled | Manager 错把 `com.android.systemui` 当 Notes；又 open Keep Notes | 0.0 | Recovery 延续了错误 App 假设 |

### 为什么是 20 次触发、只有 1 次救回

当前 Recovery 更像“再问一次同一个 Actor”，还不是具备稳定纠偏策略的模块：

1. 7/20 episode 没有产生不同动作；
2. UI Tree 的标签没有被约束性地转化为动作依据；
3. 第二级 Manager revision 有时只是把原计划换句话；
4. long-press、drag、answer 等根因不是重新观察能解决的；
5. Loop streak 和 Recovery budget 在 subgoal 真正完成或语义文本变化后没有及时重置；
6. 只有 Expense 的失败满足当前 Recovery 的理想条件：局部错误、无危险副作用、Tree 有唯一明确按钮、一步即可回到正确路线。

## F. Subgoal Manager 专项分析

### 统计事实

- 50 次调用：33 `accepted`，15 `invalid_already_satisfied`，2 `revised`。
- 触发来源：20 initial，22 previous completed，8 recovery revision。
- Evidence 类型：16 visual_state，33 ui_text，1 package_activity。
- 没有 Manager API、空输出或 JSON 解析失败；汇总里的 15 次 failure 全是语义边界检查拒绝，不是服务不稳定。

### 低质量输出分类

1. **把动作/控件写成完成证据。** 例如“点击 Stopwatch tab”用 `ui_text=Stopwatch`；“点击 FOLDER”用 `ui_text=FOLDER`。控件在点击前就存在，不能证明点击后的状态。
2. **Evidence 与 goal 不一致。** `MarkorChangeNoteContent` 的 goal 是“打开文件”，evidence 却是最终新内容；新内容追加到旧文本后，Runtime 仍确认该 subgoal 完成。
3. **Evidence 过于脆弱。** Contacts 电话号码使用精确连字符格式；Android UI 的格式化可能变化，导致输入正确仍无法匹配。
4. **过度操作化。** `SimpleSmsSendClipboardContent` 不说“打开目标 App”，而是指定“打开 app drawer 找图标”，把一种可失败的操作路线冻结成目标。
5. **猜错环境或 Package。** `SystemCopyToClipboard` Recovery 把 `com.android.systemui` 当作 Notes 证据。
6. **过粗或缺少后续约束。** Markor 复合任务只管理“打开 App/文件”或一次输入，没有稳定维护“替换内容、重命名、保存”的剩余要求。
7. **生命周期降级。** 15 次 evidence 已满足被拒后，Runtime 常退化到 `CLICK_POINT`/`TYPE_TEXT` 这类动作级状态；任务没有新的可验证语义 subgoal，Recovery 也失去抓手。

### 人工质量判断

除了 15 次硬拒绝，至少还有以下格式合法但语义低质量的 accepted/revised 输出：Contacts 电话 exact text、MarkorChange 的目标内容 evidence、Calendar 查询任务的标题字符串 evidence、CalendarAddOne 的 `Call with`、TurnOnWifi 的页面入口文本、SmsClipboard 的 app drawer 路线、Brightness 的自然语言组合 UI text、CopyClipboard 的 Notes 路线。Manager 的首要问题不是“生成失败”，而是“postcondition 设计不稳定”。

## G. Progress Verifier 专项分析

### 调用分布

- 26 次 VLM Verifier：18 `completed`、5 `stalled`、2 `regressed`、1 `progress`、0 `uncertain`。
- 17 次用于 visual_state 子目标，6 次 suspected stalled，3 次 navigation/context changed。

### 人工复核

| 判断 | 数量 | 代表案例 |
| --- | ---: | --- |
| 明显合理 | 23 | 各类“目标 App 已打开”；Expense 打开；SmsClipboard stalled；MarkorChange 重复 TYPE stalled；Brightness 子目标完成/滑条未动；CopyClipboard 连续无进展 |
| 明显错误 | 1 | Contacts step 1：截图虽主体空白，但 package 已是 Contacts，右下角有新增按钮，应该是 completed 或 progress，不是 regressed |
| 需要人工复核 | 2 | CopyClipboard step 2 的 regressed 与 stalled 边界；MarkorEdit step 7 的 progress 对当前“光标位置”勉强成立，但对 whole goal 已无帮助 |

这不是一个人工标注 benchmark，因此 23/26 不能包装成正式 Verifier accuracy；它只是本次 RCA 的人工审计结果。

### 真正问题

1. VLM 已正确输出 `completed`，Runtime 仍可能先执行 Loop/Recovery 终止逻辑；判断正确但没有控制权。
2. 确定性层的 exact/visual/semantic 信号没有充分融合：小范围文字改变被 pHash 淹没，UI Tree 文字又不是每步读取。
3. `uncertain` 从未被使用，说明五分类在当前 prompt 下实际退化成四分类；这不是成功率主因，但后续可以用人工样本检查它是否有保留价值。
4. Verifier 能指出“偏了/没动”，但处置建议仍很粗；它没有提供可被 Runtime 强制执行的“回到哪个状态、避免哪个动作”的结构化约束。

## H. 下一阶段模块优先级

如果只能改一个模块，优先级应是：

1. **Actor action contract / AndroidWorld 适配层。** 不是先换 Actor 模型，而是补齐或明确拒绝 benchmark 所需的 long-press、定点 drag、answer 回传。当前有 4 个失败在接口层就不可可靠完成，Verifier 再聪明也救不了。
2. **Runtime State + Loop Detection。** 先处理 `subgoal completed` 与 Loop 的事件顺序，并让已验证的 UI text 变化、subgoal 切换和成功 Recovery 重置无进展计数。这直接对应两个“内容已经改对却被杀掉”的任务。
3. **Subgoal Manager / Completion Evidence。** 约束 subgoal 描述 outcome 而非操作，evidence 必须是动作后的新状态；对 UI text 做格式归一和“当前已满足”检查失败后的受限再提议。

`Recovery` 的统计最难看，但不建议把它排第一：它收到的 frozen subgoal、action space 和 progress state 经常已经错了。先修输入和状态流，再要求 Recovery 根据 Tree 生成不同动作，才可能得到真实增益。

`Progress Verifier` 暂不排前三。现有证据显示它多数能发现 stalled/completed；更急迫的是让 Runtime 正确使用它的结论。

## I. 最小下一步实验建议

以下只是由 RCA 推出的实验，不在本轮实施。

### 实验 1：动作契约可完成性审计

- 假设：至少 4 个失败主要由缺失 long-press、drag、answer 引起，而非 GUI-Plus 视觉能力。
- 改动变量：只增加并验证这三类 AndroidWorld 适配动作；不改 Actor/Manager/Verifier 模型和任务。
- 保持不变：seed、截图输入、Prompt 主体、official reward、任务参数。
- 指标：unsupported action 次数、这 4 题 official success、协议重试是否仍语义改写。
- 否定条件：动作能可靠执行后，Actor仍无法找到目标/答案，或 4 题均无进展。

### 实验 2：先完成子目标，再判断循环

- 假设：VLM/deterministic 已确认 subgoal completed 时，先推进生命周期并重置 stalled streak，可避免 Markor/brightness 的误杀。
- 改动变量：只改同一步事件优先级和 streak reset；不增加 Recovery 次数。
- 保持不变：模型、Prompt、12 步、动作接口。
- 指标：`completed + loop_detected` 同步冲突数应从 2 降到 0；false loop 数、official success、平均动作数。
- 否定条件：冲突消失但 `MarkorAddNoteHeader`、`MarkorEditNote` 仍在相同状态失败，或循环漏检明显增加。

### 实验 3：Evidence 必须是 postcondition

- 假设：禁止把当前已可见控件当 completion evidence，并对电话等文本做归一化，可降低 lifecycle 卡死。
- 改动变量：只改 Manager schema/prompt 和 deterministic evidence normalization。
- 保持不变：Manager 模型、Actor、Verifier、Recovery、步数。
- 指标：`invalid_already_satisfied` 15/50、语义坏 evidence 人工占比、subgoal 完成后任务继续率、Contacts/SmsClipboard 等开发题结果。
- 否定条件：hard reject 降低但 official success 不升，或错误完成率增加。

### 实验 4：Tree-grounded Recovery 最小约束

- 假设：Recovery 候选动作必须引用一个 Tree label/resource-id，并且不能与 blocked action 等价，可减少“触发很多、策略没变”。
- 改动变量：只改 Recovery 输出约束；仍保留两次预算。
- 保持不变：Manager/Verifier/Actor 模型、触发条件、任务和步数。
- 指标：重复 blocked action 从 7/20 episode 降低、changed action 比例、strict rescue、误触发与副作用。
- 否定条件：动作变化增多但 strict rescue 不升，或 Tree 引导造成更多错误点击。

### 实验 5：20 步只做诊断，不做包装

- 假设：`SimpleCalendarAddRepeatingEvent` 是本轮唯一高度疑似被 12 步硬截断的任务。
- 改动变量：只把暴露开发题的 max steps 从 12 调到 20；不调 Prompt/模型/Recovery。
- 保持不变：同一 task params、seed 和代码 commit。
- 指标：12～20 步是否保持单调进展并取得 official reward；额外动作是否只是循环。
- 否定条件：任务仍失败或后 8 步没有可验证进展。
- 结论边界：这个结果只能解释 step budget，不能作为 V2.2 的新 held-out 成绩；新冻结 36 题已经锁定 16 步，不应因本次 RCA 改动。

## 12 步还是 20 步：直接结论

**12 步对复杂表单确实偏紧，但现在不应把冻结评测统一改成 20 步。**

四个 `step_budget_exhausted` 中：

- `SimpleCalendarAddRepeatingEvent`：很可能受益，适合 20 步诊断；
- `ContactsNewContactDraft`：可能多几步偶然完成，但核心是 phone evidence 卡死；
- `MarkorMoveNote`：缺 long-press，20 步无效；
- `SimpleCalendarEventOnDateAtTime`：缺 answer channel，20 步无效。

因此，全局从 12 改 20 会把很多“早已走错”的任务变成更长、更贵的失败，还可能增加危险重复。冻结 36 题已事先固定为 16 步，这是当前更合适的折中，应该保持不变。如果未来重新设计一批评测，可以在看结果前统一固定 20 步，并让 V1/V2.2 使用完全相同上限。

## 去掉工程包装后，V2.2 到底主要死在哪里

1. 四类任务需要的动作或答案通道，当前 Runtime 根本没有完整提供。
2. Actor 到了复杂表单或编辑页后，经常选错字段、点错控件，或者重复同一局部策略。
3. Manager 很会生成合法 JSON，但经常把“按钮已经看得见”误当成“这一步已经完成”。
4. 有些文字其实已经改对，Fingerprint 和 Loop Detection 仍把它当成没有进展。
5. Verifier 多数时候能看出 completed 或 stalled，但 Runtime 没有总是正确执行它的结论。
6. Recovery 经常只是让同一个 Actor再猜一次，7 个 episode 连动作都没有真正换。
7. UI Tree 只有在问题很局部、按钮很明确时才真正救回了任务。
8. 12 步只明显限制了少数长任务，不是 7/20 的主要原因。
9. 普通非法 JSON 已不是最大问题，但“模型想做的动作不在协议里”仍是大问题。
