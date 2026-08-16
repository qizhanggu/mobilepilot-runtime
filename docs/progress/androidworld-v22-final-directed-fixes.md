# AndroidWorld V2.2 最后一轮定向修复

> 角色边界：本文只记录 exposed 20-task development/regression set 上的开发证据；不把结果称为 held-out，也不把协议兼容或 Adapter 补全包装成模型推理提升。

## 修改假设与 RCA 证据

1. **Action Contract**：RCA 中 `MarkorMoveNote`、`SystemBrightnessMax` 和两条 Calendar 查询任务分别缺少长按、定点拖动和正式答案通道。补齐 `LONG_PRESS`、`DRAG(start,end,duration)`、`ANSWER(text)` 后，Runtime 至少能忠实表达模型意图，不再用普通点击冒充。
2. **事件顺序**：`MarkorAddNoteHeader`、`MarkorEditNote` 曾在 Verifier 已确认进展后同一步触发 Loop。可靠完成必须先推进 subgoal 生命周期并清除旧 stalled/page history，再进入下一轮。
3. **Completion Evidence**：旧回归 50 次 Manager 调用中有 15 次 `invalid_already_satisfied`。Evidence 应描述动作后的 postcondition；提前成立时只允许一次带拒绝原因的重生成。电话号码等格式化文本需要稳定归一化。
4. **Tree-grounded Recovery**：Recovery 若声称由 UI Tree 提供新证据，应记录 blocked action、Tree element、是否换动作和最终结果。Tree 无证据时不得随机改动作；只有被冻结任务/子目标明确支持的命名 `OPEN_APP` 可作为可审计 fallback。

## 明确不改

- Actor 固定 `gui-plus-2026-02-26`；Manager/Verifier 固定 `qwen3.7-flash-2026-07-15`。
- 不增加 Planner、Multi-Agent、Memory、新模型或新的 Verifier 分类。
- Recovery 仍为两级有界预算，不增加次数。
- exposed 20 保持 12 action steps；只有 `SimpleCalendarAddRepeatingEvent` 单独做一次 20-step diagnostic。
- frozen 36 在代码锁定前不运行、不看结果、不用于调参。

## 本地与真实环境验证

- 全量 pytest（本轮中间检查）：184 passed；后续以最终锁定提交的实际计数为准。
- AndroidWorld checkout：`3e50888527ef9f29b9157ecd537e408008bb1c85`；ADB 唯一设备为 `emulator-5554`。
- `ANSWER` smoke：Adapter 执行成功，AndroidWorld `interaction_cache` 收到原始文本。
- `DRAG` smoke：在 Launcher 上按像素起点 `(540,1900)` 到终点 `(540,500)`、600ms 执行，截图发生变化，Trace/结果保留完整 payload。
- `MarkorMoveNote`：Actor 两次提出并执行 `LONG_PRESS`，第一次之后为 `meaningful_ui_change`；说明动作缺口已补齐。但 12 步最终仍未完成，根因转为后续目录选择效率，不记作成功。

## 定向开发实验初步结果

- Runtime ordering：`MarkorAddNoteHeader` 与 `MarkorEditNote` 中，`subgoal_completed` 和 `loop_detected` 同 step 冲突均为 0。两题仍失败，说明误杀被修复不等于 Actor 后续决策能力已提升。
- Evidence：`ContactsNewContactDraft` 在 9 actions 后 official reward=1.0、Recovery=0；`SimpleSmsSendClipboardContent` 仍在 12 steps 后失败。Manager 的一次重生成在 Contacts 中仍重复旧 evidence，作为负结果保留。
- 20-step diagnostic：`SimpleCalendarAddRepeatingEvent` 仍为 0.0，20 actions、0 loop、0 recovery。更多步数没有在本次诊断中带来成功，因此不能简单宣称“只差步数”。
- 模型/协议负结果：定向任务仍出现 GUI Plus timeout、空输出和缺失终点的 swipe；Protocol Guard 只做一次未执行动作前的安全重试，不把语义不完整动作猜成点击。

下一步是在相同 12-step exposed 20 上执行一次完整 development regression；结果确认后锁定代码，再生成新的 frozen 36 protocol。
