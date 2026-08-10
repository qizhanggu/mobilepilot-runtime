from mobile_pilot.androidworld.runtime_state import (
    CompletionEvidence,
    Checkpoint,
    CheckpointEvidence,
    PlanState,
    RecoveryController,
    RuntimeProgress,
    SubgoalState,
    checkpoint_evidence_matches,
    completion_evidence_matches,
    classify_screen_change,
)
from mobile_pilot.core import Action, ActionType
from mobile_pilot.perception import ScreenState, UiElement


def test_progress_records_only_executed_actions_and_omits_typed_text():
    progress = RuntimeProgress()
    typed = Action(
        ActionType.TYPE_TEXT,
        {"text": "private message", "subgoal": "fill the message field"},
        reason="fill field",
        expected_outcome="the field contains the message",
    )

    progress.prepare_action(typed)
    assert progress.current_subgoal == "fill the message field"
    assert progress.next_verification == "the field contains the message"
    progress.record_execution(typed, executed=False, message="input failed")
    assert progress.completed == []
    assert progress.current_blocker == "input failed"

    progress.record_execution(typed, executed=True, message="executed")
    assert progress.completed == ["TYPE_TEXT[text omitted]"]
    assert "private message" not in str(progress)


def test_progress_detects_repeated_and_alternating_action_loops():
    progress = RuntimeProgress()
    up = Action(ActionType.SWIPE, {"direction": "up"})
    down = Action(ActionType.SWIPE, {"direction": "down"})

    for action in (up, up):
        progress.record_execution(action, executed=True, message="executed")
    assert progress.candidate_loop_signal(up) == "repeated_similar_action"

    progress = RuntimeProgress()
    for action in (up, down, up):
        progress.record_execution(action, executed=True, message="executed")
    assert progress.candidate_loop_signal(down) == "alternating_action_loop"


def test_progress_detects_two_unchanged_screens():
    progress = RuntimeProgress()
    wait = Action(ActionType.WAIT)

    progress.record_verification(changed=False, action=wait)
    assert progress.page_loop_signal("same") == ""
    progress.record_verification(changed=False, action=wait)
    assert progress.page_loop_signal("same") == "two_consecutive_unchanged_screens"


def test_progress_does_not_treat_adjacent_verifier_observations_as_page_revisit():
    progress = RuntimeProgress()

    progress.remember_screen("page-a")
    progress.remember_screen("page-a")

    assert progress.screen_fingerprints == ["page-a"]
    assert progress.page_loop_signal("page-a") == ""


def test_recovery_allows_one_replan_and_scores_rescue():
    controller = RecoveryController()
    blocked = Action(ActionType.SWIPE, {"direction": "up"})
    alternative = Action(ActionType.OPEN_APP, {"app_name": "clock"})

    episode = controller.begin("repeated_similar_action", step=2, blocked_action=blocked)
    assert episode is not None
    assert controller.review_replan(alternative) is True
    controller.mark_action_executed()

    outcome = controller.outcome(reward=1.0, terminal=True)
    assert outcome is not None
    assert outcome["rescued"] is True
    assert outcome["misfire"] is False
    assert controller.begin("another_failure", step=3, blocked_action=blocked) is None


def test_recovery_rejects_same_uncertain_action_and_marks_early_success_misfire():
    controller = RecoveryController()
    blocked = Action(ActionType.TYPE_TEXT, {"text": "do not repeat"})

    controller.begin("action_execution_failed", step=1, blocked_action=blocked)
    assert controller.review_replan(blocked) is False
    outcome = controller.outcome(reward=1.0, terminal=True)

    assert outcome is not None
    assert outcome["rescued"] is False
    assert outcome["misfire"] is True


def test_v21_recovery_uses_action_then_plan_level_and_stops_at_two():
    controller = RecoveryController(max_attempts=2)
    blocked = Action(ActionType.CLICK_POINT, {"point": [10, 20]})

    first = controller.begin("unchanged", step=1, blocked_action=blocked)
    second = controller.begin("still_blocked", step=2, blocked_action=blocked)

    assert first is not None and first.level == "action"
    assert second is not None and second.level == "plan"
    assert controller.remaining == 0
    assert controller.begin("third", step=3, blocked_action=blocked) is None


def test_plan_state_preserves_confirmed_checkpoints_when_revising():
    plan = PlanState(
        mode="checklist",
        checkpoints=[
            Checkpoint("open calendar", CheckpointEvidence("ui_text", "Calendar")),
            Checkpoint("create event", CheckpointEvidence("ui_text", "Save")),
        ],
    )
    plan.activate_first()
    plan.confirm_active()

    revised = plan.revise_remaining(
        [Checkpoint("open event editor", CheckpointEvidence("ui_text", "Event name"))],
        reason="the original editor assumption was wrong",
    )

    assert revised
    assert plan.completed_goals() == ("open calendar",)
    assert plan.active.goal == "open event editor"
    assert plan.revision_count == 1


def test_multisignal_verifier_keeps_exact_and_tolerates_tiny_visual_change():
    before = ScreenState((100, 200), "calendar", (), "exact-a", visual_fingerprint="0" * 64)
    after = ScreenState((100, 200), "calendar", (), "exact-b", visual_fingerprint="0" * 63 + "1")

    result, details = classify_screen_change(before, after)

    assert result == "visually_similar"
    assert details["exact_match"] is False
    assert details["visual_hamming_distance"] > 0


def test_checkpoint_ui_text_requires_tree_and_runtime_matches_it():
    checkpoint = Checkpoint("open editor", CheckpointEvidence("ui_text", "Save"), "active")
    no_tree = ScreenState((100, 200), "calendar", (), "a")
    element = UiElement(
        stable_id="save",
        resource_id="calendar:id/save",
        text="Save",
        content_description="",
        class_name="Button",
        bounds=(1, 1, 10, 10),
        clickable=True,
        enabled=True,
        editable=False,
    )
    with_tree = ScreenState((100, 200), "calendar", (element,), "b")

    assert checkpoint_evidence_matches(checkpoint, no_tree)[0] is None
    assert checkpoint_evidence_matches(checkpoint, with_tree)[0] is True


def test_checkpoint_package_evidence_accepts_a_stable_app_name_suffix():
    checkpoint = Checkpoint(
        "open Markor",
        CheckpointEvidence("package_activity", "com.markor.markor"),
        "active",
    )
    screen = ScreenState(
        (100, 200),
        "net.gsantner.markor/MainActivity",
        (),
        "a",
    )

    matched, evidence = checkpoint_evidence_matches(checkpoint, screen)

    assert matched is True
    assert "net.gsantner.markor" in evidence


def test_v22_subgoal_lifecycle_blocks_actor_mutation_until_recovery():
    state = SubgoalState()
    original = CompletionEvidence("ui_text", "Save")
    replacement = CompletionEvidence("visual_state", "contact editor is visible")

    assert state.accept_proposal("open editor", original) == "accepted"
    assert state.accept_proposal("open settings", replacement) == "mutation_blocked"
    assert state.active_goal == "open editor"
    assert state.active_evidence == original

    assert state.accept_proposal(
        "open settings",
        replacement,
        allow_revision=True,
        revision_reason="wrong page",
    ) == "revised"
    assert state.revision_count == 1
    assert state.confirm_active() == "open settings"
    assert state.completed_goals == ["open settings"]
    assert not state.active


def test_v22_completion_evidence_uses_hidden_runtime_text_without_actor_tree():
    screen = ScreenState(
        (100, 200),
        "com.example.messages/.ConversationActivity",
        (),
        "screen",
        verification_texts=("Zhang San | Send | app:id/send",),
    )

    text_match = completion_evidence_matches(
        CompletionEvidence("ui_text", "Zhang San"), screen
    )
    package_match = completion_evidence_matches(
        CompletionEvidence("package_activity", "messages"), screen
    )
    visual_match = completion_evidence_matches(
        CompletionEvidence("visual_state", "the editor is visibly open"), screen
    )

    assert text_match[0] is True
    assert package_match[0] is True
    assert visual_match[0] is None


def test_partial_reward_does_not_close_or_rescue_recovery_episode():
    controller = RecoveryController(max_attempts=2)
    blocked = Action(ActionType.CLICK_POINT, {"point": [10, 20]})
    controller.begin("stalled", step=1, blocked_action=blocked)
    controller.mark_action_executed()

    assert controller.outcome(reward=0.5, terminal=False) is None
    assert controller.active is not None

    outcome = controller.outcome(reward=0.5, terminal=True)

    assert outcome is not None
    assert outcome["rescued"] is False
    assert outcome["misfire"] is False
