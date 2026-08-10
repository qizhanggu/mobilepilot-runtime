# AndroidWorld Sprint 14：V2.2 子目标与 Progress Verifier 施工记录

日期：2026-08-09

状态：**最小代码闭环和本地自动化测试已完成；完整仓库测试 154/154 通过，并完成一次
无设备的 Qwen 合成图片 API 冒烟。尚未连接模拟器或运行 AndroidWorld 真实任务，因此没有
新的成功率结论。**

## 为什么另起 V2.2

V2.1 已经真实运行过，采用的是“开场 Planner 生成 Checklist”方案。在已暴露 20 题开发集
上，它经过协议修复后为 5/20，仍低于 V2 的 9/20。为了保留这段负结果和对应 Trace，本轮
不覆盖 V2.1，而将“无 Planner、Actor 提出单个子目标”的新方案记为 V2.2。

## 本轮假设

独立 Planner 会增加一次模型调用和一套额外协议，而且错误计划可能从任务开头就限制 Actor。
V2.2 改为：Actor 在正常动作中顺便提出当前小目标及完成证据，Runtime 接受后固定其生命周期。
这样不要求 Actor 一开始猜完整路线，但 Recovery 仍然有一个明确的“当前做到哪里”作为抓手。

初版 Completion Evidence 只有三类：

1. `package_activity`：目标 App 或页面上下文；
2. `ui_text`：Runtime 可见文本，不把完整 Tree 每步塞给 Actor；
3. `visual_state`：前两类无法表达时，交给事件触发的 VLM Progress Verifier。

## 真实代码行为

- V2.1 Planner/Checklist 路径保持不变，V2.2 不调用 Planner；
- Actor 可以随正常动作附带 `subgoal + completion_evidence`，不额外消耗一个动作或一次
  Planner 调用；
- Runtime 接受后冻结目标和证据。没有 Recovery 授权时，Actor 后续提出的新目标只会被记录并
  阻止修改，不直接把正常动作判成非法输出；
- `package_activity`、`ui_text`、截图精确指纹、视觉相似度、页面上下文和执行结果属于第一层
  确定性检查；
- `qwen3.7-flash-2026-07-15` 只在 `visual_state`、上下文跳转、连续无进展或 Actor 提议子目标
  完成等事件中调用；
- VLM 输入为整道任务总目标、执行前截图、Action、执行后截图、冻结子目标及证据。总目标仅作为
  方向校准的只读上下文，Verifier 不得改写目标、修改子目标或自行规划；关闭 thinking，并强制短 JSON；
- VLM 只输出 `progress / completed / stalled / regressed / uncertain` 和处置建议，不产生坐标
  或手机动作；
- 硬证据优先。若 `ui_text` 或 `package_activity` 明确不满足，VLM 的 `completed` 不能推翻它；
- Recovery 预算仍为两层：第一次换动作，第二次才允许修改当前子目标；没有增加第三次机会；
- 子目标完成不等于整题成功，AndroidWorld official reward 仍是唯一最终成功判定。

## Trace 与成本审计

新增事件包括：

- `subgoal_proposal`：接受、重复、阻止修改或 Recovery 修订；
- `deterministic_progress_verifier`：硬证据匹配情况；
- `vlm_progress_verifier`：触发原因、五分类、处置建议、Token、延迟和估算成本；
- `subgoal_completed`：证据来源及确认内容。

每次 VLM Verifier 触发时，动作前后截图保存到对应 Trace 旁的
`*.verifier-media/` 目录，便于后续人工标注和模型选型，不再只留下无法复查的哈希。

## 后续 A/B/C 开发消融

同一批已暴露开发题、同一 Actor、seed 和动作预算下分别运行：

- A：V2，现有 Runtime 基线；
- B：V2.2 + 固定 Subgoal + 确定性 Verifier，`--progress-verifier-mode off`；
- C：V2.2 完整版，`--progress-verifier-mode hybrid`。

重点比较 official success、非法输出、步数耗尽、循环、Recovery 触发/救回、子目标确认、危险
误判、调用数、Token、延迟和成本。A/B/C 都属于开发消融；在开发结论稳定前不触碰新的冻结集。

## API 冒烟结果

使用 `scripts/smoke_androidworld_progress_verifier.py` 生成两张合成小图：前图为联系人列表，
后图为包含 Name、Phone 和 Save 的编辑页。固定模型返回：

- verdict：`completed`；
- disposition：`confirm_subgoal`；
- Token：494 input + 56 output = 550；
- 延迟：2.68 秒；
- 目录价估算：¥0.0001436。

这只证明当前账号、Endpoint、固定模型、多图输入、关闭 thinking 和结构化 JSON 调用链可用，
不证明真实 AndroidWorld 判断准确率。第一次用系统 Python 运行时因缺少 `openai` SDK 失败；改用
项目既有的 `.local/conda/androidworld-py312` 环境后成功，没有安装或修改系统级环境。

## 当前证据边界

自动化测试和合成图冒烟能证明状态机、模型请求参数、事件触发、安全边界及 API 链路按设计工作，
不能证明任务成功率已经提升。旧 AndroidWorld Trace 没有保存截图，因此无法直接构造 Verifier
样本；模拟器恢复后应从已暴露开发任务补采少量动作前后对，检查危险误判，再做 A/B/C 开发消融。

本轮尝试启动唯一允许的 `AndroidWorldAvd` 时，Android Emulator 36.6.11 在启动前拒绝当前
HAXM 加速环境，提示 HAXM 已不受支持并要求 WHPX；`-accel off` 同样在兼容性检查阶段退出。
没有任何设备上线，也没有执行 Android 动作。当时尚未获得修改虚拟化环境的明确授权，因此没有
继续启用 WHPX。AndroidWorld checkout commit 已用一次性
`safe.directory` 参数只读确认，仍为 `3e50888527ef9f29b9157ecd537e408008bb1c85`。

用户的 VMware Workstation 虚拟机用于面试，属于必须保护的本机环境。经用户明确授权，可以启用
Android Emulator 所需的 WHPX，但应先确认 VMware 版本并在重启后优先验证面试虚拟机；不以破坏
VMware 可用性为代价恢复 Android Emulator。

2026-08-10 重启后，`emulator -accel-check` 返回 `WHPX(10.0.19045) is installed and usable`，
`AndroidWorldAvd` 在固定端口 `5554/8554` 完整开机，ADB 中唯一设备为 `emulator-5554`。
首条 V2.2 真实开发冒烟 `SystemBluetoothTurnOn` 官方 reward 为 0：Actor 主调用和一次安全协议重试
均返回空内容，未执行任何 Android 动作。Trace 保存在新的 `androidworld-v22-smoke-20260810`
目录，未覆盖历史产物。GUI Plus 官方接口说明固定模型属于混合思考模型；本轮据此显式关闭 Actor、
V2.1 Planner 和旧 Checkpoint Verifier 的 thinking，以减少短 JSON 输出链路的不确定性。该调整属于
协议可靠性假设，不属于 Agent 推理能力提升；仍需用不同开发题做真实验证。

随后用不同开发题 `SystemWifiTurnOff` 验证该假设，官方 reward 仍为 0。四次 Actor 调用中有三次
空输出；一次 Protocol Guard 重试成功得到 `SWIPE down` 并执行。Runtime 冻结“打开快捷设置”子目标，
Qwen Progress Verifier 根据前后截图、总目标和子目标返回 `completed`，确认了这个局部子目标，
但下一决策及其安全重试均为空输出，任务以 `invalid_actor_output` 终止。因此显式关闭 thinking
只固定了请求模式，**没有证明能够消除空输出**；当前真实阻塞仍是 GUI Plus 的动作输出可靠性，
本次也没有出现“失败信号 → Agent Recovery → 官方成功”。
