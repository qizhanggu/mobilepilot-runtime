"""Map MobilePilot observations and actions onto an AndroidWorld environment.

The module deliberately imports AndroidWorld only at execution time.  This
keeps normal MobilePilot tests independent from the emulator installation.
"""

from __future__ import annotations

from dataclasses import dataclass, field
import hashlib
import io
import re
from typing import Any, Callable

from PIL import Image

from mobile_pilot.core import Action, ActionResult, ActionType
from mobile_pilot.perception import ScreenState, UiElement


@dataclass(frozen=True)
class AndroidWorldTaskState:
    """The per-step context supplied to a multi-step MobilePilot Actor."""

    goal: str
    step_index: int
    remaining_steps: int
    completed_action_summaries: tuple[str, ...] = ()
    last_verifier_result: str = ""
    recent_failure: str = ""
    current_subgoal: str = ""
    current_blocker: str = ""
    next_verification: str = ""
    recovery_reason: str = ""
    protocol_feedback: str = ""
    runtime_version: str = "v1"
    plan_mode: str = "direct"
    completed_checkpoints: tuple[str, ...] = ()
    active_checkpoint: str = ""
    active_checkpoint_evidence: str = ""
    remaining_checkpoints: tuple[str, ...] = ()
    recovery_level: str = ""
    active_subgoal: str = ""
    active_subgoal_evidence: str = ""
    completed_subgoals: tuple[str, ...] = ()
    subgoal_revision_allowed: bool = False
    progress_verifier_mode: str = "off"


@dataclass(frozen=True)
class MappedAndroidWorldAction:
    """An official action payload or an AgentInteractionResult completion signal."""

    payload: dict[str, Any] | None
    done: bool


class AndroidWorldAdapter:
    """Thin, task-agnostic bridge around AndroidWorld's live ``AndroidEnv``.

    ``PROPOSE_COMPLETE`` only returns ``done=True``.  The caller must use the
    benchmark task's ``is_successful(env)`` reward as the final success signal.
    """

    def __init__(self, env: Any):
        self._env = env

    def observe(
        self,
        *,
        include_ui_tree: bool,
        include_context_signals: bool = False,
    ) -> tuple[Image.Image, ScreenState]:
        state = self._env.get_state(wait_to_stabilize=True)
        image = Image.fromarray(state.pixels)
        # AndroidWorld already returns accessibility metadata with the state.
        # Package is retained as a cheap context signal, but element content is
        # exposed to the Actor only after an explicit on-demand Tree request.
        raw_elements = tuple(getattr(state, "ui_elements", ()) or ())
        mapped_elements = tuple(
            _to_mobilepilot_element(item, index)
            for index, item in enumerate(raw_elements)
        ) if include_ui_tree or include_context_signals else ()
        elements = mapped_elements if include_ui_tree else ()
        package = ""
        if include_ui_tree or include_context_signals:
            package = next((item.package_name or "" for item in raw_elements if getattr(item, "package_name", "")), "")
        context_elements = mapped_elements if include_context_signals else elements
        return image, _screen_state(
            image,
            package,
            elements,
            context_elements=context_elements,
        )

    def execute(self, action: Action) -> ActionResult:
        mapped = self.map_action(action)
        if mapped.done:
            return ActionResult(
                executed=False,
                action=action,
                message="Actor proposed completion; official reward is still required.",
                details={"propose_complete": True},
            )
        assert mapped.payload is not None
        from android_world.env import json_action

        try:
            self._env.execute_action(json_action.JSONAction(**mapped.payload))
        except Exception as exc:
            return ActionResult(
                executed=False,
                action=action,
                message=f"AndroidWorld execution failed: {exc}",
                details={"androidworld_action": mapped.payload, "exception_type": type(exc).__name__},
            )
        return ActionResult(
            executed=True,
            action=action,
            message="Executed through AndroidWorld.",
            details={"androidworld_action": mapped.payload},
        )

    @staticmethod
    def map_action(action: Action) -> MappedAndroidWorldAction:
        params = action.parameters
        if action.type is ActionType.PROPOSE_COMPLETE:
            return MappedAndroidWorldAction(payload=None, done=True)
        if action.type is ActionType.CLICK_POINT:
            x, y = _point(params)
            return MappedAndroidWorldAction({"action_type": "click", "x": x, "y": y}, False)
        if action.type is ActionType.TYPE_TEXT:
            text = _required_string(params, "text")
            return MappedAndroidWorldAction({"action_type": "input_text", "text": text}, False)
        if action.type is ActionType.SWIPE:
            return MappedAndroidWorldAction(
                {"action_type": "swipe", "direction": _direction(params)}, False
            )
        if action.type is ActionType.SCROLL:
            return MappedAndroidWorldAction(
                {"action_type": "scroll", "direction": _direction(params)}, False
            )
        if action.type is ActionType.PRESS_BACK:
            return MappedAndroidWorldAction({"action_type": "navigate_back"}, False)
        if action.type is ActionType.OPEN_APP:
            return MappedAndroidWorldAction(
                {"action_type": "open_app", "app_name": _normalize_app_name(_required_string(params, "app_name"))}, False
            )
        if action.type is ActionType.WAIT:
            return MappedAndroidWorldAction({"action_type": "wait"}, False)
        raise ValueError(f"Action type is not supported by AndroidWorld: {action.type.value}")


def _screen_state(
    image: Image.Image,
    package: str,
    elements: tuple[UiElement, ...],
    *,
    context_elements: tuple[UiElement, ...] | None = None,
) -> ScreenState:
    buffer = io.BytesIO()
    image.save(buffer, format="PNG")
    screenshot_hash = hashlib.sha256(buffer.getvalue()).hexdigest()
    signature = "|".join([package, str(image.size), str(elements), screenshot_hash])
    exact = hashlib.sha256(signature.encode("utf-8")).hexdigest()[:24]
    visual = _visual_fingerprint(image)
    signal_elements = context_elements if context_elements is not None else elements
    semantic = _semantic_fingerprint(signal_elements)
    verification_texts = tuple(
        " | ".join(
            [item.text, item.content_description, item.resource_id, item.class_name]
        ).strip()
        for item in signal_elements
        if any(
            value.strip()
            for value in (
                item.text,
                item.content_description,
                item.resource_id,
                item.class_name,
            )
        )
    )
    return ScreenState(
        image_size=image.size,
        package_activity=package,
        elements=elements,
        fingerprint=exact,
        exact_fingerprint=screenshot_hash,
        visual_fingerprint=visual,
        semantic_fingerprint=semantic,
        verification_texts=verification_texts,
    )


def _visual_fingerprint(image: Image.Image) -> str:
    """Return a compact page-similarity signal, not a grounding feature."""
    gray = image.convert("L")
    width, height = gray.size
    # Status/navigation bars contain clocks and animations that should not turn
    # a stable app page into apparent progress.
    top = min(max(round(height * 0.04), 0), max(height - 1, 0))
    bottom = max(top + 1, height - round(height * 0.04))
    content = gray.crop((0, top, width, bottom)).resize((16, 16))
    pixels = list(content.getdata())
    mean = sum(pixels) / len(pixels)
    bits = "".join("1" if value >= mean else "0" for value in pixels)
    return f"{int(bits, 2):064x}"


def _semantic_fingerprint(elements: tuple[UiElement, ...]) -> str:
    if not elements:
        return ""
    rows = sorted(
        "|".join(
            [
                item.resource_id.strip().lower(),
                item.text.strip().lower(),
                item.content_description.strip().lower(),
                item.class_name.strip().lower(),
                str(item.clickable),
                str(item.editable),
            ]
        )
        for item in elements
    )
    return hashlib.sha256("\n".join(rows).encode("utf-8")).hexdigest()[:24]


def _to_mobilepilot_element(raw: Any, index: int) -> UiElement:
    bbox = getattr(raw, "bbox_pixels", None) or getattr(raw, "bbox", None)
    if bbox is None:
        bounds = (0, 0, 1, 1)
    else:
        bounds = (int(bbox.x_min), int(bbox.y_min), int(bbox.x_max), int(bbox.y_max))
    resource_id = getattr(raw, "resource_id", None) or getattr(raw, "resource_name", None) or ""
    text = getattr(raw, "text", None) or ""
    description = getattr(raw, "content_description", None) or ""
    source = f"{resource_id}|{text}|{description}|{bounds}|{index}"
    return UiElement(
        stable_id=hashlib.sha256(source.encode("utf-8")).hexdigest()[:16],
        resource_id=resource_id,
        text=text,
        content_description=description,
        class_name=getattr(raw, "class_name", None) or "",
        bounds=bounds,
        clickable=bool(getattr(raw, "is_clickable", False)),
        enabled=getattr(raw, "is_enabled", True) is not False,
        editable=bool(getattr(raw, "is_editable", False)),
    )


def _point(params: dict[str, Any]) -> tuple[int, int]:
    point = params.get("point")
    if not isinstance(point, (tuple, list)) or len(point) != 2:
        raise ValueError("CLICK_POINT requires a two-item point parameter")
    x, y = point
    if isinstance(x, bool) or isinstance(y, bool) or not isinstance(x, (int, float)) or not isinstance(y, (int, float)):
        raise ValueError("CLICK_POINT coordinates must be numeric")
    return int(x), int(y)


def _required_string(params: dict[str, Any], key: str) -> str:
    value = params.get(key)
    if not isinstance(value, str) or not value:
        raise ValueError(f"{key} must be a non-empty string")
    return value


def _direction(params: dict[str, Any]) -> str:
    direction = _required_string(params, "direction")
    if direction not in {"left", "right", "up", "down"}:
        raise ValueError("direction must be one of left, right, up, down")
    return direction


def _normalize_app_name(app_name: str) -> str:
    """Remove display-name articles before AndroidWorld resolves its app key.

    AndroidWorld accepts canonical keys such as ``clock`` and otherwise treats
    text as an Android package.  This is a task-independent compatibility
    normalization; it does not map one benchmark task to an action sequence.
    """
    normalized = re.sub(r"^\s*(?:the|an|a)\s+", "", app_name, flags=re.IGNORECASE).strip()
    return normalized or app_name
