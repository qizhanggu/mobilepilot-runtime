from types import SimpleNamespace

from scripts.run_mobilepilot_androidworld import _run_agent_loop, _should_retry_rejected_completion
from scripts.run_androidworld_heldout import _run_one


def test_retries_premature_completion_when_an_action_step_remains():
    assert _should_retry_rejected_completion(
        {"reason": "actor_proposed_complete", "steps": 7},
        max_steps=8,
        already_rejected=False,
    )


def test_does_not_retry_completion_after_an_official_rejection():
    assert not _should_retry_rejected_completion(
        {"reason": "actor_proposed_complete", "steps": 7},
        max_steps=8,
        already_rejected=True,
    )


def test_does_not_retry_when_action_budget_is_exhausted_or_reason_differs():
    assert not _should_retry_rejected_completion(
        {"reason": "actor_proposed_complete", "steps": 8},
        max_steps=8,
        already_rejected=False,
    )
    assert not _should_retry_rejected_completion(
        {"reason": "invalid_actor_output", "steps": 3},
        max_steps=8,
        already_rejected=False,
    )


def test_runner_loop_continues_after_one_rejected_completion_with_action_budget_left():
    class FakeAgent:
        def __init__(self):
            self.calls = 0
            self.rejections = 0

        def step(self, _goal):
            self.calls += 1
            if self.calls == 1:
                return SimpleNamespace(done=True, data={"reason": "actor_proposed_complete", "steps": 7})
            return SimpleNamespace(done=True, data={"reason": "step_budget_exhausted", "steps": 8})

        def reject_completion_proposal(self, _reason):
            self.rejections += 1

    agent = FakeAgent()
    result, rewards = _run_agent_loop(agent, "goal", lambda: 0.0, max_steps=8)

    assert agent.calls == 2
    assert agent.rejections == 1
    assert result.data["reason"] == "step_budget_exhausted"
    assert rewards == [0.0, 0.0]


def test_runner_records_official_reward_for_nonterminal_and_terminal_steps():
    class FakeAgent:
        def __init__(self):
            self.calls = 0
            self.recorded = []

        def step(self, _goal):
            self.calls += 1
            return SimpleNamespace(
                done=self.calls == 2,
                data={
                    "reason": "step_budget_exhausted" if self.calls == 2 else "",
                    "steps": self.calls,
                },
            )

        def record_official_reward(self, reward, *, terminal):
            self.recorded.append((reward, terminal))

    agent = FakeAgent()
    rewards = iter([0.0, 0.0])

    _run_agent_loop(agent, "goal", lambda: next(rewards), max_steps=2)

    assert agent.recorded == [(0.0, False), (0.0, True)]


def test_runner_does_not_stop_on_partial_composite_reward():
    class FakeAgent:
        def __init__(self):
            self.calls = 0
            self.recorded = []

        def step(self, _goal):
            self.calls += 1
            return SimpleNamespace(done=False, data={"steps": self.calls})

        def record_official_reward(self, reward, *, terminal):
            self.recorded.append((reward, terminal))

    agent = FakeAgent()
    rewards = iter([0.5, 1.0])

    result, observed = _run_agent_loop(
        agent, "composite goal", lambda: next(rewards), max_steps=2
    )

    assert agent.calls == 2
    assert result.done is False
    assert observed == [0.5, 1.0]
    assert agent.recorded == [(0.5, False), (1.0, True)]


def test_historical_heldout_runner_pins_v1_runtime(monkeypatch, tmp_path):
    captured = {}

    def fake_run(command, **kwargs):
        captured["command"] = command
        return SimpleNamespace(
            returncode=0,
            stdout='{"official_reward": 0.0, "agent_data": {}}\n',
            stderr="",
        )

    monkeypatch.setattr("scripts.run_androidworld_heldout.subprocess.run", fake_run)
    monkeypatch.setattr(
        "scripts.run_androidworld_heldout._trace_metrics",
        lambda _path: {},
    )
    manifest = SimpleNamespace(max_action_steps=12, seed=0, model="model")
    args = SimpleNamespace(
        adb_path="adb.exe",
        task_timeout_seconds=10,
    )

    _run_one(
        manifest,
        "ClockStopWatchRunning",
        "hybrid",
        args,
        tmp_path / "trace.jsonl",
        {},
    )

    index = captured["command"].index("--runtime-version")
    assert captured["command"][index + 1] == "v1"
