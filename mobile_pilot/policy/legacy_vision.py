"""把原离线视觉 Agent 接入新 Runtime 的策略 Adapter。"""

from typing import Any

from mobile_pilot.core import ParseResult
from mobile_pilot.legacy import adapt_legacy_output


class LegacyVisionPolicy:
    """复用旧 Agent 的候选动作能力，不赋予它最终成功判定权。"""

    def __init__(self, legacy_agent: Any):
        self._legacy_agent = legacy_agent

    def decide(self, agent_input: Any) -> ParseResult:
        output = self._legacy_agent.act(agent_input)
        return adapt_legacy_output(
            action=output.action,
            parameters=output.parameters,
            raw_output=output.raw_output,
        )
