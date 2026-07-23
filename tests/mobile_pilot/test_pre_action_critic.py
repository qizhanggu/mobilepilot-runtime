from mobile_pilot.policy import GroundingCandidate, GroundingSource
from mobile_pilot.runtime import PreActionCritic

from test_hybrid_grounding import make_state


def test_critic_blocks_visual_point_overlapping_semantic_button():
    decision = PreActionCritic().review(
        GroundingCandidate(
            point=(630, 310),
            source=GroundingSource.VISION,
            confidence=0.55,
            reason="model candidate",
        ),
        make_state(),
    )

    assert not decision.allowed
    assert decision.conflicting_element_id.endswith("search_button")


def test_critic_allows_visual_point_not_claimed_by_ui_tree():
    decision = PreActionCritic().review(
        GroundingCandidate(
            point=(630, 800),
            source=GroundingSource.VISION,
            confidence=0.55,
            reason="model candidate",
        ),
        make_state(),
    )

    assert decision.allowed
