# Architecture

## Runtime boundary

当前系统负责从手机截图生成下一步标准动作。截图来自离线评测器；未来接入真实设备时，设备执行器只需消费相同的 `AgentOutput`，无需改变视觉决策接口。

```text
AgentInput
  ├─ instruction
  ├─ current_image
  ├─ step_count
  └─ history_actions
        │
        ▼
Grid Overlay → Prompt Builder → Vision Model → Output Parser
                                                │
                                                ▼
                              Coordinate Post-processing
                                                │
                                                ▼
                                      AgentOutput(action, params)
```

## Components

### `agent_base.py`

定义 `AgentInput`、`AgentOutput`、动作常量以及统一的模型调用入口。评测环境通过该层固定 API 地址和模型配置。

### `agent.py`

负责指令信息提取、视觉网格、文本历史、消息构造、坐标后处理和异常降级。每次 `act()` 只产生一个动作。

### `utils/output_parser.py`

将视觉模型自由文本解析为稳定的动作协议。解析器先尝试高置信度格式；如果无法可靠确定动作，返回安全终止动作而不是猜测坐标。

### `test_runner.py`

从 `ref.json` 加载状态图，根据 Agent 动作匹配允许的状态转移，并记录步骤级和任务级结果。

## State and memory

模型请求本身保持单轮。Agent 通过 `history_actions` 接收外部历史，并将 Thought 与 Action 合并成文本叙事。内部 `_step_thoughts` 保存已经生成的简短推理摘要，在每个任务开始时由 `reset()` 清空。

## Coordinate contract

所有动作使用 `[0, 1000]` 归一化坐标。该约定把不同手机分辨率转换成统一决策空间，也让视觉网格刻度与模型输出直接对应。

