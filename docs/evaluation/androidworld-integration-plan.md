# AndroidWorld 接入方案（仅设计，尚未部署）

日期：2026-07-24

## 目标与边界

ScreenSpot-v2 只验证单步 grounding；AndroidWorld 用标准模拟器、动态任务参数和程序化成功判定验证多步任务闭环。下一阶段不重写 MobilePilot Runtime，只增加一层官方环境 Adapter。

本文件只完成接入设计，不下载、不安装、不启动 AndroidWorld。

## 接口映射

AndroidWorld 要求自定义 Agent 继承 `EnvironmentInteractingAgent` 并实现 `step()`。每轮由官方循环调用 Agent，Agent从 `AndroidEnv` 读取截图与 UI 元素、选择并执行官方支持的动作，然后返回 `AgentInteractionResult`；`done=true` 表示 Agent提出结束。

建议适配关系：

| AndroidWorld | MobilePilot | 处理方式 |
| --- | --- | --- |
| Task goal | `TaskState.goal` | 每个 episode 初始化一次，不跨任务保留状态 |
| 当前 screenshot | `ScreenState.screenshot` | 作为视觉主输入 |
| Accessibility/UI elements | `ScreenState.ui_elements` | 仅在 `vision_with_tree_aux` 或 Critic/Verifier 按需读取 |
| 官方 action | `Action` | click、type、swipe、back、open app 等做确定性双向映射 |
| `EnvironmentInteractingAgent.step()` | Runtime 单步循环 | 每次只执行一个 observe→decide→critic→act→verify |
| `AgentInteractionResult.done` | `PROPOSE_COMPLETE` | 只表示Agent停止；最终成功仍以AndroidWorld程序化 reward 为准 |
| 官方 task reset/evaluator | 外部评测边界 | 不由MobilePilot替换或修改 |

## 可直接复用的模块

- Actor：`GuiPlusVisionPolicy` 与 `vision_only` / `vision_with_tree_aux`；
- Critic：坐标越界、目标冲突和状态指纹检查；
- Verifier：页面变化、动作结果和局部状态检查，但不能代替官方任务成功判定；
- Recovery：弹窗、键盘、等待、重新观察和有限恢复；
- Trace：继续记录截图哈希、原始模型输出、动作、Verifier与官方 reward；
- DeviceAdapter 抽象：复用数据模型，不直接用当前真机ADB执行；实际动作交给 AndroidWorld `AndroidEnv`。

## 首批10个代表性任务

按“冒烟→输入→状态设置→长任务→跨App”递进，每个任务先只跑一个参数实例：

1. `OpenAppTaskEval`：验证启动App和权限弹窗；
2. `ClockStopWatchRunning`：最短状态变化与完成判断；
3. `SystemWifiTurnOnVerify`：系统设置与官方 verification；
4. `ContactsAddContact`：多字段输入和保存；
5. `ClockTimerEntry`：数字输入且要求“不启动”；
6. `SimpleSmsSend`：联系人/号码查找与文本输入；
7. `SimpleCalendarAddOneEventTomorrow`：日期、时间和多字段表单；
8. `MarkorCreateNote`：文件名、正文和保存；
9. `ExpenseAddSingle`：第三方App中的搜索与结构化录入；
10. `MarkorCreateNoteAndSms`：跨App分享，验证长程任务和恢复。

这10个任务覆盖 easy/medium/hard、系统App/开源App、Text/Icon、表单、日期时间、状态验证和多App，不追求一次覆盖全部116类任务。

## 环境与资源

- 官方推荐 Pixel 6、Android 13/API 33、AVD名 `AndroidWorldAvd`；
- 模拟器需从命令行以 `-grpc 8554` 启动；
- Python 3.11+，建议建立独立 conda 环境，避免污染 MobilePilot 当前环境；
- 需要 `ffmpeg`，首次用 `--perform_emulator_setup` 安装App和权限；
- 官方给出的轻量需求约为2 GB内存、8 GB磁盘，本机额外预留15 GB更稳妥；
- 首批10任务预计150～250次模型调用；按本轮GUI-Plus实测，建议设置 ¥3 API硬上限；
- 预计工作量：环境搭建0.5～1天、Adapter与动作映射1天、10任务调试与报告1～2天。

## 验收节点

1. 官方 `minimal_task_runner.py` 能完成不接入MobilePilot的环境冒烟；
2. MobilePilot Agent Adapter 只跑 `OpenAppTaskEval`，官方 reward 和本地 Trace一致；
3. 冻结 Agent、Prompt、动作映射和10任务清单；
4. 10任务各运行一个参数实例并报告，不把结果写成完整AndroidWorld成绩；
5. 在扩展任务或重复次数前暂停汇报。

最大风险是 Windows 模拟器/gRPC兼容、官方开源App初始化，以及 GUI-Plus 当前输出协议与 AndroidWorld完整动作空间不一致。若环境问题超过一天，应优先使用官方实验性Docker/单独Linux环境，而不是继续改造MobilePilot底层。

官方资料：

- https://github.com/google-research/android_world
- https://google-research.github.io/android_world/task_list.html
