"""将 UI Tree 语义定位与旧视觉策略连接为可审计的两级 grounding。"""

from __future__ import annotations

from enum import Enum
from typing import Any

from mobile_pilot.core import ActionType
from mobile_pilot.perception import ScreenState

from .grounding import Grounder, GroundingCandidate, GroundingSource, PointTarget, SemanticTarget
from .legacy_vision import LegacyVisionPolicy


class HybridGrounder:
    """按显式模式组合视觉候选与 UI Tree，不把路线写死。

    视觉策略沿用旧 Agent 的 ``[0, 1000]`` 归一化坐标协议。这里仅产生候选点，
    不执行设备动作；后续 Runtime 仍须经过安全审批、重新观察和执行后验证。
    """

    def __init__(
        self,
        ui_grounder: Grounder | None = None,
        *,
        mode: "GroundingMode | str" = "tree_first",
    ):
        self._ui_grounder = ui_grounder or Grounder()
        self.mode = GroundingMode(mode)

    @property
    def requires_ui_tree(self) -> bool:
        """当前模式是否需要 Runtime 按需读取 UI Tree。"""

        return self.mode is not GroundingMode.VISION_ONLY

    def resolve(
        self,
        target: SemanticTarget | PointTarget,
        state: ScreenState,
        *,
        vision_policy: LegacyVisionPolicy | None = None,
        vision_input: Any = None,
    ) -> GroundingCandidate:
        if isinstance(target, PointTarget):
            return self._ui_grounder.resolve(target, state)

        if self.mode in (GroundingMode.VISION_ONLY, GroundingMode.VISION_WITH_TREE_AUX):
            return self._resolve_vision(state, vision_policy, vision_input)

        try:
            return self._ui_grounder.resolve(target, state)
        except LookupError as exc:
            if vision_policy is None:
                raise
            ui_error = exc

        return self._resolve_vision(state, vision_policy, vision_input, ui_error=ui_error)

    def _resolve_vision(
        self,
        state: ScreenState,
        vision_policy: LegacyVisionPolicy | None,
        vision_input: Any,
        *,
        ui_error: Exception | None = None,
    ) -> GroundingCandidate:
        if vision_policy is None:
            raise LookupError(f"{self.mode.value} requires a visual policy") from ui_error

        parsed = vision_policy.decide(vision_input)
        if not parsed.is_success or parsed.action is None:
            raise LookupError(
                f"Visual policy returned an invalid candidate: {parsed.message}"
            ) from ui_error
        if parsed.action.type is not ActionType.CLICK_POINT:
            raise LookupError(
                "Visual policy did not propose a click point."
            ) from ui_error

        point = _normalized_point_to_pixels(parsed.action.parameters.get("point"), state.image_size)
        return GroundingCandidate(
            point=point,
            source=GroundingSource.VISION,
            confidence=0.55,
            reason=f"Visual candidate selected in {self.mode.value} mode.",
        )


class GroundingMode(str, Enum):
    """视觉与 UI Tree 的三种可消融运行模式。"""

    VISION_ONLY = "vision_only"
    VISION_WITH_TREE_AUX = "vision_with_tree_aux"
    TREE_FIRST = "tree_first"


def _normalized_point_to_pixels(value: object, image_size: tuple[int, int]) -> tuple[int, int]:
    """将旧协议的归一化坐标严格转换为当前截图的像素坐标。"""

    if not isinstance(value, (list, tuple)) or len(value) != 2:
        raise LookupError("Visual fallback click point must be a two-item normalized coordinate.")
    x, y = value
    if isinstance(x, bool) or isinstance(y, bool) or not isinstance(x, (int, float)) or not isinstance(y, (int, float)):
        raise LookupError("Visual fallback click point must contain numeric coordinates.")
    if not (0 <= x <= 1000 and 0 <= y <= 1000):
        raise LookupError("Visual fallback click point is outside the legacy [0, 1000] range.")
    width, height = image_size
    return (int(x / 1000 * width), int(y / 1000 * height))
