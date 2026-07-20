# Phase 0 基线与协议迁移记录

日期：2026-07-20

## 已核实的原项目基线

- 原项目是“离线截图 + 自然语言指令 → 单步 GUI 动作”的视觉决策器。
- `test_runner.py` 从 `test_data/offline/` 的 `ref.json` 状态图读取允许的动作转移，不会连接真实 Android 设备。
- 原始动作协议为 `CLICK`、`TYPE`、`SCROLL`、`OPEN`、`COMPLETE`，坐标为 `[0, 1000]` 归一化空间。
- 网络无关测试覆盖输出解析、视觉网格和坐标后处理；在本次改造开始前实际运行结果为 `11 passed`。
- 离线 API 评测需要真实模型 Key，未将其结果伪造为已验证指标。

## 发现的问题

旧 `OutputParser` 在自由文本无法解析时返回 `COMPLETE`；`Agent.act()` 捕获到模型或基础设施异常后也返回 `COMPLETE`。在比赛离线 Runner 中这相当于终止当前路径，但在真实 Runtime 中会错误地把“模型/解析失败”与“用户目标完成”混为一谈。

## Phase 0 新增协议

新增 `mobile_pilot/`，不改动可能被竞赛环境替换的 `agent_base.py`：

- `TaskStatus` 明确区分 `SUCCEEDED`、`MODEL_ERROR`、`DEVICE_ERROR`、`POLICY_BLOCKED` 等终态；
- `ActionType.PROPOSE_COMPLETE` 仅代表策略建议完成，不能直接等价于 `SUCCEEDED`；
- `ParseResult` 显式表示 `EMPTY_OUTPUT`、`PARSE_ERROR`、`UNKNOWN_ACTION`、`MODEL_ERROR`；
- `adapt_legacy_output()` 将旧动作适配为新动作，并识别旧解析器的 `COMPLETE` 兜底。

最终成功判断将由后续 Phase 3 的 Verifier 根据确定性成功条件完成。

## 兼容策略

原 `agent.py`、`agent_base.py`、`utils/output_parser.py` 和 `test_runner.py` 原样保留，以维持离线竞赛能力。新代码仅通过兼容层读取旧 Agent 输出，因此后续接入真机 Runtime 不会改变旧评测协议。
