"""Phase 0：新 Runtime 与旧竞赛 Agent 的协议兼容测试。"""

from mobile_pilot.core import ActionType, ErrorKind, TaskStatus
from mobile_pilot.legacy import adapt_legacy_output


def test_explicit_legacy_complete_is_only_a_proposal():
    result = adapt_legacy_output("COMPLETE", {}, "Thought: done\nAction: COMPLETE | {}")

    assert result.is_success
    assert result.action.type is ActionType.PROPOSE_COMPLETE
    assert result.action.type.value != TaskStatus.SUCCEEDED.value


def test_parser_fallback_complete_is_not_treated_as_success():
    result = adapt_legacy_output("COMPLETE", {}, "I cannot decide what to do")

    assert not result.is_success
    assert result.error_kind is ErrorKind.PARSE_ERROR


def test_legacy_agent_error_is_not_treated_as_success():
    result = adapt_legacy_output("COMPLETE", {}, "Error: network timeout")

    assert not result.is_success
    assert result.error_kind is ErrorKind.MODEL_ERROR


def test_legacy_click_remains_compatible_with_new_runtime():
    result = adapt_legacy_output(
        "CLICK",
        {"point": [321, 654]},
        'Action: CLICK | {"point": [321, 654]}',
    )

    assert result.is_success
    assert result.action.type is ActionType.CLICK_POINT
    assert result.action.parameters == {"point": [321, 654]}
