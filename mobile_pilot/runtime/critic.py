"""执行前的轻量 Critic：拒绝可由当前状态证明不合理的候选点。"""

from __future__ import annotations

from dataclasses import dataclass

from mobile_pilot.perception import ScreenState
from mobile_pilot.policy.grounding import GroundingCandidate, GroundingSource


@dataclass(frozen=True)
class CriticDecision:
    allowed: bool
    reason: str
    conflicting_element_id: str = ""


class PreActionCritic:
    """不重新规划，只在执行前拦截明显错误或陈旧的候选动作。"""

    def review(self, candidate: GroundingCandidate, state: ScreenState) -> CriticDecision:
        x, y = candidate.point
        width, height = state.image_size
        if not (0 <= x < width and 0 <= y < height):
            return CriticDecision(False, "Candidate point is outside the current screenshot.")

        if candidate.source is not GroundingSource.VISION:
            return CriticDecision(True, "Non-visual candidate is grounded in the current UI Tree.")

        for element in state.elements:
            if element.enabled and element.clickable and _contains(element.bounds, candidate.point):
                label = element.resource_id or element.text or element.content_description or element.stable_id
                return CriticDecision(
                    False,
                    "Visual candidate overlaps a currently clickable semantic element; request a new observation or escalate.",
                    label,
                )
        return CriticDecision(True, "Visual point does not overlap a current clickable semantic element.")


def _contains(bounds: tuple[int, int, int, int], point: tuple[int, int]) -> bool:
    left, top, right, bottom = bounds
    x, y = point
    return left <= x < right and top <= y < bottom
