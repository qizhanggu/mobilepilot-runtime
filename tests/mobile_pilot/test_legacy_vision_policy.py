from types import SimpleNamespace

from mobile_pilot.core import ActionType, ErrorKind
from mobile_pilot.policy import LegacyVisionPolicy


class FakeLegacyAgent:
    def __init__(self, output):
        self.output = output

    def act(self, _agent_input):
        return self.output


def test_legacy_vision_policy_adapts_candidate_action():
    output = SimpleNamespace(
        action="CLICK",
        parameters={"point": [100, 200]},
        raw_output='Action: CLICK | {"point": [100, 200]}',
    )

    result = LegacyVisionPolicy(FakeLegacyAgent(output)).decide(object())

    assert result.is_success
    assert result.action.type is ActionType.CLICK_POINT


def test_legacy_vision_policy_preserves_model_error():
    output = SimpleNamespace(action="COMPLETE", parameters={}, raw_output="Error: timeout")

    result = LegacyVisionPolicy(FakeLegacyAgent(output)).decide(object())

    assert not result.is_success
    assert result.error_kind is ErrorKind.MODEL_ERROR
