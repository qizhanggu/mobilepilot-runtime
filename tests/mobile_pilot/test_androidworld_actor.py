from mobile_pilot.androidworld import parse_androidworld_actor_output
from mobile_pilot.androidworld.download_cache import _safe_name
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


def test_download_cache_rejects_paths_outside_cache_directory():
    import pytest

    with pytest.raises(ValueError):
        _safe_name("../not-an-apk")


def test_uses_explicit_swipe_reason_only_when_direction_field_is_missing():
    result = parse_androidworld_actor_output(
        '{"action":"SWIPE","coordinate":[500,700],"reason":"Swipe up to access the drawer"}',
        (1080, 2400),
    )
    assert result.is_success
    assert result.action.type is ActionType.SWIPE
    assert result.action.parameters["direction"] == "up"


def test_uses_first_complete_json_action_when_model_emits_a_second_one():
    result = parse_androidworld_actor_output(
        '{"action":"TYPE","text":"179.68"}\n{"action":"PROPOSE_COMPLETE"}',
        (1080, 2400),
    )
    assert result.is_success
    assert result.action.type is ActionType.TYPE_TEXT
    assert result.action.parameters["text"] == "179.68"
