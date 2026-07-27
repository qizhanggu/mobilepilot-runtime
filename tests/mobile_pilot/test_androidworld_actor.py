from mobile_pilot.androidworld import parse_androidworld_actor_output
from mobile_pilot.core import ActionType, ErrorKind


def test_parses_normalized_click_into_screenshot_pixels():
    result = parse_androidworld_actor_output('{"action":"CLICK","coordinate":[500,250],"reason":"tap"}', (1080, 2400))
    assert result.is_success
    assert result.action.type is ActionType.CLICK_POINT
    assert result.action.parameters["point"] == [540, 600]


def test_parses_non_click_action():
    result = parse_androidworld_actor_output('{"action":"TYPE","text":"Alice","reason":"fill form"}', (1080, 2400))
    assert result.is_success
    assert result.action.type is ActionType.TYPE_TEXT
    assert result.action.parameters["text"] == "Alice"


def test_rejects_invalid_actor_json_without_fallback():
    result = parse_androidworld_actor_output('{"action":"CLICK","coordinate":[1001,0]}', (1080, 2400))
    assert not result.is_success
    assert result.error_kind is ErrorKind.PARSE_ERROR
