from types import SimpleNamespace

from mobile_pilot.androidworld.agent import MobilePilotAndroidWorldAgent


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
            {"step": 3, "reason": "official reward remained zero", "mode": "hybrid"},
        )
    ]
