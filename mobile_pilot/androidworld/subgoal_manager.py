"""Low-frequency subgoal proposals for the AndroidWorld V2.2 runtime.

This module is intentionally smaller than a Planner.  It proposes only the
next verifiable objective and never chooses a click, coordinate, or action
sequence.  Runtime owns the proposal after accepting it.
"""

from __future__ import annotations

import base64
from dataclasses import dataclass
import io
import json
import os
import time
from typing import Any, Callable, Iterable

from PIL import Image

from mobile_pilot.androidworld.runtime_state import CompletionEvidence
from mobile_pilot.policy.gui_plus import VisionCallMetrics


SUBGOAL_MANAGER_PROMPT = """You are a constrained Android GUI Subgoal Manager, not an Actor and not a full Planner.
From the screenshot, whole task goal, and bounded Runtime state, propose exactly
one small next objective that helps the task and can be verified on a later
screen. Do not output a click, coordinate, phone action, or multi-step sequence.

Choose one completion evidence kind:
- package_activity: an exact package identifier explicitly present in Runtime context should be foreground; never invent a future package identifier from an app label;
- ui_text: one distinctive visible label or value should appear;
- visual_state: a specific visible page/state when deterministic evidence is insufficient.

Prefer deterministic evidence when it is reliable. Do not guess an Android
package name from a human app label; use ui_text or visual_state instead.
Evidence describes the state after the subgoal is complete, never the action
used to reach it. It must be a postcondition newly observable after progress,
not the label of the control to press. For example, if "Stopwatch" is already
visible as a tab, do not use that same text as evidence for entering the
Stopwatch page; use a page-specific timer control or a precise visual state.
Propose useful new progress, not a state already satisfied in the current
screenshot. If Runtime supplies rejected_evidence_feedback, replace that
evidence with a genuinely new postcondition. Do not claim that the whole task is complete. During
recovery, revise the current subgoal only when the supplied failure makes it
unsuitable.

Return exactly one JSON object:
{"subgoal":"one immediate objective","evidence":{"kind":"package_activity|ui_text|visual_state","value":"specific completion state"},"reason":"short alignment reason"}
"""


@dataclass(frozen=True)
class SubgoalManagerDecision:
    subgoal: str
    evidence: CompletionEvidence | None
    reason: str
    metrics: VisionCallMetrics
    message: str = ""
    raw_output: str = ""

    @property
    def is_success(self) -> bool:
        return bool(self.subgoal and self.evidence is not None)


class QwenSubgoalManager:
    """One-image, non-thinking Qwen subgoal proposer used at boundaries only."""

    def __init__(
        self,
        *,
        api_key: str | None = None,
        base_url: str | None = None,
        model: str | None = None,
        request_timeout_seconds: float | None = None,
        client_factory: Callable[..., Any] | None = None,
        input_price_per_million_cny: float | None = None,
        output_price_per_million_cny: float | None = None,
    ) -> None:
        self._api_key = (
            api_key
            or os.getenv("MOBILEPILOT_SUBGOAL_API_KEY")
            or os.getenv("MOBILEPILOT_VERIFIER_API_KEY")
            or os.getenv("DASHSCOPE_API_KEY")
        )
        self._base_url = (
            base_url
            or os.getenv("MOBILEPILOT_SUBGOAL_BASE_URL")
            or os.getenv("MOBILEPILOT_VERIFIER_BASE_URL")
            or os.getenv("DASHSCOPE_BASE_URL")
        )
        self._model = model or os.getenv(
            "MOBILEPILOT_SUBGOAL_MODEL", "qwen3.7-flash-2026-07-15"
        )
        self._timeout = request_timeout_seconds or float(
            os.getenv("MOBILEPILOT_API_TIMEOUT_SECONDS", "90")
        )
        self._client_factory = client_factory
        self._input_price = (
            input_price_per_million_cny
            if input_price_per_million_cny is not None
            else float(os.getenv("MOBILEPILOT_VERIFIER_INPUT_PRICE_CNY_PER_M", "0.2"))
        )
        self._output_price = (
            output_price_per_million_cny
            if output_price_per_million_cny is not None
            else float(os.getenv("MOBILEPILOT_VERIFIER_OUTPUT_PRICE_CNY_PER_M", "0.8"))
        )

    @property
    def model(self) -> str:
        return self._model

    def propose_with_metrics(
        self,
        *,
        image: Image.Image,
        task_goal: str,
        completed_subgoals: Iterable[str],
        trigger: str,
        current_subgoal: str = "",
        current_evidence: str = "",
        recovery_reason: str = "",
        package_activity: str = "",
        visible_ui_text: Iterable[str] = (),
        rejected_evidence_feedback: str = "",
    ) -> SubgoalManagerDecision:
        if not self._api_key or not self._base_url:
            return self._failed("Subgoal Manager API credentials are not configured.")
        context = {
            "whole_task_goal": task_goal,
            "trigger": trigger,
            "completed_subgoals": list(completed_subgoals)[-6:],
            "current_frozen_subgoal": current_subgoal,
            "current_frozen_evidence": current_evidence,
            "recovery_reason": recovery_reason,
            "package_activity": package_activity,
            "visible_ui_text": list(visible_ui_text)[:40],
            "rejected_evidence_feedback": rejected_evidence_feedback,
        }
        started = time.perf_counter()
        try:
            completion = self._make_client().chat.completions.create(
                model=self._model,
                messages=[
                    {"role": "system", "content": SUBGOAL_MANAGER_PROMPT},
                    {
                        "role": "user",
                        "content": [
                            {
                                "type": "image_url",
                                "image_url": {"url": _image_to_data_url(image)},
                            },
                            {
                                "type": "text",
                                "text": "Subgoal context JSON:\n"
                                + json.dumps(context, ensure_ascii=False, sort_keys=True),
                            },
                        ],
                    },
                ],
                response_format={"type": "json_object"},
                extra_body={"enable_thinking": False},
            )
            raw = completion.choices[0].message.content or ""
            payload = json.loads(raw)
            subgoal = str(payload.get("subgoal", "")).strip()
            evidence_row = payload.get("evidence")
            reason = str(payload.get("reason", "")).strip()
            if not subgoal or not isinstance(evidence_row, dict):
                raise ValueError("subgoal and evidence object are required")
            evidence = CompletionEvidence(
                str(evidence_row.get("kind", "")).strip().lower(),
                str(evidence_row.get("value", "")).strip(),
            )
            normalization_message = ""
            if evidence.kind == "package_activity" and not _package_is_grounded(
                evidence.value,
                package_activity,
            ):
                evidence = CompletionEvidence(
                    "visual_state",
                    f"the screen visibly shows this subgoal is complete: {subgoal}",
                )
                normalization_message = (
                    "Ungrounded package_activity evidence was downgraded to "
                    "visual_state; Runtime supplied no matching exact package identifier."
                )
            return SubgoalManagerDecision(
                subgoal,
                evidence,
                reason,
                self._metrics(
                    time.perf_counter() - started,
                    getattr(completion, "usage", None),
                ),
                message=normalization_message,
                raw_output=raw,
            )
        except Exception as exc:
            return self._failed(
                f"Subgoal Manager failed: {exc}",
                latency=time.perf_counter() - started,
                raw_output=locals().get("raw", ""),
            )

    def _make_client(self) -> Any:
        if self._client_factory:
            return self._client_factory(api_key=self._api_key, base_url=self._base_url)
        from openai import OpenAI

        return OpenAI(
            api_key=self._api_key,
            base_url=self._base_url,
            timeout=self._timeout,
            max_retries=0,
        )

    def _failed(
        self,
        message: str,
        *,
        latency: float = 0.0,
        raw_output: str = "",
    ) -> SubgoalManagerDecision:
        return SubgoalManagerDecision(
            "",
            None,
            "",
            self._metrics(latency),
            message=message,
            raw_output=raw_output,
        )

    def _metrics(self, latency: float, usage: Any = None) -> VisionCallMetrics:
        prompt = _usage_int(usage, "prompt_tokens")
        completion = _usage_int(usage, "completion_tokens")
        total = _usage_int(usage, "total_tokens")
        cost = None
        if prompt is not None and completion is not None:
            cost = (
                prompt * self._input_price / 1_000_000
                + completion * self._output_price / 1_000_000
            )
        return VisionCallMetrics(
            self._model,
            latency,
            prompt,
            completion,
            total,
            cost,
        )


def _image_to_data_url(image: Image.Image) -> str:
    buffer = io.BytesIO()
    image.save(buffer, format="PNG")
    return "data:image/png;base64," + base64.b64encode(buffer.getvalue()).decode("ascii")


def _usage_int(usage: Any, name: str) -> int | None:
    value = getattr(usage, name, None) if usage is not None else None
    if value is None and isinstance(usage, dict):
        value = usage.get(name)
    return int(value) if value is not None else None


def _package_is_grounded(proposed: str, runtime_package: str) -> bool:
    """Accept hard package evidence only when Runtime supplied that identifier."""
    value = proposed.strip().casefold()
    observed = runtime_package.strip().casefold()
    return bool(value and observed) and (value in observed or observed in value)
