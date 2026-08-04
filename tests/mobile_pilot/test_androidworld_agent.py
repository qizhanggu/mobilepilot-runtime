import json
from types import SimpleNamespace

from PIL import Image

from mobile_pilot.androidworld.actor import AndroidWorldActorDecision
from mobile_pilot.androidworld.agent import MobilePilotAndroidWorldAgent
from mobile_pilot.androidworld.runtime_state import RuntimeProgress
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


class _FakeAdapter:
    def __init__(self, fingerprints, *, execution_results=None):
        self.fingerprints = list(fingerprints)
        self.execution_results = list(execution_results or [])
        self.include_tree_calls = []
        self.executed_actions = []

    def observe(self, *, include_ui_tree):
        self.include_tree_calls.append(include_ui_tree)
        fingerprint = self.fingerprints.pop(0)
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
            package_activity="test",
            elements=elements,
            fingerprint=fingerprint,
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
