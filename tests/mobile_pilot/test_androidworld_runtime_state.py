from mobile_pilot.androidworld.runtime_state import RecoveryController, RuntimeProgress
from mobile_pilot.core import Action, ActionType


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
