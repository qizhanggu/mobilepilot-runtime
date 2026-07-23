"""UI Tree 优先、视觉点位兜底的 Grounding 策略。"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum

from mobile_pilot.perception import ScreenState, UiElement


class GroundingSource(str, Enum):
    UI_TREE = "UI_TREE"
    VISION = "VISION"
    GRID = "GRID"


@dataclass(frozen=True)
class SemanticTarget:
    resource_id: str = ""
    text: str = ""
    content_description: str = ""


@dataclass(frozen=True)
class PointTarget:
    point: tuple[int, int]
    source: GroundingSource
    reason: str = ""


@dataclass(frozen=True)
class GroundingCandidate:
    point: tuple[int, int]
    source: GroundingSource
    confidence: float
    reason: str
    element: UiElement | None = None


class Grounder:
    """按 resource-id、文本、content description 的顺序定位元素。"""

    def resolve(self, target: SemanticTarget | PointTarget, state: ScreenState) -> GroundingCandidate:
        if isinstance(target, PointTarget):
            return GroundingCandidate(
                point=target.point,
                source=target.source,
                confidence=0.55 if target.source is GroundingSource.VISION else 0.35,
                reason=target.reason or "UI Tree does not provide a usable target; using visual fallback.",
            )

        match = self._find_semantic_match(target, state.elements)
        if match is None:
            raise LookupError("Semantic target is absent from the current UI Tree; visual fallback is required.")
        element, confidence, reason = match
        if not element.enabled:
            raise LookupError("Semantic target exists but is disabled.")
        return GroundingCandidate(
            point=element.center,
            source=GroundingSource.UI_TREE,
            confidence=confidence,
            reason=reason,
            element=element,
        )

    @staticmethod
    def _find_semantic_match(target: SemanticTarget, elements: tuple[UiElement, ...]):
        if target.resource_id:
            for element in elements:
                if element.resource_id == target.resource_id:
                    return element, 0.99, "Matched stable resource-id."
        if target.text:
            for element in elements:
                if element.text == target.text:
                    return element, 0.90, "Matched visible text."
        if target.content_description:
            for element in elements:
                if element.content_description == target.content_description:
                    return element, 0.85, "Matched content description."
        return None
