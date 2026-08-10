# AndroidWorld Sprint 12：V2.1 原20题开发结果

日期：2026-08-05

状态：**V2.1 在已暴露20题开发集上仅成功 2/20，明显低于现有 V2 的 9/20。**

## 公平条件

- 任务：`configs/androidworld/held_out_20.json`，现在只作为开发/回归集；
- 模型：`gui-plus-2026-02-26`；
- AndroidWorld commit：`3e50888527ef9f29b9157ecd537e408008bb1c85`；
- mode / seed / 动作上限：`hybrid` / `0` / `12`；
- 设备：唯一 `emulator-5554`；
- 有效产物：`artifacts/evaluation/androidworld-v21-development-20260805/regression-20-step12-network/`。

启动时曾有一次沙箱网络阻断，Planner 和 Actor 全部报 `Connection error`，在两条已记录
运行后立即停止。该目录保留为基础设施证据，不计入成绩；随后在允许 API 访问的新目录
从头完成20题开发运行。

## V2 与 V2.1 开发集结果

| 指标 | V2 | V2.1 |
| --- | ---: | ---: |
| official success | 9/20 | 2/20 |
| 非法输出终止 | 7 | 11 |
| 步数耗尽 | 1 | 0 |
| Recovery 触发 / 救回 | 10 / 3 | 12 / 0 |
| 执行动作 | 112 | 53 |
| VLM 调用 | 144 | 116 |
| Token | 493,719 | 382,727 |
| 目录价成本 | ¥0.7969 | ¥0.6059 |

V2.1 的调用和动作更少主要来自过早失败，不能解释为效率提升。

## 失败根因

1. 92 次 Actor 调用中有 23 次空输出，最终造成 11 个任务以
   `invalid_actor_output` 结束。新 Prompt 和状态协议没有提升输出稳定性。
2. 20 次初始 Planner 中只有 11 次成功解析；7 次输出了自相矛盾的
   `mode=direct` 加非空 checkpoints，2 次没有 JSON。严格解析虽安全，但使 Checklist
   大量退化为 direct fallback。
3. Checklist 实际只在 4 个任务启用；发生 3 次检查点验证，仅确认 1 次。另有 3 个任务
   因没有合法 active checkpoint 却提出检查点完成而终止。
4. Recovery 触发 12 次、救回 0 次；两次计划修改成功执行，但没有转化为 official
   success，另有两次 plan recovery 本身失败。
5. 没有任务因12步耗尽而失败。因此本轮主要问题不是步数上限，而是 Planner/Actor
   协议过重、完成提议状态机过严和空输出处理不足。

## 下一轮最小方向

- 缩短 V2.1 Actor Prompt，不在 direct 模式暴露检查点完成动作；
- 对 Planner 的 `direct + checkpoints` 做无歧义归一化：有 checkpoints 即按 checklist
  解析，而不是整份计划丢弃；
- Checklist 全部确认后，只允许整题完成提议，不把重复检查点提议当成致命协议错误；
- 将 Planner 失败视为可审计的 direct fallback，不占用 Agent Recovery；
- 保持12步重新跑开发集，确认提升来自 Runtime 修改；最终新评测再让 V1/V2.1 统一使用
  18步。

本结果必须保留，不能写成 V2.1 已经提升成功率，也不能进入简历正向数字。
