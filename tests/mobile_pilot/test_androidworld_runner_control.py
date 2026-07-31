from types import SimpleNamespace

from scripts.run_mobilepilot_androidworld import _run_agent_loop, _should_retry_rejected_completion


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
