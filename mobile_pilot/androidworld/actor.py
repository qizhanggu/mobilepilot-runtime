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
from mobile_pilot.androidworld.runtime_state import Checkpoint, CheckpointEvidence, PlanState
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

ANDROIDWORLD_ACTOR_V21_CHECKLIST_SUFFIX = """

Runtime has supplied one active checkpoint. Work toward that checkpoint while
keeping the whole task goal in view. When its frozen evidence is visibly
satisfied, you may return this additional action:
{"action":"PROPOSE_CHECKPOINT_COMPLETE","observed_evidence":"what is visible now","reason":"why the frozen evidence is satisfied"}
This is only a proposal; Runtime verifies it. Do not use this action when there
is no active checkpoint. Do not act on a later checkpoint early.
"""

ANDROIDWORLD_ACTOR_V21_ALL_CHECKPOINTS_DONE_SUFFIX = """

All planned checkpoints are confirmed. Re-check the whole task goal. Use
PROPOSE_COMPLETE only if the whole task is visibly complete; otherwise choose a
normal corrective action. Do not propose checkpoint completion again.
"""

ANDROIDWORLD_ACTOR_V22_TOOL_PROMPT = """You are the GUI Actor inside an auditable Android Agent Runtime.
Look at the current screenshot, the whole task goal, and the frozen current
subgoal. Choose exactly one next phone action. Runtime owns subgoal creation,
completion evidence, verification, and recovery state; do not create or edit
those fields yourself.

Use recovery feedback to choose a meaningfully different safe action. Do not
guessingly repeat text entry, send, delete, confirm, or another action with a
side effect. If the screenshot is genuinely insufficient and no accessibility
elements are present, request the UI Tree. Whole-task completion and subgoal
completion are proposals only; Runtime and AndroidWorld decide whether they
are true.

When the frozen subgoal is to open a named installed app, prefer open_app with
its short canonical app name instead of searching the launcher or app drawer.

<tools>
{"type":"function","function":{"name":"mobile_action","description":"Execute exactly one Android GUI action or make one bounded completion proposal.","parameters":{"type":"object","properties":{"action":{"type":"string","enum":["click","long_press","drag","type","swipe","back","open_app","wait","answer","request_ui_tree","propose_subgoal_complete","propose_complete"]},"coordinate":{"type":"array","items":{"type":"number"},"minItems":2,"maxItems":2,"description":"Click or long-press point in 0-1000 normalized screenshot coordinates."},"start_coordinate":{"type":"array","items":{"type":"number"},"minItems":2,"maxItems":2},"end_coordinate":{"type":"array","items":{"type":"number"},"minItems":2,"maxItems":2},"duration_ms":{"type":"integer","minimum":100,"maximum":3000},"text":{"type":"string"},"direction":{"type":"string","enum":["up","down","left","right"]},"app_name":{"type":"string"},"observed_evidence":{"type":"string"},"ui_tree_reference":{"type":"string","description":"When Recovery supplied a UI Tree, cite the visible label or resource-id supporting this action."},"reason":{"type":"string"}},"required":["action"]}}}
</tools>

Use long_press only when the UI requires a press-and-hold gesture. Use drag only
when an item or slider must move between two visible points. Use answer only
when the task explicitly asks an information question and the answer is already
supported by visible evidence; answer does not touch the screen.
When Recovery supplied accessibility elements, ground the new action in one
visible element and set ui_tree_reference to its label or resource-id. If the
Tree offers no new evidence, do not invent a random alternative.

Return exactly one tool call and no other text:
<tool_call>
{"name":"mobile_action","arguments":{"action":"click","coordinate":[500,500],"reason":"short reason"}}
</tool_call>
"""

ANDROIDWORLD_PLANNER_PROMPT = """You create a short, auditable checkpoint plan for an Android task.
Decide from task structure, not guessed click count. Use checklist mode only
when the task has multiple fields or constraints, crosses pages, must find a
specific object, must save/submit, or contains a side effect that needs
verification. Otherwise use direct mode.

Each checklist checkpoint must be independently verifiable. Evidence kind must
be one of ui_text, ui_state, package_activity, visual. Evidence should describe
a visible state, never an action. Produce 2 to 6 checkpoints. Do not include
coordinates or a fixed click sequence.
Direct mode must have an empty checkpoints list. If any checkpoint is useful,
use checklist mode. package_activity evidence must be only a package or app
identifier, never a sentence describing screen content.

Return exactly one JSON object:
{"mode":"direct","reason":"why one reactive path is enough","checkpoints":[]}
or
{"mode":"checklist","reason":"why checkpoints help","checkpoints":[{"goal":"one subgoal","evidence":{"kind":"ui_text|ui_state|package_activity|visual","value":"specific state to verify"}}]}
"""

ANDROIDWORLD_PLAN_RECOVERY_PROMPT = """Revise only the active and remaining checkpoints after a failed recovery.
Confirmed checkpoints are locked and must not be repeated or changed. Keep the
whole task goal, remove a wrong assumption, and return 1 to 6 replacement
checkpoints with verifiable evidence. Do not provide coordinates or actions.

Return exactly one JSON object:
{"mode":"checklist","reason":"specific reason for revision","checkpoints":[{"goal":"replacement subgoal","evidence":{"kind":"ui_text|ui_state|package_activity|visual","value":"specific state to verify"}}]}
"""

ANDROIDWORLD_CHECKPOINT_VERIFIER_PROMPT = """You are a constrained checkpoint Verifier, not an Actor.
Judge only whether the current screenshot and optional accessibility elements
prove the frozen checkpoint evidence. Do not infer success from the Actor's
claim and do not suggest an action. If evidence is missing or ambiguous, choose
uncertain.

Return exactly one JSON object:
{"decision":"confirmed|not_confirmed|uncertain","evidence":"brief visible evidence"}
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


@dataclass(frozen=True)
class AndroidWorldPlanDecision:
    plan: PlanState | None
    metrics: VisionCallMetrics
    message: str = ""
    raw_output: str = ""


@dataclass(frozen=True)
class AndroidWorldCheckpointDecision:
    decision: str
    evidence: str
    metrics: VisionCallMetrics
    message: str = ""
    raw_output: str = ""


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
                        "content": _actor_prompt(request.task),
                    },
                    {
                        "role": "user",
                        "content": [
                            {"type": "image_url", "image_url": {"url": _image_to_data_url(request.image)}},
                            {"type": "text", "text": _context_text(request)},
                        ],
                    },
                ],
                extra_body={
                    "vl_high_resolution_images": True,
                    "enable_thinking": False,
                },
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
                allow_v2_repairs=request.task.runtime_version in {"v2", "v2.1", "v2.2"},
                allow_v21_actions=request.task.runtime_version == "v2.1",
                allow_v22_actions=request.task.runtime_version == "v2.2",
            ),
            self._metrics(time.perf_counter() - started, getattr(completion, "usage", None)),
        )

    def plan_with_metrics(
        self,
        *,
        goal: str,
        image: Image.Image,
        current_plan: PlanState | None = None,
        recovery_reason: str = "",
    ) -> AndroidWorldPlanDecision:
        if not self._api_key or not self._base_url:
            return AndroidWorldPlanDecision(
                None,
                self._metrics(0.0),
                "Planner API credentials are not configured.",
            )
        recovering = current_plan is not None
        context = [f"Task goal: {goal}"]
        if recovering:
            context.extend(
                [
                    f"Locked completed checkpoints: {list(current_plan.completed_goals())}",
                    f"Current unfinished checkpoints: {[item.goal for item in current_plan.checkpoints if item.status != 'done']}",
                    f"Recovery trigger: {recovery_reason}",
                ]
            )
        started = time.perf_counter()
        try:
            completion = self._make_client().chat.completions.create(
                model=self._model,
                messages=[
                    {
                        "role": "system",
                        "content": (
                            ANDROIDWORLD_PLAN_RECOVERY_PROMPT
                            if recovering
                            else ANDROIDWORLD_PLANNER_PROMPT
                        ),
                    },
                    {
                        "role": "user",
                        "content": [
                            {"type": "image_url", "image_url": {"url": _image_to_data_url(image)}},
                            {"type": "text", "text": "\n".join(context)},
                        ],
                    },
                ],
                extra_body={
                    "vl_high_resolution_images": True,
                    "enable_thinking": False,
                },
            )
            raw = completion.choices[0].message.content or ""
            plan = parse_androidworld_plan(
                raw,
                require_checklist=recovering,
                fallback_plan=current_plan,
            )
            return AndroidWorldPlanDecision(
                plan,
                self._metrics(time.perf_counter() - started, getattr(completion, "usage", None)),
                raw_output=raw,
            )
        except Exception as exc:
            return AndroidWorldPlanDecision(
                None,
                self._metrics(time.perf_counter() - started),
                f"Planner failed: {exc}",
                locals().get("raw", ""),
            )

    def verify_checkpoint_with_metrics(
        self,
        *,
        checkpoint: Checkpoint,
        claimed_evidence: str,
        image: Image.Image,
        screen: ScreenState,
        include_ui_tree: bool,
    ) -> AndroidWorldCheckpointDecision:
        if not self._api_key or not self._base_url:
            return AndroidWorldCheckpointDecision(
                "uncertain", "", self._metrics(0.0), "Verifier API credentials are not configured."
            )
        context = [
            f"Checkpoint: {checkpoint.goal}",
            f"Frozen evidence: {checkpoint.evidence.describe()}",
            f"Actor claim (untrusted): {claimed_evidence or 'none'}",
        ]
        if include_ui_tree:
            elements = [
                {
                    "text": item.text,
                    "description": item.content_description,
                    "resource_id": item.resource_id,
                }
                for item in screen.elements[:80]
            ]
            context.append("Accessibility evidence: " + json.dumps(elements, ensure_ascii=False))
        started = time.perf_counter()
        try:
            completion = self._make_client().chat.completions.create(
                model=self._model,
                messages=[
                    {"role": "system", "content": ANDROIDWORLD_CHECKPOINT_VERIFIER_PROMPT},
                    {
                        "role": "user",
                        "content": [
                            {"type": "image_url", "image_url": {"url": _image_to_data_url(image)}},
                            {"type": "text", "text": "\n".join(context)},
                        ],
                    },
                ],
                extra_body={
                    "vl_high_resolution_images": True,
                    "enable_thinking": False,
                },
            )
            raw = completion.choices[0].message.content or ""
            payload = json.loads(_extract_json(raw))
            decision = str(payload.get("decision", "")).strip().lower()
            evidence = str(payload.get("evidence", "")).strip()
            if decision not in {"confirmed", "not_confirmed", "uncertain"}:
                raise ValueError("invalid checkpoint verifier decision")
            return AndroidWorldCheckpointDecision(
                decision,
                evidence,
                self._metrics(time.perf_counter() - started, getattr(completion, "usage", None)),
                raw_output=raw,
            )
        except Exception as exc:
            return AndroidWorldCheckpointDecision(
                "uncertain",
                "",
                self._metrics(time.perf_counter() - started),
                f"Checkpoint Verifier failed: {exc}",
                locals().get("raw", ""),
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
    allow_v21_actions: bool = False,
    allow_v22_actions: bool = False,
) -> ParseResult:
    """Parse one strict JSON action and convert normalized clicks to pixels."""
    try:
        try:
            payload = _unwrap_mobile_action_payload(
                json.loads(_extract_json(raw_output))
            )
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
        if (
            allow_v22_actions
            and kind == "SWIPE"
            and payload.get("start_coordinate") is not None
            and payload.get("end_coordinate") is not None
            and not _normalize_swipe_direction(payload.get("direction"))
        ):
            # GUI-Plus sometimes names an explicit point-to-point gesture
            # "swipe". Preserve its exact start/end/duration semantics through
            # the V2.2 DRAG contract instead of guessing a coarse direction.
            kind = "DRAG"
        reason = str(payload.get("reason", ""))
        subgoal = str(payload.get("subgoal", "")).strip()
        expected_outcome = str(payload.get("expected_outcome", ""))
        completion_evidence = _parse_completion_evidence(
            payload.get("completion_evidence"),
            enabled=allow_v22_actions,
        )
        if kind == "CLICK":
            point, coordinate_space = _parse_action_point(
                payload.get("coordinate"), image_size, action_name="CLICK"
            )
            action = Action(
                ActionType.CLICK_POINT,
                _with_subgoal(
                    {"point": point, "coordinate_space": coordinate_space},
                    subgoal,
                    completion_evidence,
                ),
                reason,
                expected_outcome,
                source="androidworld_gui_plus",
            )
        elif kind == "LONG_PRESS" and allow_v22_actions:
            point, coordinate_space = _parse_action_point(
                payload.get("coordinate"), image_size, action_name="LONG_PRESS"
            )
            action = Action(
                ActionType.LONG_PRESS,
                _with_subgoal(
                    {"point": point, "coordinate_space": coordinate_space},
                    subgoal,
                    completion_evidence,
                ),
                reason,
                expected_outcome,
                source="androidworld_gui_plus",
            )
        elif kind == "DRAG" and allow_v22_actions:
            start, start_space = _parse_action_point(
                payload.get("start_coordinate"), image_size, action_name="DRAG start"
            )
            end, end_space = _parse_action_point(
                payload.get("end_coordinate"), image_size, action_name="DRAG end"
            )
            if start == end:
                raise ValueError("DRAG start and end coordinates must differ")
            duration_ms = payload.get("duration_ms", 500)
            if isinstance(duration_ms, bool) or not isinstance(duration_ms, (int, float)):
                raise ValueError("DRAG duration_ms must be numeric")
            duration_ms = round(duration_ms)
            if not 100 <= duration_ms <= 3000:
                raise ValueError("DRAG duration_ms must be between 100 and 3000")
            action = Action(
                ActionType.DRAG,
                _with_subgoal(
                    {
                        "start_point": start,
                        "end_point": end,
                        "duration_ms": duration_ms,
                        "coordinate_space": f"{start_space}->{end_space}",
                    },
                    subgoal,
                    completion_evidence,
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
                _with_subgoal({"text": text}, subgoal, completion_evidence),
                reason,
                expected_outcome,
                source="androidworld_gui_plus",
            )
        elif kind == "ANSWER" and allow_v22_actions:
            text = payload.get("text")
            if not isinstance(text, str) or not text.strip():
                raise ValueError("ANSWER requires non-empty text")
            action = Action(
                ActionType.ANSWER,
                _with_subgoal(
                    {"text": text.strip()}, subgoal, completion_evidence
                ),
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
                _with_subgoal({"direction": direction}, subgoal, completion_evidence),
                reason,
                expected_outcome,
                source="androidworld_gui_plus",
            )
        elif kind in {"BACK", "PRESS_BACK", "WAIT", "PROPOSE_COMPLETE"}:
            action = Action(
                ActionType("PRESS_BACK" if kind in {"BACK", "PRESS_BACK"} else kind),
                _with_subgoal({}, subgoal, completion_evidence),
                reason=reason,
                expected_outcome=expected_outcome,
                source="androidworld_gui_plus",
            )
        elif kind == "PROPOSE_CHECKPOINT_COMPLETE" and allow_v21_actions:
            action = Action(
                ActionType.PROPOSE_CHECKPOINT_COMPLETE,
                {"observed_evidence": str(payload.get("observed_evidence", "")).strip()},
                reason=reason,
                source="androidworld_gui_plus",
            )
        elif kind == "PROPOSE_SUBGOAL_COMPLETE" and allow_v22_actions:
            action = Action(
                ActionType.PROPOSE_SUBGOAL_COMPLETE,
                {"observed_evidence": str(payload.get("observed_evidence", "")).strip()},
                reason=reason,
                source="androidworld_gui_plus",
            )
        elif kind == "OPEN_APP":
            app_name = payload.get("app_name")
            if not isinstance(app_name, str) or not app_name:
                raise ValueError("OPEN_APP requires app_name")
            action = Action(
                ActionType.OPEN_APP,
                _with_subgoal({"app_name": app_name}, subgoal, completion_evidence),
                reason,
                expected_outcome,
                source="androidworld_gui_plus",
            )
        elif kind == "REQUEST_UI_TREE":
            action = Action(
                ActionType.CALL_TOOL,
                _with_subgoal({"tool": "ui_tree"}, subgoal, completion_evidence),
                reason,
                expected_outcome,
                source="androidworld_gui_plus",
            )
        elif kind in {"LONG_PRESS", "DRAG", "ANSWER"}:
            raise ValueError(f"unsupported action capability {kind}")
        else:
            raise ValueError(f"unknown action {kind}")
    except (KeyError, TypeError, ValueError, json.JSONDecodeError) as exc:
        if not (raw_output or "").strip():
            error_kind = ErrorKind.EMPTY_OUTPUT
        elif "unsupported action capability" in str(exc):
            error_kind = ErrorKind.UNSUPPORTED_ACTION_CAPABILITY
        elif "unknown action" in str(exc):
            error_kind = ErrorKind.UNKNOWN_ACTION
        else:
            error_kind = ErrorKind.PARSE_ERROR
        return ParseResult(
            error_kind=error_kind,
            message=f"Invalid AndroidWorld Actor output: {exc}",
            raw_output=raw_output,
        )
    tree_reference = payload.get("ui_tree_reference")
    if isinstance(tree_reference, str) and tree_reference.strip():
        action.parameters["ui_tree_reference"] = tree_reference.strip()
    return ParseResult(action=action, raw_output=raw_output)


def _parse_action_point(
    coordinate: Any,
    image_size: tuple[int, int],
    *,
    action_name: str,
) -> tuple[list[int], str]:
    if not isinstance(coordinate, list) or len(coordinate) != 2:
        raise ValueError(f"{action_name} coordinate must be a two-item list")
    x, y = coordinate
    if (
        isinstance(x, bool)
        or isinstance(y, bool)
        or not isinstance(x, (int, float))
        or not isinstance(y, (int, float))
    ):
        raise ValueError(f"{action_name} coordinate values must be numeric")
    width, height = image_size
    if 0 <= x <= 1000 and 0 <= y <= 1000:
        return [
            round(x * (width - 1) / 1000),
            round(y * (height - 1) / 1000),
        ], "normalized_1000"
    if 0 <= x < width and 0 <= y < height:
        return [round(x), round(y)], "image_pixels"
    raise ValueError(
        f"{action_name} coordinate is neither normalized [0, 1000] nor inside the image"
    )


def _context_text(request: AndroidWorldActorRequest) -> str:
    task = request.task
    lines = [
        f"Task goal: {task.goal}",
        f"Step: {task.step_index}; remaining steps: {task.remaining_steps}",
        f"Completed actions: {list(task.completed_action_summaries[-5:])}",
        f"Last verifier result: {task.last_verifier_result or 'none'}",
        f"Recent failure: {task.recent_failure or 'none'}",
    ]
    if task.runtime_version in {"v2", "v2.1", "v2.2"}:
        lines.extend(
            [
                f"Current subgoal: {task.current_subgoal or 'choose the next safe subgoal'}",
                f"Current blocker: {task.current_blocker or 'none'}",
                f"Next verification: {task.next_verification or 'verify the visible result of the next action'}",
                f"Recovery instruction: {task.recovery_reason or 'none'}",
                f"Protocol correction: {task.protocol_feedback or 'none'}",
            ]
        )
    if task.runtime_version == "v2.1":
        lines.extend(
            [
                f"Plan mode: {task.plan_mode}",
                f"Confirmed checkpoints: {list(task.completed_checkpoints)}",
                f"Active checkpoint: {task.active_checkpoint or 'none; execute the task directly'}",
                f"Frozen completion evidence: {task.active_checkpoint_evidence or 'none'}",
                f"Remaining checkpoints: {list(task.remaining_checkpoints)}",
                f"Recovery level: {task.recovery_level or 'none'}",
            ]
        )
    if task.runtime_version == "v2.2":
        lines.extend(
            [
                f"Frozen active subgoal: {task.active_subgoal or 'none; follow the whole task safely'}",
                f"Frozen completion evidence: {task.active_subgoal_evidence or 'none'}",
                f"Completed subgoals: {list(task.completed_subgoals)}",
                f"Subgoal revision allowed by Recovery: {task.subgoal_revision_allowed}",
                f"Progress Verifier mode: {task.progress_verifier_mode}",
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


def _unwrap_mobile_action_payload(payload: Any) -> dict[str, Any]:
    """Accept the V2.2 tool envelope while preserving legacy bare JSON.

    The wrapper contains no planning semantics: it only names the one Actor
    tool and carries the same action arguments the strict parser validates.
    """
    if not isinstance(payload, dict):
        raise ValueError("response JSON must be an object")
    if "action" in payload:
        return payload
    if str(payload.get("name", "")).strip() != "mobile_action":
        raise ValueError("tool call must target mobile_action")
    arguments = payload.get("arguments")
    if not isinstance(arguments, dict):
        raise ValueError("mobile_action arguments must be an object")
    return arguments


def parse_androidworld_plan(
    raw_output: str,
    *,
    require_checklist: bool = False,
    fallback_plan: PlanState | None = None,
) -> PlanState:
    payload = json.loads(_extract_json(raw_output))
    mode = str(payload.get("mode", "")).strip().lower()
    reason = str(payload.get("reason", "")).strip()
    rows = payload.get("checkpoints")
    if mode not in {"direct", "checklist"} or not isinstance(rows, list):
        raise ValueError("Planner must return direct or checklist mode with checkpoints")
    if mode == "direct":
        if not rows:
            if require_checklist:
                raise ValueError("plan-level recovery must return replacement checkpoints")
            return PlanState.direct(reason or "Planner selected direct execution")
        # GUI-Plus sometimes labels a structured plan as direct while still
        # supplying explicit checkpoints. The checkpoints are unambiguous and
        # safer to preserve than to discard as a full Planner failure.
        mode = "checklist"
    if not 1 <= len(rows) <= 6:
        raise ValueError("checklist mode requires 1 to 6 checkpoints")
    checkpoints: list[Checkpoint] = []
    for row in rows:
        if not isinstance(row, dict) or not isinstance(row.get("evidence"), dict):
            raise ValueError("each checkpoint requires a goal and evidence object")
        goal = str(row.get("goal", "")).strip()
        evidence_row = row["evidence"]
        kind = str(evidence_row.get("kind", "")).strip().lower()
        value = str(evidence_row.get("value", "")).strip()
        kind = {"ui_element": "visual", "screen": "visual"}.get(kind, kind)
        if kind == "package_activity" and any(character.isspace() for character in value):
            kind = "visual"
        if (not kind or not value) and fallback_plan is not None:
            previous = next(
                (
                    item
                    for item in fallback_plan.checkpoints
                    if item.status != "done" and item.goal.casefold() == goal.casefold()
                ),
                None,
            )
            if previous is not None:
                kind, value = previous.evidence.kind, previous.evidence.value
        if not goal or not value or kind not in {"ui_text", "ui_state", "package_activity", "visual"}:
            raise ValueError("checkpoint goal or evidence is invalid")
        checkpoints.append(Checkpoint(goal, CheckpointEvidence(kind, value)))
    plan = PlanState(mode="checklist", reason=reason, checkpoints=checkpoints)
    plan.activate_first()
    return plan


def _actor_prompt(task: AndroidWorldTaskState) -> str:
    if task.runtime_version == "v2.2":
        return ANDROIDWORLD_ACTOR_V22_TOOL_PROMPT
    if task.runtime_version == "v2.1":
        if task.plan_mode == "checklist" and task.active_checkpoint:
            return ANDROIDWORLD_ACTOR_V2_PROMPT + ANDROIDWORLD_ACTOR_V21_CHECKLIST_SUFFIX
        if task.plan_mode == "checklist" and task.completed_checkpoints:
            return ANDROIDWORLD_ACTOR_V2_PROMPT + ANDROIDWORLD_ACTOR_V21_ALL_CHECKPOINTS_DONE_SUFFIX
        return ANDROIDWORLD_ACTOR_V2_PROMPT
    if task.runtime_version == "v2":
        return ANDROIDWORLD_ACTOR_V2_PROMPT
    return ANDROIDWORLD_ACTOR_PROMPT


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


def _with_subgoal(
    parameters: dict[str, Any],
    subgoal: str,
    completion_evidence: tuple[str, str] | None = None,
) -> dict[str, Any]:
    if subgoal:
        parameters["subgoal"] = subgoal
    if completion_evidence is not None:
        parameters["completion_evidence_kind"] = completion_evidence[0]
        parameters["completion_evidence_value"] = completion_evidence[1]
    return parameters


def _parse_completion_evidence(
    payload: object,
    *,
    enabled: bool,
) -> tuple[str, str] | None:
    if payload is None or not enabled:
        return None
    if not isinstance(payload, dict):
        raise ValueError("completion_evidence must be an object")
    kind = str(payload.get("kind", "")).strip().lower()
    kind = {"visual": "visual_state", "ui_state": "visual_state"}.get(kind, kind)
    value = str(payload.get("value", "")).strip()
    if kind not in {"ui_text", "package_activity", "visual_state"} or not value:
        raise ValueError("completion_evidence requires ui_text, package_activity, or visual_state")
    return kind, value


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
