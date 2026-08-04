"""Multi-step GUI-Plus policy used only by the AndroidWorld integration.

This protocol is intentionally separate from :mod:`mobile_pilot.policy.gui_plus`.
The latter is frozen for the ScreenSpot single-step evaluation; changing the
AndroidWorld action space must never change a published ScreenSpot result.
"""

from __future__ import annotations

import base64
from dataclasses import dataclass
import io
import json
import os
import re
import time
from typing import Any, Callable

from PIL import Image

from mobile_pilot.androidworld.adapter import AndroidWorldTaskState
from mobile_pilot.core import Action, ActionType, ErrorKind, ParseResult
from mobile_pilot.perception import ScreenState
from mobile_pilot.policy.gui_plus import VisionCallMetrics


ANDROIDWORLD_ACTOR_PROMPT = """You are the action planner for an Android phone task.
Decide exactly one next action from the current screenshot. You may use the
optional accessibility elements only as supporting evidence; they are absent
in vision_only mode. Do not invent completion: choose PROPOSE_COMPLETE only
when the task goal is visibly complete.

When the task explicitly names an installed app, prefer OPEN_APP with its
short canonical name instead of navigating the app drawer.

Return exactly one JSON object, with no Markdown and no extra text:
{"action":"CLICK","coordinate":[0-1000,0-1000],"reason":"short reason"}
{"action":"TYPE","text":"text to enter","reason":"short reason"}
{"action":"SWIPE","direction":"up|down|left|right","reason":"short reason"}
{"action":"BACK","reason":"short reason"}
{"action":"OPEN_APP","app_name":"canonical installed app key (for example clock, not The Clock)","reason":"short reason"}
{"action":"WAIT","reason":"short reason"}
{"action":"PROPOSE_COMPLETE","reason":"short reason"}
"""

ANDROIDWORLD_ACTOR_V2_PROMPT = """You are the action planner inside an auditable Android GUI Agent Runtime.
Choose exactly one next action from the current screenshot and short-term
progress state. Accessibility elements are an on-demand tool, not guaranteed
context. If visual evidence is genuinely insufficient and no accessibility
elements are present, choose REQUEST_UI_TREE instead of guessing.

Use recovery feedback to replan. Do not repeat an action whose execution result
is uncertain, and do not guessingly repeat text entry, send, delete, confirm, or
other actions that may have side effects. PROPOSE_COMPLETE is only a proposal;
the AndroidWorld official reward is the final success decision.

Return exactly one JSON object, with no Markdown and no extra text. Use one of:
{"action":"CLICK","coordinate":[0-1000,0-1000],"reason":"short reason","subgoal":"current subgoal","expected_outcome":"what should visibly change"}
{"action":"TYPE","text":"text to enter","reason":"short reason","subgoal":"current subgoal","expected_outcome":"what should visibly change"}
{"action":"SWIPE","direction":"up|down|left|right","reason":"short reason","subgoal":"current subgoal","expected_outcome":"what should visibly change"}
{"action":"BACK","reason":"short reason","subgoal":"current subgoal","expected_outcome":"what should visibly change"}
{"action":"OPEN_APP","app_name":"canonical installed app key (for example clock, not The Clock)","reason":"short reason","subgoal":"current subgoal","expected_outcome":"what should visibly change"}
{"action":"WAIT","reason":"short reason","subgoal":"current subgoal","expected_outcome":"what should visibly change"}
{"action":"REQUEST_UI_TREE","reason":"specific visual uncertainty"}
{"action":"PROPOSE_COMPLETE","reason":"visible evidence that the goal is complete"}
"""


@dataclass(frozen=True)
class AndroidWorldActorRequest:
    task: AndroidWorldTaskState
    image: Image.Image
    screen: ScreenState
    include_ui_tree: bool


@dataclass(frozen=True)
class AndroidWorldActorDecision:
    result: ParseResult
    metrics: VisionCallMetrics


class AndroidWorldGuiPlusPolicy:
    """Task-agnostic multi-action Actor backed by DashScope GUI-Plus."""

    def __init__(
        self,
        *,
        api_key: str | None = None,
        base_url: str | None = None,
        model: str | None = None,
        request_timeout_seconds: float | None = None,
        client_factory: Callable[..., Any] | None = None,
    ) -> None:
        self._api_key = api_key or os.getenv("DASHSCOPE_API_KEY")
        self._base_url = base_url or os.getenv("DASHSCOPE_BASE_URL")
        self._model = model or os.getenv("MOBILEPILOT_ACTOR_MODEL", "gui-plus-2026-02-26")
        self._timeout = request_timeout_seconds or float(os.getenv("MOBILEPILOT_API_TIMEOUT_SECONDS", "90"))
        self._client_factory = client_factory

    def decide_with_metrics(self, request: AndroidWorldActorRequest) -> AndroidWorldActorDecision:
        if not self._api_key:
            return self._failed("DASHSCOPE_API_KEY is not configured.")
        if not self._base_url:
            return self._failed("DASHSCOPE_BASE_URL is not configured.")

        started = time.perf_counter()
        try:
            completion = self._make_client().chat.completions.create(
                model=self._model,
                messages=[
                    {
                        "role": "system",
                        "content": (
                            ANDROIDWORLD_ACTOR_V2_PROMPT
                            if request.task.runtime_version == "v2"
                            else ANDROIDWORLD_ACTOR_PROMPT
                        ),
                    },
                    {
                        "role": "user",
                        "content": [
                            {"type": "image_url", "image_url": {"url": _image_to_data_url(request.image)}},
                            {"type": "text", "text": _context_text(request)},
                        ],
                    },
                ],
                extra_body={"vl_high_resolution_images": True},
            )
            raw = completion.choices[0].message.content or ""
        except Exception as exc:
            return AndroidWorldActorDecision(
                ParseResult(error_kind=ErrorKind.MODEL_ERROR, message=f"GUI-Plus request failed: {exc}"),
                self._metrics(time.perf_counter() - started),
            )
        return AndroidWorldActorDecision(
            parse_androidworld_actor_output(
                raw,
                request.image.size,
                allow_v2_repairs=request.task.runtime_version == "v2",
            ),
            self._metrics(time.perf_counter() - started, getattr(completion, "usage", None)),
        )

    def _failed(self, message: str) -> AndroidWorldActorDecision:
        return AndroidWorldActorDecision(
            ParseResult(error_kind=ErrorKind.MODEL_ERROR, message=message), self._metrics(0.0)
        )

    def _make_client(self) -> Any:
        if self._client_factory:
            return self._client_factory(api_key=self._api_key, base_url=self._base_url)
        from openai import OpenAI

        return OpenAI(api_key=self._api_key, base_url=self._base_url, timeout=self._timeout, max_retries=0)

    def _metrics(self, latency: float, usage: Any = None) -> VisionCallMetrics:
        prompt = _usage_int(usage, "prompt_tokens")
        completion = _usage_int(usage, "completion_tokens")
        total = _usage_int(usage, "total_tokens")
        cost = prompt * 1.5 / 1_000_000 + completion * 4.5 / 1_000_000 if prompt is not None and completion is not None else None
        return VisionCallMetrics(self._model, latency, prompt, completion, total, cost)


def parse_androidworld_actor_output(
    raw_output: str,
    image_size: tuple[int, int],
    *,
    allow_v2_repairs: bool = False,
) -> ParseResult:
    """Parse one strict JSON action and convert normalized clicks to pixels."""
    try:
        try:
            payload = json.loads(_extract_json(raw_output))
        except (ValueError, json.JSONDecodeError):
            payload = _recover_minimal_payload(raw_output, allow_v2_repairs=allow_v2_repairs)
        kind = str(payload["action"]).strip().upper()
        if (
            allow_v2_repairs
            and kind == "SYSTEM_FUNCTION"
            and str(payload.get("function_name", "")).strip().lower() == "open_app"
        ):
            # GUI-Plus sometimes emits its native tool spelling even when the
            # prompt asks for OPEN_APP.  The explicit function and app_name
            # make this a protocol alias, not a guessed Agent action.
            kind = "OPEN_APP"
        reason = str(payload.get("reason", ""))
        subgoal = str(payload.get("subgoal", "")).strip()
        expected_outcome = str(payload.get("expected_outcome", ""))
        if kind == "CLICK":
            coordinate = payload["coordinate"]
            if not isinstance(coordinate, list) or len(coordinate) != 2:
                raise ValueError("CLICK coordinate must be a two-item list")
            x, y = coordinate
            if isinstance(x, bool) or isinstance(y, bool) or not isinstance(x, (int, float)) or not isinstance(y, (int, float)):
                raise ValueError("CLICK coordinate values must be numeric")
            width, height = image_size
            if 0 <= x <= 1000 and 0 <= y <= 1000:
                point = [round(x * (width - 1) / 1000), round(y * (height - 1) / 1000)]
                coordinate_space = "normalized_1000"
            elif 0 <= x < width and 0 <= y < height:
                point = [round(x), round(y)]
                coordinate_space = "image_pixels"
            else:
                raise ValueError("CLICK coordinate is neither normalized [0, 1000] nor inside the image")
            action = Action(
                ActionType.CLICK_POINT,
                _with_subgoal(
                    {"point": point, "coordinate_space": coordinate_space},
                    subgoal,
                ),
                reason,
                expected_outcome,
                source="androidworld_gui_plus",
            )
        elif kind == "TYPE":
            text = payload.get("text")
            if not isinstance(text, str) or not text:
                raise ValueError("TYPE requires non-empty text")
            action = Action(
                ActionType.TYPE_TEXT,
                _with_subgoal({"text": text}, subgoal),
                reason,
                expected_outcome,
                source="androidworld_gui_plus",
            )
        elif kind == "SWIPE":
            direction = _normalize_swipe_direction(payload.get("direction")) or _explicit_swipe_direction(reason)
            if direction not in {"left", "right", "up", "down"}:
                raise ValueError("SWIPE direction is invalid")
            action = Action(
                ActionType.SWIPE,
                _with_subgoal({"direction": direction}, subgoal),
                reason,
                expected_outcome,
                source="androidworld_gui_plus",
            )
        elif kind in {"BACK", "PRESS_BACK", "WAIT", "PROPOSE_COMPLETE"}:
            action = Action(
                ActionType("PRESS_BACK" if kind in {"BACK", "PRESS_BACK"} else kind),
                _with_subgoal({}, subgoal),
                reason=reason,
                expected_outcome=expected_outcome,
                source="androidworld_gui_plus",
            )
        elif kind == "OPEN_APP":
            app_name = payload.get("app_name")
            if not isinstance(app_name, str) or not app_name:
                raise ValueError("OPEN_APP requires app_name")
            action = Action(
                ActionType.OPEN_APP,
                _with_subgoal({"app_name": app_name}, subgoal),
                reason,
                expected_outcome,
                source="androidworld_gui_plus",
            )
        elif kind == "REQUEST_UI_TREE":
            action = Action(
                ActionType.CALL_TOOL,
                _with_subgoal({"tool": "ui_tree"}, subgoal),
                reason,
                expected_outcome,
                source="androidworld_gui_plus",
            )
        else:
            raise ValueError(f"unknown action {kind}")
    except (KeyError, TypeError, ValueError, json.JSONDecodeError) as exc:
        if not (raw_output or "").strip():
            error_kind = ErrorKind.EMPTY_OUTPUT
        elif "unknown action" in str(exc):
            error_kind = ErrorKind.UNKNOWN_ACTION
        else:
            error_kind = ErrorKind.PARSE_ERROR
        return ParseResult(
            error_kind=error_kind,
            message=f"Invalid AndroidWorld Actor output: {exc}",
            raw_output=raw_output,
        )
    return ParseResult(action=action, raw_output=raw_output)


def _context_text(request: AndroidWorldActorRequest) -> str:
    task = request.task
    lines = [
        f"Task goal: {task.goal}",
        f"Step: {task.step_index}; remaining steps: {task.remaining_steps}",
        f"Completed actions: {list(task.completed_action_summaries[-5:])}",
        f"Last verifier result: {task.last_verifier_result or 'none'}",
        f"Recent failure: {task.recent_failure or 'none'}",
    ]
    if task.runtime_version == "v2":
        lines.extend(
            [
                f"Current subgoal: {task.current_subgoal or 'choose the next safe subgoal'}",
                f"Current blocker: {task.current_blocker or 'none'}",
                f"Next verification: {task.next_verification or 'verify the visible result of the next action'}",
                f"Recovery instruction: {task.recovery_reason or 'none'}",
                f"Protocol correction: {task.protocol_feedback or 'none'}",
            ]
        )
    if request.include_ui_tree:
        elements = [
            {"text": item.text, "description": item.content_description, "resource_id": item.resource_id, "bounds": item.bounds, "clickable": item.clickable, "editable": item.editable}
            for item in request.screen.elements[:80]
        ]
        lines.append("Optional accessibility elements: " + json.dumps(elements, ensure_ascii=False))
    return "\n".join(lines)


def _extract_json(raw: str) -> str:
    candidate = (raw or "").strip()
    candidate = re.sub(r"^```(?:json)?\s*|\s*```$", "", candidate, flags=re.IGNORECASE)
    start = candidate.find("{")
    if start < 0:
        raise ValueError("response does not contain a JSON object")
    try:
        _, end = json.JSONDecoder().raw_decode(candidate[start:])
    except json.JSONDecodeError as exc:
        raise ValueError("response does not contain a complete JSON object") from exc
    return candidate[start : start + end]


def _recover_minimal_payload(
    raw: str,
    *,
    allow_v2_repairs: bool,
) -> dict[str, Any]:
    """Recover only an unambiguous action from otherwise invalid model JSON.

    Some model responses put an unescaped quote inside an optional ``reason``.
    We never attempt broad JSON repair: only the required action field and its
    small, independently validated parameter are accepted.  Text entry stays
    strict because guessing a malformed string could change user data.
    """
    action_match = re.search(r'"action"\s*:\s*"([A-Za-z_]+)"', raw or "")
    if not action_match:
        raise ValueError("response does not contain a recoverable action")
    kind = action_match.group(1).upper()
    if kind == "CLICK":
        coordinate_pattern = (
            r'"coordinate"\s*:\s*\[?\s*(-?\d+(?:\.\d+)?)\s*,\s*'
            r'(-?\d+(?:\.\d+)?)\s*\]?(?=\s*(?:,\s*"|}|$))'
            if allow_v2_repairs
            else r'"coordinate"\s*:\s*\[\s*(-?\d+(?:\.\d+)?)\s*,\s*(-?\d+(?:\.\d+)?)\s*\]'
        )
        coordinate = re.search(coordinate_pattern, raw)
        if not coordinate:
            raise ValueError("malformed CLICK coordinate cannot be recovered")
        return {"action": kind, "coordinate": [float(coordinate.group(1)), float(coordinate.group(2))]}
    if kind == "SWIPE":
        direction = re.search(r'"direction"\s*:\s*"((?:swipe[_ -]?)?(?:left|right|up|down))"', raw, flags=re.IGNORECASE)
        if direction:
            return {"action": kind, "direction": _normalize_swipe_direction(direction.group(1))}
        inferred = _explicit_swipe_direction(raw)
        if inferred:
            return {"action": kind, "direction": inferred}
        raise ValueError("malformed SWIPE direction cannot be recovered")
    if kind in {"BACK", "PRESS_BACK", "WAIT", "PROPOSE_COMPLETE"}:
        return {"action": kind}
    if allow_v2_repairs and kind == "OPEN_APP":
        app_name = re.search(r'"app_name"\s*:\s*"([^"\r\n]+)"', raw)
        if not app_name or not app_name.group(1).strip():
            raise ValueError("malformed OPEN_APP output cannot be recovered safely")
        return {"action": kind, "app_name": app_name.group(1).strip()}
    raise ValueError(f"malformed {kind} output cannot be recovered safely")


def _image_to_data_url(image: Image.Image) -> str:
    buffer = io.BytesIO()
    image.save(buffer, format="PNG")
    return "data:image/png;base64," + base64.b64encode(buffer.getvalue()).decode("ascii")


def _with_subgoal(parameters: dict[str, Any], subgoal: str) -> dict[str, Any]:
    if subgoal:
        parameters["subgoal"] = subgoal
    return parameters


def _usage_int(usage: Any, name: str) -> int | None:
    value = getattr(usage, name, None) if usage is not None else None
    if value is None and isinstance(usage, dict):
        value = usage.get(name)
    return int(value) if value is not None else None


def _explicit_swipe_direction(text: str) -> str | None:
    """Return a direction only for an explicit natural-language swipe phrase."""
    match = re.search(r"\bswipe\s+(up|down|left|right)\b", text or "", flags=re.IGNORECASE)
    return match.group(1).lower() if match else None


def _normalize_swipe_direction(value: object) -> str | None:
    """Accept the model's unambiguous ``swipe_up`` spelling as ``up``.

    The action protocol continues to expose only AndroidWorld's four canonical
    directions.  This is parser interoperability, not a policy fallback:
    unrecognized direction values still fail closed.
    """
    if not isinstance(value, str):
        return None
    normalized = value.strip().lower().replace("-", "_").replace(" ", "_")
    if normalized.startswith("swipe_"):
        normalized = normalized.removeprefix("swipe_")
    return normalized if normalized in {"left", "right", "up", "down"} else None
