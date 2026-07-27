from mobile_pilot.androidworld import parse_androidworld_actor_output
from mobile_pilot.core import ActionType, ErrorKind


def test_parses_normalized_click_into_screenshot_pixels():
    result = parse_androidworld_actor_output('{"action":"CLICK","coordinate":[500,250],"reason":"tap"}', (1080, 2400))
    assert result.is_success
    assert result.action.type is ActionType.CLICK_POINT
    assert result.action.parameters["point"] == [540, 600]
    assert result.action.parameters["coordinate_space"] == "normalized_1000"


def test_parses_main_model_image_pixel_click_and_trims_action_name():
    result = parse_androidworld_actor_output('{"action":" CLICK","coordinate":[690,2241]}', (1080, 2400))
    assert result.is_success
    assert result.action.parameters["point"] == [690, 2241]
    assert result.action.parameters["coordinate_space"] == "image_pixels"


def test_parses_non_click_action():
    result = parse_androidworld_actor_output('{"action":"TYPE","text":"Alice","reason":"fill form"}', (1080, 2400))
    assert result.is_success
    assert result.action.type is ActionType.TYPE_TEXT
    assert result.action.parameters["text"] == "Alice"


def test_rejects_invalid_actor_json_without_fallback():
    result = parse_androidworld_actor_output('{"action":"CLICK","coordinate":[1080,2400]}', (1080, 2400))
    assert not result.is_success
    assert result.error_kind is ErrorKind.PARSE_ERROR


def test_recovers_click_when_only_optional_reason_has_unescaped_quotes():
    raw = '{"action":"CLICK","coordinate":[100,200],"reason":"tap the "1" button"}'
    result = parse_androidworld_actor_output(raw, (1080, 2400))
    assert result.is_success
    assert result.action.type is ActionType.CLICK_POINT
    assert result.action.parameters["point"] == [108, 480]


def test_recovers_truncated_but_complete_click_fields():
    result = parse_androidworld_actor_output('{"action":"CLICK","coordinate":[500,250]', (1080, 2400))
    assert result.is_success
    assert result.action.parameters["point"] == [540, 600]
