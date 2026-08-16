from mobile_pilot.androidworld import parse_androidworld_actor_output
from types import SimpleNamespace

from PIL import Image

from mobile_pilot.androidworld.actor import (
    AndroidWorldActorRequest,
    AndroidWorldGuiPlusPolicy,
    _actor_prompt,
    parse_androidworld_plan,
)
from mobile_pilot.androidworld.adapter import AndroidWorldTaskState
from mobile_pilot.androidworld.runtime_state import (
    Checkpoint,
    CheckpointEvidence,
    PlanState,
)
from mobile_pilot.androidworld.download_cache import _safe_name
from mobile_pilot.core import ActionType, ErrorKind
from mobile_pilot.perception import ScreenState


class _RecordingCompletions:
    def __init__(self):
        self.requests = []

    def create(self, **request):
        self.requests.append(request)
        return SimpleNamespace(
            choices=[
                SimpleNamespace(
                    message=SimpleNamespace(
                        content='{"action":"WAIT","reason":"test"}'
                    )
                )
            ],
            usage=SimpleNamespace(
                prompt_tokens=10,
                completion_tokens=5,
                total_tokens=15,
            ),
        )


class _RecordingClient:
    def __init__(self, completions):
        self.chat = SimpleNamespace(completions=completions)


def test_androidworld_actor_explicitly_disables_gui_plus_thinking():
    completions = _RecordingCompletions()
    policy = AndroidWorldGuiPlusPolicy(
        api_key="test",
        base_url="https://example.invalid/v1",
        client_factory=lambda **_: _RecordingClient(completions),
    )
    request = AndroidWorldActorRequest(
        task=AndroidWorldTaskState(
            goal="turn bluetooth on",
            step_index=0,
            remaining_steps=12,
            runtime_version="v2.2",
        ),
        image=Image.new("RGB", (20, 30), "white"),
        screen=ScreenState((20, 30), "launcher", (), "fingerprint"),
        include_ui_tree=False,
    )

    result = policy.decide_with_metrics(request)

    assert result.result.is_success
    assert completions.requests[0]["extra_body"] == {
        "vl_high_resolution_images": True,
        "enable_thinking": False,
    }


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


def test_normalizes_unambiguous_swipe_direction_alias():
    result = parse_androidworld_actor_output(
        '{"action":"SWIPE","direction":"swipe_up","reason":"open drawer"}',
        (1080, 2400),
    )
    assert result.is_success
    assert result.action.type is ActionType.SWIPE
    assert result.action.parameters["direction"] == "up"


def test_accepts_press_back_alias():
    result = parse_androidworld_actor_output(
        '{"action":"PRESS_BACK","reason":"dismiss the panel"}',
        (1080, 2400),
    )
    assert result.is_success
    assert result.action.type is ActionType.PRESS_BACK


def test_uses_first_complete_json_action_when_model_emits_a_second_one():
    result = parse_androidworld_actor_output(
        '{"action":"TYPE","text":"179.68"}\n{"action":"PROPOSE_COMPLETE"}',
        (1080, 2400),
    )
    assert result.is_success
    assert result.action.type is ActionType.TYPE_TEXT
    assert result.action.parameters["text"] == "179.68"


def test_v2_repairs_unambiguous_click_with_one_missing_bracket_only_when_enabled():
    raw = '{"action":"CLICK","coordinate":937,606,"reason":"tap send"}'

    v1 = parse_androidworld_actor_output(raw, (1080, 2400))
    v2 = parse_androidworld_actor_output(
        raw,
        (1080, 2400),
        allow_v2_repairs=True,
    )

    assert not v1.is_success
    assert v2.is_success
    assert v2.action.type is ActionType.CLICK_POINT
    assert v2.action.parameters["point"] == [1011, 1454]


def test_v2_repairs_open_app_when_only_optional_reason_breaks_json():
    raw = (
        '{"action":"OPEN_APP","app_name":"markor",'
        '"reason":"open "markor" directly"}'
    )

    result = parse_androidworld_actor_output(
        raw,
        (1080, 2400),
        allow_v2_repairs=True,
    )

    assert result.is_success
    assert result.action.type is ActionType.OPEN_APP
    assert result.action.parameters["app_name"] == "markor"


def test_v2_does_not_guess_malformed_type_text():
    result = parse_androidworld_actor_output(
        '{"action":"TYPE","text":"unsafe',
        (1080, 2400),
        allow_v2_repairs=True,
    )

    assert not result.is_success


def test_v2_parses_explicit_ui_tree_tool_request():
    result = parse_androidworld_actor_output(
        '{"action":"REQUEST_UI_TREE","reason":"labels are unreadable"}',
        (1080, 2400),
        allow_v2_repairs=True,
    )

    assert result.is_success
    assert result.action.type is ActionType.CALL_TOOL
    assert result.action.parameters == {"tool": "ui_tree"}


def test_classifies_empty_and_unknown_outputs_for_failure_taxonomy():
    empty = parse_androidworld_actor_output("", (1080, 2400))
    unknown = parse_androidworld_actor_output(
        '{"action":"SAVE","reason":"unsupported direct save"}',
        (1080, 2400),
    )

    assert empty.error_kind is ErrorKind.EMPTY_OUTPUT
    assert unknown.error_kind is ErrorKind.UNKNOWN_ACTION


def test_v22_parses_bounded_long_press_drag_and_answer_actions():
    long_press = parse_androidworld_actor_output(
        '{"action":"LONG_PRESS","coordinate":[500,250]}',
        (1080, 2400),
        allow_v22_actions=True,
    )
    drag = parse_androidworld_actor_output(
        '{"action":"DRAG","start_coordinate":[100,200],'
        '"end_coordinate":[900,800],"duration_ms":750}',
        (1080, 2400),
        allow_v22_actions=True,
    )
    answer = parse_androidworld_actor_output(
        '{"action":"ANSWER","text":"42"}',
        (1080, 2400),
        allow_v22_actions=True,
    )

    assert long_press.action.type is ActionType.LONG_PRESS
    assert long_press.action.parameters["point"] == [540, 600]
    assert drag.action.type is ActionType.DRAG
    assert drag.action.parameters["start_point"] == [108, 480]
    assert drag.action.parameters["end_point"] == [971, 1919]
    assert drag.action.parameters["duration_ms"] == 750
    assert answer.action.type is ActionType.ANSWER
    assert answer.action.parameters["text"] == "42"


def test_v22_semantic_actions_are_version_gated_and_not_misclassified_as_json_errors():
    unsupported = parse_androidworld_actor_output(
        '{"action":"ANSWER","text":"visible answer"}', (1080, 2400)
    )
    invalid_drag = parse_androidworld_actor_output(
        '{"action":"DRAG","start_coordinate":[100,100],'
        '"end_coordinate":[100,100]}',
        (1080, 2400),
        allow_v22_actions=True,
    )

    assert unsupported.error_kind is ErrorKind.UNSUPPORTED_ACTION_CAPABILITY
    assert invalid_drag.error_kind is ErrorKind.PARSE_ERROR


def test_v22_normalizes_explicit_point_to_point_swipe_as_drag_without_guessing():
    result = parse_androidworld_actor_output(
        '{"action":"SWIPE","start_coordinate":[500,850],'
        '"end_coordinate":[500,150],"duration_ms":800}',
        (1080, 2400),
        allow_v22_actions=True,
    )

    assert result.is_success
    assert result.action.type is ActionType.DRAG
    assert result.action.parameters["start_point"] == [540, 2039]
    assert result.action.parameters["end_point"] == [540, 360]
    assert result.action.parameters["duration_ms"] == 800


def test_v2_preserves_actor_subgoal_and_expected_outcome_for_runtime_state():
    result = parse_androidworld_actor_output(
        '{"action":"CLICK","coordinate":[500,500],'
        '"subgoal":"open the contact editor",'
        '"expected_outcome":"the edit form becomes visible"}',
        (1080, 2400),
        allow_v2_repairs=True,
    )

    assert result.is_success
    assert result.action.parameters["subgoal"] == "open the contact editor"
    assert result.action.expected_outcome == "the edit form becomes visible"


def test_v2_normalizes_explicit_gui_plus_open_app_system_function_only():
    raw = (
        '{"action":"SYSTEM_FUNCTION","function_name":"open_app",'
        '"app_name":"clock","reason":"open the named app"}'
    )

    v1 = parse_androidworld_actor_output(raw, (1080, 2400))
    v2 = parse_androidworld_actor_output(
        raw,
        (1080, 2400),
        allow_v2_repairs=True,
    )
    unsupported = parse_androidworld_actor_output(
        '{"action":"SYSTEM_FUNCTION","function_name":"unknown_tool"}',
        (1080, 2400),
        allow_v2_repairs=True,
    )

    assert not v1.is_success
    assert v2.is_success
    assert v2.action.type is ActionType.OPEN_APP
    assert v2.action.parameters["app_name"] == "clock"
    assert not unsupported.is_success


def test_v21_checkpoint_proposal_is_explicitly_version_gated():
    raw = (
        '{"action":"PROPOSE_CHECKPOINT_COMPLETE",'
        '"observed_evidence":"Save button is visible"}'
    )

    v2 = parse_androidworld_actor_output(raw, (1080, 2400), allow_v2_repairs=True)
    v21 = parse_androidworld_actor_output(
        raw,
        (1080, 2400),
        allow_v2_repairs=True,
        allow_v21_actions=True,
    )

    assert not v2.is_success
    assert v21.is_success
    assert v21.action.type is ActionType.PROPOSE_CHECKPOINT_COMPLETE
    assert v21.action.parameters["observed_evidence"] == "Save button is visible"


def test_v21_planner_parses_verifiable_checklist_without_actions():
    plan = parse_androidworld_plan(
        '{"mode":"checklist","reason":"multiple fields and save",'
        '"checkpoints":['
        '{"goal":"open editor","evidence":{"kind":"ui_text","value":"Save"}},'
        '{"goal":"fill details","evidence":{"kind":"ui_state","value":"Team sync"}}]}'
    )

    assert plan.mode == "checklist"
    assert plan.active.goal == "open editor"
    assert plan.active.evidence.value == "Save"
    assert plan.remaining_goals() == ("fill details",)


def test_v21_planner_preserves_unambiguous_checkpoints_mislabeled_as_direct():
    plan = parse_androidworld_plan(
        '{"mode":"direct","reason":"model mislabeled the mode",'
        '"checkpoints":[{"goal":"open editor",'
        '"evidence":{"kind":"ui_element","value":"Save button visible"}}]}'
    )

    assert plan.mode == "checklist"
    assert plan.active.goal == "open editor"
    assert plan.active.evidence.kind == "visual"


def test_v21_recovery_reuses_frozen_evidence_for_same_unfinished_goal():
    original = PlanState(
        mode="checklist",
        checkpoints=[
            Checkpoint(
                "open editor",
                CheckpointEvidence("ui_text", "Save"),
                "active",
            )
        ],
    )

    revised = parse_androidworld_plan(
        '{"mode":"checklist","reason":"keep goal but revise route",'
        '"checkpoints":[{"goal":"open editor","evidence":{}}]}',
        require_checklist=True,
        fallback_plan=original,
    )

    assert revised.active.evidence == CheckpointEvidence("ui_text", "Save")


def test_v21_actor_only_sees_checkpoint_action_when_a_checkpoint_is_active():
    direct = AndroidWorldTaskState(
        goal="wait", step_index=0, remaining_steps=2, runtime_version="v2.1"
    )
    checklist = AndroidWorldTaskState(
        goal="create event",
        step_index=0,
        remaining_steps=8,
        runtime_version="v2.1",
        plan_mode="checklist",
        active_checkpoint="open editor",
        active_checkpoint_evidence="ui_text: Save",
    )

    assert "PROPOSE_CHECKPOINT_COMPLETE" not in _actor_prompt(direct)
    assert "PROPOSE_CHECKPOINT_COMPLETE" in _actor_prompt(checklist)


def test_v22_parses_subgoal_completion_evidence_and_completion_proposal():
    action = parse_androidworld_actor_output(
        '{"action":"OPEN_APP","app_name":"messages",'
        '"subgoal":"open messages","completion_evidence":'
        '{"kind":"package_activity","value":"messages"}}',
        (1080, 2400),
        allow_v2_repairs=True,
        allow_v22_actions=True,
    )
    completion = parse_androidworld_actor_output(
        '{"action":"PROPOSE_SUBGOAL_COMPLETE",'
        '"observed_evidence":"Messages is foreground"}',
        (1080, 2400),
        allow_v2_repairs=True,
        allow_v22_actions=True,
    )

    assert action.is_success
    assert action.action.parameters["subgoal"] == "open messages"
    assert action.action.parameters["completion_evidence_kind"] == "package_activity"
    assert action.action.parameters["completion_evidence_value"] == "messages"
    assert completion.is_success
    assert completion.action.type is ActionType.PROPOSE_SUBGOAL_COMPLETE


def test_v22_parses_action_only_mobile_tool_call_and_keeps_legacy_json_compatible():
    tool_call = parse_androidworld_actor_output(
        '<tool_call>{"name":"mobile_action","arguments":'
        '{"action":"swipe","direction":"down","reason":"open shade"}}'
        '</tool_call>',
        (1080, 2400),
        allow_v2_repairs=True,
        allow_v22_actions=True,
    )
    legacy = parse_androidworld_actor_output(
        '{"action":"SWIPE","direction":"down"}',
        (1080, 2400),
        allow_v2_repairs=True,
        allow_v22_actions=True,
    )

    assert tool_call.is_success and legacy.is_success
    assert tool_call.action.type is ActionType.SWIPE
    assert tool_call.action.parameters["direction"] == "down"


def test_v22_prompt_keeps_actor_action_only_with_runtime_owned_subgoal():
    task = AndroidWorldTaskState(
        goal="reply to the message",
        step_index=2,
        remaining_steps=8,
        runtime_version="v2.2",
        active_subgoal="open the target conversation",
        active_subgoal_evidence="ui_text: Zhang San",
    )

    prompt = _actor_prompt(task)

    assert '"name":"mobile_action"' in prompt
    assert "<tool_call>" in prompt
    assert "propose_subgoal_complete" in prompt
    assert '"completion_evidence"' not in prompt
    assert '"subgoal":"one small current objective"' not in prompt
    assert "Runtime owns subgoal creation" in prompt
    assert "prefer open_app" in prompt
    assert "2 to 6 checkpoints" not in prompt
