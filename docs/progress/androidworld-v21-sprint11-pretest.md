# AndroidWorld Sprint 11：V2.1 测试前冻结说明

日期：2026-08-05

状态：**代码与测试用例已实现；相关测试 59/59、完整 MobilePilot 测试 125/125
通过；尚未执行模拟器任务或模型评测。**

## 这次要解决什么

V2 能修一部分输出协议错误，也能在重复动作时尽早止损，但它没有显式的整体任务计划，
Verifier 只知道截图是否变化，单次 Recovery 也不会检查“当前路线本身是不是错了”。V2.1
的目标不是增加视觉定位技巧，而是让 Runtime 在长任务失败后更会管理状态和换路线。

## V2.1 最小假设

对于包含多个字段、跨页面、查找指定对象、保存/提交或不可重复副作用的任务，维护一份
带完成证据的短 Checklist；Actor 每次只处理当前检查点。若动作级换招仍失败，再允许一次
计划级修订。预期它主要减少任务中途跑偏、重复危险动作和错误推进，而不保证单步视觉
识别本身变强。

风险包括 Planner 生成错误检查点、额外 VLM 调用增加成本、检查点过严导致短任务退化，
以及页面信号改善但官方 reward 不提升。所有风险都必须由配对 Trace 和官方 reward 判断。

## 已实现的运行时行为

1. `PlanState` 维护 direct/checklist 模式、已确认/当前/剩余检查点和冻结证据。Planner 按
   任务结构决定是否启用 Checklist，不按预计点击次数机械分档。
2. Actor 只能输出 `PROPOSE_CHECKPOINT_COMPLETE`。Runtime 先用 UI Tree 文本或
   package/activity 等确定性证据确认；证据仍模糊时才调用受约束 Verifier。Actor 不能
   给自己判完成。
3. 保留截图字节级 SHA-256，同时增加裁掉系统栏后的轻量视觉指纹、UI Tree 语义摘要和
   package/activity 信号。Verifier 区分完全相同、视觉近似、有效 UI 变化和上下文跳转；
   “页面变了”仍不等于“任务做对了”。
4. Recovery 最多两次：第一次保持当前检查点，只换安全动作；第二次保留已确认检查点，
   修订当前和剩余计划。两次均失败后停止，不继续猜测性重复。
5. AndroidWorld official reward 仍是整题唯一成功判定。检查点确认只代表局部进度。

## 新冻结配对集

清单：`configs/androidworld/runtime_eval_12_v21.json`

- 对照：未修改行为的 V2.0 vs V2.1；
- 模型：两版均为 `gui-plus-2026-02-26`；
- AndroidWorld：固定 commit `3e50888527ef9f29b9157ecd537e408008bb1c85`；
- mode / seed / 步数：`hybrid` / `0` / `12`；
- 12 个任务均未出现在已有开发或冻结清单中；
- 避开已知 Notes/Joplin 初始化问题以及此前暴露的任务；
- 不单题重试，不根据结果改 Prompt、策略或任务清单。

## 必须统计

- official success、非法输出终止、步数耗尽和失败 taxonomy；
- 循环信号与四类页面变化信号；
- 动作级/计划级 Recovery 触发、修订、救回和误触发；
- Checklist 创建、检查点确认/拒绝和按需 UI Tree 使用；
- Actor、Planner、Checkpoint Verifier 的调用数、Token、延迟和目录价成本；
- 平均执行动作数。

## 测试前停止点

本 Sprint 已完成实现、测试代码、冻结协议和本地单元测试。相关模块测试为 59/59，完整
`tests/mobile_pilot` 为 125/125。尚未连接模拟器、调用模型或生成新实验结果，因此不能写
“V2.1 已提升成功率”。下一步应先做少量开发回归，确认真实运行链路，再对冻结清单只跑
一次公平配对评测。
