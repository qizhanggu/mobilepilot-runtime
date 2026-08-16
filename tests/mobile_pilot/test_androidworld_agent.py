import json
from pathlib import Path
from types import SimpleNamespace

from PIL import Image

from mobile_pilot.androidworld.actor import (
    AndroidWorldActorDecision,
    AndroidWorldPlanDecision,
)
from mobile_pilot.androidworld.agent import MobilePilotAndroidWorldAgent
from mobile_pilot.androidworld.progress_verifier import ProgressVerifierDecision
from mobile_pilot.androidworld.subgoal_manager import SubgoalManagerDecision
from mobile_pilot.androidworld.runtime_state import (
    Checkpoint,
    CheckpointEvidence,
    CompletionEvidence,
    PlanState,
    RuntimeProgress,
)
from mobile_pilot.core import Action, ActionResult, ActionType, ErrorKind, ParseResult
from mobile_pilot.perception import ScreenState, UiElement
from mobile_pilot.policy.gui_plus import VisionCallMetrics


def test_official_completion_rejection_is_recorded_for_next_step():
    recorded = []
    agent = object.__new__(MobilePilotAndroidWorldAgent)
    agent._recent_failure = ""
    agent._last_verifier = ""
    agent._step_index = 3
    agent._mode = "hybrid"
    agent._trace = SimpleNamespace(write=lambda event, **payload: recorded.append((event, payload)))

    agent.reject_completion_proposal("official reward remained zero")

    assert agent._recent_failure == "official reward remained zero"
    assert agent._last_verifier == "official_completion_rejected"
    assert recorded == [
        (
                "official_completion_rejected",
                {
                    "step": 3,
                    "reason": "official reward remained zero",
                    "mode": "hybrid",
                    "runtime_version": "v1",
                },
            )
        ]


def test_v2_official_completion_rejection_updates_progress_state():
    recorded = []
    agent = object.__new__(MobilePilotAndroidWorldAgent)
    agent._recent_failure = ""
    agent._last_verifier = ""
    agent._step_index = 1
    agent._mode = "hybrid"
    agent._runtime_version = "v2"
    agent._progress = RuntimeProgress()
    agent._trace = SimpleNamespace(write=lambda event, **payload: recorded.append((event, payload)))

    agent.reject_completion_proposal("official reward remained zero")

    assert agent._progress.current_blocker == "official_completion_rejected"
    assert agent._progress.recent_failure == "official reward remained zero"


class _QueuedPolicy:
    def __init__(self, results):
        self.results = list(results)
        self.requests = []

    def decide_with_metrics(self, request):
        self.requests.append(request)
        result = self.results.pop(0)
        return AndroidWorldActorDecision(
            result,
            VisionCallMetrics("test-model", 0.01, 10, 2, 12, 0.001),
        )


class _V21Policy(_QueuedPolicy):
    def __init__(self, results, plan):
        super().__init__(results)
        self.plan = plan
        self.plan_requests = []

    def plan_with_metrics(self, **request):
        self.plan_requests.append(request)
        return AndroidWorldPlanDecision(
            self.plan,
            VisionCallMetrics("test-model", 0.01, 10, 2, 12, 0.001),
            raw_output='{"mode":"checklist"}',
        )


class _FakeAdapter:
    def __init__(
        self,
        fingerprints,
        *,
        execution_results=None,
        verification_texts=None,
        packages=None,
    ):
        self.fingerprints = list(fingerprints)
        self.execution_results = list(execution_results or [])
        self.verification_texts = list(verification_texts or [])
        self.packages = list(packages or [])
        self.include_tree_calls = []
        self.executed_actions = []

    def observe(self, *, include_ui_tree, include_context_signals=False):
        self.include_tree_calls.append(include_ui_tree)
        fingerprint = self.fingerprints.pop(0)
        verification_texts = (
            tuple(self.verification_texts.pop(0))
            if self.verification_texts
            else ()
        )
        package = self.packages.pop(0) if self.packages else "test"
        elements = ()
        if include_ui_tree:
            elements = (
                UiElement(
                    stable_id="button",
                    resource_id="app:id/next",
                    text="Next",
                    content_description="",
                    class_name="Button",
                    bounds=(1, 2, 20, 30),
                    clickable=True,
                    enabled=True,
                    editable=False,
                ),
            )
        return Image.new("RGB", (100, 200), "white"), ScreenState(
            image_size=(100, 200),
            package_activity=package,
            elements=elements,
            fingerprint=fingerprint,
            exact_fingerprint=fingerprint,
            verification_texts=verification_texts,
        )

    def execute(self, action):
        self.executed_actions.append(action)
        if self.execution_results:
            return self.execution_results.pop(0)
        return ActionResult(True, action, "executed")


def _parsed(action, raw='{"action":"WAIT"}'):
    return ParseResult(action=action, raw_output=raw)


def _trace_rows(path):
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines()]


class _FakeProgressVerifier:
    def __init__(self, verdict, *, evidence="visible evidence", disposition=None):
        self.verdict = verdict
        self.evidence = evidence
        self.disposition = disposition or {
            "completed": "confirm_subgoal",
            "progress": "continue",
            "stalled": "change_action",
            "regressed": "recover",
            "uncertain": "reobserve",
        }[verdict]
        self.requests = []

    def verify_with_metrics(self, **request):
        self.requests.append(request)
        return ProgressVerifierDecision(
            self.verdict,
            self.evidence,
            self.disposition,
            VisionCallMetrics("qwen-test", 0.01, 20, 4, 24, 0.0001),
            raw_output='{"verdict":"test"}',
        )


class _FakeSubgoalManager:
    def __init__(self, decisions):
        self.decisions = list(decisions)
        self.requests = []

    def propose_with_metrics(self, **request):
        self.requests.append(request)
        subgoal, evidence = self.decisions.pop(0)
        return SubgoalManagerDecision(
            subgoal,
            evidence,
            "bounded next objective",
            VisionCallMetrics("qwen-test", 0.01, 20, 4, 24, 0.0001),
            raw_output='{"subgoal":"test"}',
        )


def test_v2_protocol_guard_retries_once_before_any_action(tmp_path):
    policy = _QueuedPolicy(
        [
            ParseResult(
                error_kind=ErrorKind.EMPTY_OUTPUT,
                message="empty model output",
                raw_output="",
            ),
            _parsed(Action(ActionType.WAIT, reason="stabilize")),
        ]
    )
    agent = MobilePilotAndroidWorldAgent(
        object(),
        mode="hybrid",
        max_steps=3,
        policy=policy,
        trace_path=tmp_path / "trace.jsonl",
        runtime_version="v2",
    )
    adapter = _FakeAdapter(["before", "retry", "after"])
    agent._adapter = adapter

    result = agent.step("do the task")

    assert not result.done
    assert len(adapter.executed_actions) == 1
    # The Tree is supplied to the retry decision only; the post-action
    # fingerprint verifier remains screenshot-only.
    assert adapter.include_tree_calls == [False, True, False]
    assert policy.requests[1].task.protocol_feedback
    rows = _trace_rows(tmp_path / "trace.jsonl")
    guards = [row for row in rows if row["event"] == "protocol_guard"]
    assert [row["outcome"] for row in guards] == ["triggered", "action_obtained"]
    retry_observation = next(
        row
        for row in rows
        if row["event"] == "observation" and row["phase"] == "protocol_retry"
    )
    assert retry_observation["ui_tree_trigger_reason"] == "invalid_actor_output"
    assert retry_observation["ui_tree_summary"]["element_count"] == 1


def test_v1_keeps_fail_fast_behavior_for_invalid_output(tmp_path):
    policy = _QueuedPolicy(
        [
            ParseResult(
                error_kind=ErrorKind.EMPTY_OUTPUT,
                message="empty model output",
                raw_output="",
            )
        ]
    )
    agent = MobilePilotAndroidWorldAgent(
        object(),
        mode="hybrid",
        max_steps=3,
        policy=policy,
        trace_path=tmp_path / "trace.jsonl",
        runtime_version="v1",
    )
    adapter = _FakeAdapter(["before"])
    agent._adapter = adapter

    result = agent.step("do the task")

    assert result.done
    assert result.data["reason"] == "invalid_actor_output"
    assert len(policy.requests) == 1
    assert adapter.include_tree_calls == [True]


def test_v2_repeated_action_triggers_one_replan_and_records_official_rescue(tmp_path):
    swipe = Action(ActionType.SWIPE, {"direction": "up"}, reason="find app")
    open_clock = Action(
        ActionType.OPEN_APP,
        {"app_name": "clock"},
        reason="use direct app launch",
    )
    policy = _QueuedPolicy(
        [
            _parsed(swipe, '{"action":"SWIPE","direction":"up"}'),
            _parsed(swipe, '{"action":"SWIPE","direction":"up"}'),
            _parsed(swipe, '{"action":"SWIPE","direction":"up"}'),
            _parsed(open_clock, '{"action":"OPEN_APP","app_name":"clock"}'),
        ]
    )
    agent = MobilePilotAndroidWorldAgent(
        object(),
        mode="hybrid",
        max_steps=5,
        policy=policy,
        trace_path=tmp_path / "trace.jsonl",
        runtime_version="v2",
    )
    adapter = _FakeAdapter(
        ["s0", "s1", "s2", "s3", "s4", "replan", "done"]
    )
    agent._adapter = adapter

    assert not agent.step("open clock").done
    assert not agent.step("open clock").done
    replan_request = agent.step("open clock")
    assert not replan_request.done
    assert replan_request.data["reason"] == "agent_replan_requested"
    assert len(adapter.executed_actions) == 2

    resumed = agent.step("open clock")
    assert not resumed.done
    agent.record_official_reward(1.0, terminal=True)

    rows = _trace_rows(tmp_path / "trace.jsonl")
    trigger = next(row for row in rows if row["event"] == "agent_recovery_triggered")
    outcome = next(row for row in rows if row["event"] == "agent_recovery_outcome")
    tree = next(
        row
        for row in rows
        if row["event"] == "observation"
        and row["ui_tree_trigger_reason"] == "repeated_similar_action"
    )
    assert trigger["ui_tree_requested_next"]
    assert tree["ui_tree_summary"]["element_count"] == 1
    assert outcome["rescued"]
    assert not outcome["misfire"]


def test_v2_recovery_rejects_the_same_looping_action_before_second_trigger(tmp_path):
    swipe = Action(ActionType.SWIPE, {"direction": "up"}, reason="find app")
    policy = _QueuedPolicy(
        [_parsed(swipe, '{"action":"SWIPE","direction":"up"}')] * 4
    )
    agent = MobilePilotAndroidWorldAgent(
        object(),
        mode="hybrid",
        max_steps=5,
        policy=policy,
        trace_path=tmp_path / "trace.jsonl",
        runtime_version="v2",
    )
    adapter = _FakeAdapter(["s0", "s1", "s2", "s3", "s4", "replan"])
    agent._adapter = adapter

    assert not agent.step("open clock").done
    assert not agent.step("open clock").done
    assert not agent.step("open clock").done
    repeated = agent.step("open clock")

    assert repeated.done
    assert repeated.data["reason"] == "unsafe_repeated_action_after_recovery"
    rows = _trace_rows(tmp_path / "trace.jsonl")
    replans = [row for row in rows if row["event"] == "agent_recovery_replan"]
    triggers = [row for row in rows if row["event"] == "agent_recovery_triggered"]
    assert len(triggers) == 1
    assert replans[0]["changed_action"] is False


def test_v2_action_failure_reobserves_with_tree_and_uses_different_action(tmp_path):
    failed_open = Action(ActionType.OPEN_APP, {"app_name": "Note"})
    alternative = Action(ActionType.PRESS_BACK, reason="return to a known state")
    policy = _QueuedPolicy(
        [
            _parsed(failed_open, '{"action":"OPEN_APP","app_name":"Note"}'),
            _parsed(alternative, '{"action":"BACK"}'),
        ]
    )
    failed_result = ActionResult(False, failed_open, "app key was rejected")
    successful_result = ActionResult(True, alternative, "executed")
    agent = MobilePilotAndroidWorldAgent(
        object(),
        mode="hybrid",
        max_steps=4,
        policy=policy,
        trace_path=tmp_path / "trace.jsonl",
        runtime_version="v2",
    )
    adapter = _FakeAdapter(
        ["home", "replan", "after"],
        execution_results=[failed_result, successful_result],
    )
    agent._adapter = adapter

    first = agent.step("copy text")
    agent.record_official_reward(0.0, terminal=False)
    second = agent.step("copy text")
    agent.record_official_reward(1.0, terminal=True)

    assert not first.done
    assert first.data["trigger"] == "action_execution_failed"
    assert not second.done
    assert adapter.include_tree_calls == [False, True, True]
    rows = _trace_rows(tmp_path / "trace.jsonl")
    replan = next(row for row in rows if row["event"] == "agent_recovery_replan")
    outcome = next(row for row in rows if row["event"] == "agent_recovery_outcome")
    assert replan["changed_action"] is True
    assert outcome["rescued"] is True


def test_v2_actor_can_request_ui_tree_as_an_on_demand_tool(tmp_path):
    request_tree = Action(
        ActionType.CALL_TOOL,
        {"tool": "ui_tree"},
        reason="the visual label is unclear",
    )
    wait = Action(ActionType.WAIT, reason="wait for the selected page")
    policy = _QueuedPolicy(
        [
            _parsed(request_tree, '{"action":"REQUEST_UI_TREE"}'),
            _parsed(wait, '{"action":"WAIT"}'),
        ]
    )
    agent = MobilePilotAndroidWorldAgent(
        object(),
        mode="hybrid",
        max_steps=3,
        policy=policy,
        trace_path=tmp_path / "trace.jsonl",
        runtime_version="v2",
    )
    adapter = _FakeAdapter(["before", "with-tree", "after"])
    agent._adapter = adapter

    result = agent.step("inspect the page")
    agent.record_official_reward(0.0, terminal=True)

    assert not result.done
    assert adapter.include_tree_calls == [False, True, False]
    rows = _trace_rows(tmp_path / "trace.jsonl")
    tool_request = next(row for row in rows if row["event"] == "ui_tree_tool_requested")
    tree_observation = next(
        row
        for row in rows
        if row["event"] == "observation" and row["phase"] == "ui_tree_tool"
    )
    tree_outcome = next(row for row in rows if row["event"] == "ui_tree_outcome")
    assert tool_request["action_executed_before_request"] is False
    assert tree_observation["ui_tree_summary"]["sample_labels"] == ["Next"]
    assert tree_outcome["official_success_after_use"] is False


def test_v21_actor_can_only_propose_checkpoint_and_runtime_confirms_tree_evidence(tmp_path):
    plan = PlanState(
        mode="checklist",
        reason="the task has a verifiable editor page",
        checkpoints=[
            Checkpoint(
                "open the next page",
                CheckpointEvidence("ui_text", "Next"),
                "active",
            )
        ],
    )
    proposal = Action(
        ActionType.PROPOSE_CHECKPOINT_COMPLETE,
        {"observed_evidence": "I think the page is open"},
        reason="Next is visible",
    )
    policy = _V21Policy(
        [_parsed(proposal, '{"action":"PROPOSE_CHECKPOINT_COMPLETE"}')],
        plan,
    )
    agent = MobilePilotAndroidWorldAgent(
        object(),
        mode="hybrid",
        max_steps=3,
        policy=policy,
        trace_path=tmp_path / "trace.jsonl",
        runtime_version="v2.1",
    )
    adapter = _FakeAdapter(["before", "tree-evidence"])
    agent._adapter = adapter

    result = agent.step("open the next page")

    assert not result.done
    assert result.data["reason"] == "checkpoint_confirmed"
    assert agent._plan.is_complete
    assert adapter.executed_actions == []
    assert adapter.include_tree_calls == [False, True]
    rows = _trace_rows(tmp_path / "trace.jsonl")
    verifier = next(row for row in rows if row["event"] == "checkpoint_verifier")
    assert verifier["decision"] == "deterministic_confirmed"
    assert verifier["actor_self_certified"] is False


def test_v21_direct_plan_does_not_force_checkpoints_on_short_task(tmp_path):
    policy = _V21Policy(
        [_parsed(Action(ActionType.WAIT), '{"action":"WAIT"}')],
        PlanState.direct("single visible action"),
    )
    agent = MobilePilotAndroidWorldAgent(
        object(),
        mode="vision_only",
        max_steps=2,
        policy=policy,
        trace_path=tmp_path / "trace.jsonl",
        runtime_version="v2.1",
    )
    adapter = _FakeAdapter(["before", "after"])
    agent._adapter = adapter

    result = agent.step("wait for the page")

    assert not result.done
    assert len(adapter.executed_actions) == 1
    assert policy.requests[0].task.plan_mode == "direct"
    assert policy.requests[0].task.active_checkpoint == ""


def test_v21_direct_plan_safely_corrects_one_checkpoint_proposal(tmp_path):
    proposal = Action(
        ActionType.PROPOSE_CHECKPOINT_COMPLETE,
        {"observed_evidence": "the page looks ready"},
    )
    wait = Action(ActionType.WAIT, reason="continue normal execution")
    policy = _V21Policy(
        [
            _parsed(proposal, '{"action":"PROPOSE_CHECKPOINT_COMPLETE"}'),
            _parsed(wait, '{"action":"WAIT"}'),
        ],
        PlanState.direct("single visible action"),
    )
    agent = MobilePilotAndroidWorldAgent(
        object(),
        mode="vision_only",
        max_steps=2,
        policy=policy,
        trace_path=tmp_path / "trace.jsonl",
        runtime_version="v2.1",
    )
    adapter = _FakeAdapter(["before", "again", "after"])
    agent._adapter = adapter

    corrected = agent.step("wait for the page")
    resumed = agent.step("wait for the page")

    assert not corrected.done
    assert corrected.data["reason"] == "checkpoint_proposal_corrected"
    assert not resumed.done
    assert len(adapter.executed_actions) == 1
    rows = _trace_rows(tmp_path / "trace.jsonl")
    assert any(row["event"] == "checkpoint_proposal_corrected" for row in rows)


def test_v21_protocol_guard_allows_one_safe_retry_per_decision_point(tmp_path):
    invalid = ParseResult(
        error_kind=ErrorKind.EMPTY_OUTPUT,
        message="empty model output",
        raw_output="",
    )
    wait = _parsed(Action(ActionType.WAIT), '{"action":"WAIT"}')
    policy = _V21Policy([invalid, wait, invalid, wait], PlanState.direct("reactive"))
    agent = MobilePilotAndroidWorldAgent(
        object(),
        mode="vision_only",
        max_steps=3,
        policy=policy,
        trace_path=tmp_path / "trace.jsonl",
        runtime_version="v2.1",
    )
    adapter = _FakeAdapter(["s0", "retry0", "s1", "s2", "retry1", "s3"])
    agent._adapter = adapter

    first = agent.step("wait")
    second = agent.step("wait")

    assert not first.done and not second.done
    assert len(adapter.executed_actions) == 2
    rows = _trace_rows(tmp_path / "trace.jsonl")
    guards = [row for row in rows if row["event"] == "protocol_guard"]
    assert [row["outcome"] for row in guards] == [
        "triggered",
        "action_obtained",
        "triggered",
        "action_obtained",
    ]


def test_v22_deterministic_verifier_completes_subgoal_without_vlm(tmp_path):
    action = Action(
        ActionType.WAIT,
        {
            "subgoal": "show the ready page",
            "completion_evidence_kind": "ui_text",
            "completion_evidence_value": "Ready",
        },
        expected_outcome="Ready becomes visible",
    )
    policy = _QueuedPolicy([_parsed(action)])
    agent = MobilePilotAndroidWorldAgent(
        object(),
        mode="hybrid",
        max_steps=3,
        policy=policy,
        progress_verifier_mode="off",
        trace_path=tmp_path / "trace.jsonl",
        runtime_version="v2.2",
    )
    agent._adapter = _FakeAdapter(
        ["before", "after"],
        verification_texts=[(), ("Ready | app:id/status",)],
    )

    result = agent.step("show the ready page")

    assert not result.done
    assert not agent._subgoals.active
    assert agent._subgoals.completed_goals == ["show the ready page"]
    rows = _trace_rows(tmp_path / "trace.jsonl")
    assert any(row["event"] == "deterministic_progress_verifier" for row in rows)
    completed = next(row for row in rows if row["event"] == "subgoal_completed")
    assert completed["source"] == "deterministic"
    assert not any(row["event"] == "vlm_progress_verifier" for row in rows)


def test_v22_visual_state_uses_event_triggered_verifier_and_keeps_images(tmp_path):
    action = Action(
        ActionType.WAIT,
        {
            "subgoal": "open the editor",
            "completion_evidence_kind": "visual_state",
            "completion_evidence_value": "the contact editor is visible",
        },
        expected_outcome="editor opens",
    )
    verifier = _FakeProgressVerifier("completed", evidence="editor fields are visible")
    agent = MobilePilotAndroidWorldAgent(
        object(),
        mode="vision_only",
        max_steps=3,
        policy=_QueuedPolicy([_parsed(action)]),
        progress_verifier=verifier,
        trace_path=tmp_path / "trace.jsonl",
        runtime_version="v2.2",
    )
    agent._adapter = _FakeAdapter(["before", "after"])

    result = agent.step("open the editor")

    assert not result.done
    assert len(verifier.requests) == 1
    assert agent._subgoals.completed_goals == ["open the editor"]
    row = next(
        row for row in _trace_rows(tmp_path / "trace.jsonl")
        if row["event"] == "vlm_progress_verifier"
    )
    assert row["verdict"] == "completed"
    assert Path(row["before_image"]).exists()
    assert Path(row["after_image"]).exists()


def test_v22_vlm_regression_triggers_bounded_recovery(tmp_path):
    action = Action(
        ActionType.CLICK_POINT,
        {
            "point": [20, 30],
            "subgoal": "open the target conversation",
            "completion_evidence_kind": "visual_state",
            "completion_evidence_value": "target conversation is visible",
        },
    )
    verifier = _FakeProgressVerifier("regressed", evidence="a different app opened")
    agent = MobilePilotAndroidWorldAgent(
        object(),
        mode="hybrid",
        max_steps=3,
        policy=_QueuedPolicy([_parsed(action)]),
        progress_verifier=verifier,
        trace_path=tmp_path / "trace.jsonl",
        runtime_version="v2.2",
    )
    adapter = _FakeAdapter(["before", "after"])
    agent._adapter = adapter

    result = agent.step("reply to the target message")

    assert not result.done
    assert result.data["reason"] == "agent_replan_requested"
    assert result.data["trigger"] == "progress_verifier_regressed"
    assert len(adapter.executed_actions) == 1
    assert agent._recovery.active.level == "action"
    assert agent._pending_tree_reason == "progress_verifier_regressed"


def test_v22_manager_freezes_subgoal_before_action_only_actor_decision(tmp_path):
    manager = _FakeSubgoalManager(
        [("open Messages", CompletionEvidence("package_activity", "messaging"))]
    )
    action = Action(ActionType.WAIT, reason="let the app settle")
    policy = _QueuedPolicy([_parsed(action)])
    agent = MobilePilotAndroidWorldAgent(
        object(),
        mode="hybrid",
        max_steps=3,
        policy=policy,
        subgoal_manager=manager,
        progress_verifier_mode="off",
        trace_path=tmp_path / "trace.jsonl",
        runtime_version="v2.2",
    )
    agent._adapter = _FakeAdapter(
        ["before", "after"],
        packages=["launcher", "com.google.android.apps.messaging"],
    )

    result = agent.step("reply to Alice in Messages")

    assert not result.done
    assert len(manager.requests) == 1
    assert policy.requests[0].task.active_subgoal == "open Messages"
    assert "subgoal" not in action.parameters
    assert agent._subgoals.completed_goals == ["open Messages"]
    rows = _trace_rows(tmp_path / "trace.jsonl")
    manager_row = next(row for row in rows if row["event"] == "subgoal_manager")
    assert manager_row["outcome"] == "accepted"
    assert manager_row["action_executed"] is False


def test_v22_manager_is_not_called_on_every_actor_step(tmp_path):
    manager = _FakeSubgoalManager(
        [("open the editor", CompletionEvidence("ui_text", "Save"))]
    )
    policy = _QueuedPolicy(
        [_parsed(Action(ActionType.WAIT)), _parsed(Action(ActionType.PRESS_BACK))]
    )
    agent = MobilePilotAndroidWorldAgent(
        object(),
        mode="vision_only",
        max_steps=4,
        policy=policy,
        subgoal_manager=manager,
        progress_verifier_mode="off",
        trace_path=tmp_path / "trace.jsonl",
        runtime_version="v2.2",
    )
    agent._adapter = _FakeAdapter(
        ["s0", "s1", "s2", "s3"],
        verification_texts=[("Home",), ("Home",), ("Home",), ("Home",)],
    )

    first = agent.step("create a note")
    second = agent.step("create a note")

    assert not first.done and not second.done
    assert len(manager.requests) == 1
    assert agent._subgoals.active_goal == "open the editor"
    assert agent._progress.current_subgoal == "open the editor"


def test_v22_manager_rejects_hard_evidence_already_true_before_action(tmp_path):
    manager = _FakeSubgoalManager(
        [
            ("return home", CompletionEvidence("ui_text", "Home")),
            ("return home", CompletionEvidence("ui_text", "Home")),
        ]
    )
    agent = MobilePilotAndroidWorldAgent(
        object(),
        mode="hybrid",
        max_steps=3,
        policy=_QueuedPolicy([_parsed(Action(ActionType.WAIT))]),
        subgoal_manager=manager,
        progress_verifier_mode="off",
        trace_path=tmp_path / "trace.jsonl",
        runtime_version="v2.2",
    )
    agent._adapter = _FakeAdapter(
        ["s0", "s1"],
        verification_texts=[("Home",), ("Home",)],
    )

    result = agent.step("open Messages")

    assert not result.done
    assert not agent._subgoals.active
    rows = [
        row for row in _trace_rows(tmp_path / "trace.jsonl")
        if row["event"] == "subgoal_manager"
    ]
    assert len(manager.requests) == 2
    assert manager.requests[1]["rejected_evidence_feedback"]
    assert [row["outcome"] for row in rows] == [
        "invalid_already_satisfied_regenerating",
        "invalid_already_satisfied",
    ]
    assert rows[-1]["action_executed"] is False


def test_v22_manager_accepts_one_regenerated_postcondition(tmp_path):
    manager = _FakeSubgoalManager(
        [
            ("enter Stopwatch", CompletionEvidence("ui_text", "Stopwatch")),
            (
                "enter Stopwatch",
                CompletionEvidence("visual_state", "timer controls are visible"),
            ),
        ]
    )
    agent = MobilePilotAndroidWorldAgent(
        object(),
        mode="hybrid",
        max_steps=3,
        policy=_QueuedPolicy([_parsed(Action(ActionType.WAIT))]),
        subgoal_manager=manager,
        progress_verifier_mode="off",
        trace_path=tmp_path / "trace.jsonl",
        runtime_version="v2.2",
    )
    agent._adapter = _FakeAdapter(
        ["s0", "s1"], verification_texts=[("Stopwatch",), ("Stopwatch",)]
    )

    result = agent.step("open Stopwatch")

    assert not result.done
    assert len(manager.requests) == 2
    assert agent._subgoals.active_goal == "enter Stopwatch"
    assert agent._subgoals.active_evidence == CompletionEvidence(
        "visual_state", "timer controls are visible"
    )


def test_v22_redundant_tree_request_gets_one_safe_action_retry(tmp_path):
    request_tree = Action(ActionType.CALL_TOOL, {"tool": "ui_tree"})
    wait = Action(ActionType.WAIT, reason="use the supplied context")
    policy = _QueuedPolicy([_parsed(request_tree), _parsed(wait)])
    agent = MobilePilotAndroidWorldAgent(
        object(),
        mode="hybrid",
        max_steps=3,
        policy=policy,
        progress_verifier_mode="off",
        trace_path=tmp_path / "trace.jsonl",
        runtime_version="v2.2",
    )
    agent._pending_tree_reason = "progress_verifier_uncertain"
    agent._adapter = _FakeAdapter(["s0", "s1"])

    result = agent.step("open settings")

    assert not result.done
    assert len(policy.requests) == 2
    assert all(request.include_ui_tree for request in policy.requests)
    assert [action.type for action in agent._adapter.executed_actions] == [
        ActionType.WAIT
    ]
    guards = [
        row for row in _trace_rows(tmp_path / "trace.jsonl")
        if row["event"] == "protocol_guard"
        and row["strategy"] == "redundant_ui_tree_request"
    ]
    assert [row["outcome"] for row in guards] == [
        "triggered",
        "action_obtained",
    ]


def test_v22_manager_proposes_again_after_confirmed_subgoal_boundary(tmp_path):
    manager = _FakeSubgoalManager(
        [
            ("open Messages", CompletionEvidence("package_activity", "messaging")),
            ("open Alice conversation", CompletionEvidence("ui_text", "Alice")),
        ]
    )
    policy = _QueuedPolicy(
        [_parsed(Action(ActionType.WAIT)), _parsed(Action(ActionType.WAIT))]
    )
    agent = MobilePilotAndroidWorldAgent(
        object(),
        mode="hybrid",
        max_steps=4,
        policy=policy,
        subgoal_manager=manager,
        progress_verifier_mode="off",
        trace_path=tmp_path / "trace.jsonl",
        runtime_version="v2.2",
    )
    agent._adapter = _FakeAdapter(
        ["s0", "s1", "s2", "s3"],
        packages=[
            "launcher",
            "com.google.android.apps.messaging",
            "com.google.android.apps.messaging",
            "com.google.android.apps.messaging",
        ],
        verification_texts=[(), (), ("Conversations",), ("Conversations",)],
    )

    agent.step("reply to Alice in Messages")
    agent.step("reply to Alice in Messages")

    assert len(manager.requests) == 2
    assert [request["trigger"] for request in manager.requests] == [
        "initial",
        "previous_completed",
    ]
    assert agent._subgoals.active_goal == "open Alice conversation"


def test_v22_second_recovery_can_request_one_subgoal_revision(tmp_path):
    manager = _FakeSubgoalManager(
        [("return to Messages", CompletionEvidence("package_activity", "messages"))]
    )
    agent = MobilePilotAndroidWorldAgent(
        object(),
        mode="hybrid",
        max_steps=4,
        policy=_QueuedPolicy([]),
        subgoal_manager=manager,
        progress_verifier_mode="off",
        trace_path=tmp_path / "trace.jsonl",
        runtime_version="v2.2",
    )
    agent._goal = "reply to Alice in Messages"
    agent._subgoals.accept_proposal(
        "open Alice conversation",
        CompletionEvidence("ui_text", "Alice"),
    )
    blocked = Action(ActionType.WAIT)

    assert agent._begin_recovery("screen_stalled", blocked_action=blocked)
    assert agent._begin_recovery("wrong_context", blocked_action=blocked)
    agent._ensure_managed_subgoal(
        Image.new("RGB", (100, 200), "white"),
        ScreenState(
            image_size=(100, 200),
            package_activity="settings",
            elements=(),
            fingerprint="screen",
            exact_fingerprint="screen",
        ),
    )

    assert len(manager.requests) == 1
    assert manager.requests[0]["trigger"] == "recovery_revision"
    assert manager.requests[0]["current_subgoal"] == "open Alice conversation"
    assert agent._subgoals.active_goal == "return to Messages"
    assert agent._subgoals.revision_count == 1


def test_v22_hard_evidence_cannot_be_overruled_by_vlm_completed_claim(tmp_path):
    first_action = Action(
        ActionType.WAIT,
        {
            "subgoal": "show the Done label",
            "completion_evidence_kind": "ui_text",
            "completion_evidence_value": "Done",
        },
    )
    proposal = Action(
        ActionType.PROPOSE_SUBGOAL_COMPLETE,
        {"observed_evidence": "I think it is done"},
    )
    verifier = _FakeProgressVerifier("completed", evidence="page looks finished")
    agent = MobilePilotAndroidWorldAgent(
        object(),
        mode="hybrid",
        max_steps=3,
        policy=_QueuedPolicy([_parsed(first_action), _parsed(proposal)]),
        progress_verifier=verifier,
        trace_path=tmp_path / "trace.jsonl",
        runtime_version="v2.2",
    )
    agent._adapter = _FakeAdapter(
        ["s0", "s1", "s2"],
        verification_texts=[("Loading",), ("Still loading",), ("Still loading",)],
    )

    first = agent.step("finish loading")
    second = agent.step("finish loading")

    assert not first.done and not second.done
    assert agent._subgoals.active
    assert agent._subgoals.completed_goals == []
    assert second.data["reason"] == "agent_replan_requested"
    assert len(verifier.requests) == 1


def test_v22_actor_cannot_mutate_frozen_subgoal_without_recovery(tmp_path):
    first = Action(
        ActionType.WAIT,
        {
            "subgoal": "open conversation A",
            "completion_evidence_kind": "ui_text",
            "completion_evidence_value": "Conversation A",
        },
    )
    second = Action(
        ActionType.WAIT,
        {
            "subgoal": "open settings",
            "completion_evidence_kind": "ui_text",
            "completion_evidence_value": "Settings",
        },
    )
    agent = MobilePilotAndroidWorldAgent(
        object(),
        mode="vision_only",
        max_steps=4,
        policy=_QueuedPolicy([_parsed(first), _parsed(second)]),
        progress_verifier_mode="off",
        trace_path=tmp_path / "trace.jsonl",
        runtime_version="v2.2",
    )
    agent._adapter = _FakeAdapter(
        ["s0", "s1", "s2", "s3"],
        verification_texts=[("Home",), ("Home",), ("Home",), ("Home",)],
    )

    agent.step("open conversation A")
    agent.step("open conversation A")

    assert agent._subgoals.active_goal == "open conversation A"
    rows = [
        row for row in _trace_rows(tmp_path / "trace.jsonl")
        if row["event"] == "subgoal_proposal"
    ]
    assert [row["outcome"] for row in rows] == ["accepted", "mutation_blocked"]


def test_v22_confirmed_subgoal_returns_before_unchanged_page_loop(tmp_path):
    action = Action(
        ActionType.WAIT,
        {
            "subgoal": "show Done",
            "completion_evidence_kind": "ui_text",
            "completion_evidence_value": "Done",
        },
    )
    agent = MobilePilotAndroidWorldAgent(
        object(),
        mode="hybrid",
        max_steps=3,
        policy=_QueuedPolicy([_parsed(action)]),
        progress_verifier_mode="off",
        trace_path=tmp_path / "trace.jsonl",
        runtime_version="v2.2",
    )
    agent._adapter = _FakeAdapter(
        ["same", "same"],
        verification_texts=[("Loading",), ("Done",)],
    )

    result = agent.step("wait until done")

    assert result.data["reason"] == "subgoal_confirmed"
    assert agent._subgoals.completed_goals == ["show Done"]
    assert not any(
        row["event"] == "loop_detected"
        for row in _trace_rows(tmp_path / "trace.jsonl")
    )


def test_semantic_capability_gap_is_not_retried_as_protocol_formatting(tmp_path):
    failed = ParseResult(
        error_kind=ErrorKind.UNSUPPORTED_ACTION_CAPABILITY,
        message="unsupported action capability ANSWER",
        raw_output='{"action":"ANSWER","text":"42"}',
    )
    policy = _QueuedPolicy([failed])
    agent = MobilePilotAndroidWorldAgent(
        object(),
        mode="hybrid",
        max_steps=3,
        policy=policy,
        trace_path=tmp_path / "trace.jsonl",
        runtime_version="v2.2",
    )
    agent._adapter = _FakeAdapter(["s0"])

    result = agent.step("answer the visible question")

    assert result.done
    assert result.data["reason"] == "unsupported_action_capability"
    assert len(policy.requests) == 1
    protocol_rows = [
        row for row in _trace_rows(tmp_path / "trace.jsonl")
        if row["event"] == "protocol_guard"
    ]
    assert protocol_rows[-1]["outcome"] == "not_attempted_for_semantic_capability_gap"


def test_v22_tree_supported_recovery_records_grounded_changed_action(tmp_path):
    failed_open = Action(ActionType.OPEN_APP, {"app_name": "missing"})
    grounded_click = Action(
        ActionType.CLICK_POINT,
        {"point": [10, 10], "ui_tree_reference": "Next"},
    )
    agent = MobilePilotAndroidWorldAgent(
        object(),
        mode="hybrid",
        max_steps=4,
        policy=_QueuedPolicy([_parsed(failed_open), _parsed(grounded_click)]),
        progress_verifier_mode="off",
        trace_path=tmp_path / "trace.jsonl",
        runtime_version="v2.2",
    )
    agent._adapter = _FakeAdapter(
        ["home", "replan", "after"],
        execution_results=[ActionResult(False, failed_open, "not installed")],
    )

    first = agent.step("open the next available page")
    second = agent.step("open the next available page")

    assert first.data["reason"] == "agent_replan_requested"
    assert not second.done
    tree_row = next(
        row for row in _trace_rows(tmp_path / "trace.jsonl")
        if row["event"] == "ui_tree_decision"
    )
    assert tree_row["result"] == "grounded"
    assert tree_row["chosen_ui_element"]["label"] == "Next"
    assert tree_row["changed_action"] is True


def test_v22_tree_supported_recovery_fails_closed_without_new_evidence(tmp_path):
    failed_open = Action(ActionType.OPEN_APP, {"app_name": "missing"})
    ungrounded_wait = Action(ActionType.WAIT, reason="try something different")
    agent = MobilePilotAndroidWorldAgent(
        object(),
        mode="hybrid",
        max_steps=4,
        policy=_QueuedPolicy([_parsed(failed_open), _parsed(ungrounded_wait)]),
        progress_verifier_mode="off",
        trace_path=tmp_path / "trace.jsonl",
        runtime_version="v2.2",
    )
    agent._adapter = _FakeAdapter(
        ["home", "replan"],
        execution_results=[ActionResult(False, failed_open, "not installed")],
    )

    agent.step("open the next available page")
    result = agent.step("open the next available page")

    assert result.done
    assert result.data["reason"] == "insufficient_new_evidence"
    assert [action.type for action in agent._adapter.executed_actions] == [
        ActionType.OPEN_APP
    ]
    replan = next(
        row for row in _trace_rows(tmp_path / "trace.jsonl")
        if row["event"] == "agent_recovery_replan"
    )
    assert replan["result"] == "insufficient_new_evidence"


def test_v22_recovery_allows_named_app_fallback_grounded_by_runtime_state(tmp_path):
    failed_swipe = Action(ActionType.SWIPE, {"direction": "up"})
    reopen = Action(ActionType.OPEN_APP, {"app_name": "Settings"})
    agent = MobilePilotAndroidWorldAgent(
        object(),
        mode="hybrid",
        max_steps=4,
        policy=_QueuedPolicy([_parsed(failed_swipe), _parsed(reopen)]),
        progress_verifier_mode="off",
        trace_path=tmp_path / "trace.jsonl",
        runtime_version="v2.2",
    )
    agent._subgoals.completed_goals.append("Open Settings")
    agent._adapter = _FakeAdapter(
        ["settings", "home", "home-tree", "settings-again"],
        execution_results=[ActionResult(False, failed_swipe, "left Settings")],
    )

    agent.step("turn brightness to max")
    result = agent.step("turn brightness to max")

    assert not result.done
    assert agent._adapter.executed_actions[-1].type is ActionType.OPEN_APP
    replan = next(
        row for row in _trace_rows(tmp_path / "trace.jsonl")
        if row["event"] == "agent_recovery_replan"
    )
    assert replan["result"] == "task_grounded_fallback"
