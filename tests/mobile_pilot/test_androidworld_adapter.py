from types import SimpleNamespace

from PIL import Image
import pytest

from mobile_pilot.androidworld import AndroidWorldAdapter
from mobile_pilot.core import Action, ActionType


@pytest.mark.parametrize(
    ("action", "expected"),
    [
        (Action(ActionType.CLICK_POINT, {"point": [10, 20]}), {"action_type": "click", "x": 10, "y": 20}),
        (Action(ActionType.TYPE_TEXT, {"text": "hello"}), {"action_type": "input_text", "text": "hello"}),
        (Action(ActionType.SWIPE, {"direction": "up"}), {"action_type": "swipe", "direction": "up"}),
        (Action(ActionType.PRESS_BACK), {"action_type": "navigate_back"}),
        (Action(ActionType.OPEN_APP, {"app_name": "Clock"}), {"action_type": "open_app", "app_name": "Clock"}),
        (Action(ActionType.WAIT), {"action_type": "wait"}),
    ],
)
def test_maps_generic_actions_without_importing_androidworld(action, expected):
    mapped = AndroidWorldAdapter.map_action(action)
    assert mapped.payload == expected
    assert not mapped.done


def test_propose_complete_is_not_local_success():
    mapped = AndroidWorldAdapter.map_action(Action(ActionType.PROPOSE_COMPLETE))
    assert mapped.done
    assert mapped.payload is None


def test_open_app_normalizes_display_name_before_androidworld_mapping():
    mapped = AndroidWorldAdapter.map_action(Action(ActionType.OPEN_APP, {"app_name": "The Clock"}))
    assert mapped.payload == {"action_type": "open_app", "app_name": "Clock"}


def test_observe_uses_or_omits_accessibility_elements_by_mode():
    raw_element = SimpleNamespace(
        bbox_pixels=SimpleNamespace(x_min=1, y_min=2, x_max=30, y_max=40),
        resource_id="clock:start",
        resource_name=None,
        text="Start",
        content_description=None,
        class_name="Button",
        is_clickable=True,
        is_enabled=True,
        is_editable=False,
        package_name="com.android.deskclock",
    )
    env = SimpleNamespace(
        get_state=lambda wait_to_stabilize: SimpleNamespace(
            pixels=__import__("numpy").zeros((40, 30, 3), dtype="uint8"), ui_elements=[raw_element]
        )
    )
    adapter = AndroidWorldAdapter(env)
    _, vision_only = adapter.observe(include_ui_tree=False)
    _, v21_context = adapter.observe(
        include_ui_tree=False,
        include_context_signals=True,
    )
    _, hybrid = adapter.observe(include_ui_tree=True)
    assert vision_only.elements == ()
    assert vision_only.package_activity == ""
    assert v21_context.elements == ()
    assert v21_context.package_activity == "com.android.deskclock"
    assert any("Start" in row for row in v21_context.verification_texts)
    assert v21_context.semantic_fingerprint
    assert hybrid.elements[0].text == "Start"
    assert hybrid.elements[0].bounds == (1, 2, 30, 40)
