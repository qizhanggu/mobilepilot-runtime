"""Event-triggered visual progress Verifier for AndroidWorld.

The Verifier is deliberately separate from the GUI Actor.  It compares two
observations and returns a bounded progress judgement; it never chooses a tap,
coordinate, or text entry action.
"""

from __future__ import annotations

import base64
from dataclasses import dataclass
import io
import json
import os
import time
from typing import Any, Callable

from PIL import Image

from mobile_pilot.policy.gui_plus import VisionCallMetrics


PROGRESS_VERDICTS = frozenset(
    {"progress", "completed", "stalled", "regressed", "uncertain"}
)
PROGRESS_DISPOSITIONS = frozenset(
    {"continue", "confirm_subgoal", "reobserve", "change_action", "recover"}
)

PROGRESS_VERIFIER_PROMPT = """You are a constrained Android GUI progress Verifier, not an Actor.
Compare the before screenshot, executed action, and after screenshot against
one frozen subgoal and its completion evidence. Use the whole task goal only
as read-only alignment context: the subgoal should make progress toward it.

Choose exactly one verdict:
- progress: visible movement toward the frozen subgoal, but not completed;
- completed: the after screenshot visibly satisfies the completion evidence;
- stalled: no meaningful movement toward the subgoal;
- regressed: the after screenshot moved away from the subgoal or into a wrong context;
- uncertain: the screenshots do not support a safe judgement.

Be conservative. Never infer completion from the Actor claim alone. Never
rewrite the whole task goal or frozen subgoal, and never replan. If the frozen
subgoal conflicts with the whole task goal, report regressed or uncertain with
visible evidence instead of confirming local completion. Never return
coordinates, taps, text, or a concrete phone action. The disposition is only
advice to Runtime.

Return exactly one JSON object:
{"verdict":"progress|completed|stalled|regressed|uncertain","evidence":"brief visible evidence","disposition":"continue|confirm_subgoal|reobserve|change_action|recover"}
"""


@dataclass(frozen=True)
class ProgressVerifierDecision:
    verdict: str
    evidence: str
    disposition: str
    metrics: VisionCallMetrics
    message: str = ""
    raw_output: str = ""


class QwenProgressVerifier:
    """Two-image Qwen Verifier with non-thinking structured output."""

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
            or os.getenv("MOBILEPILOT_VERIFIER_API_KEY")
            or os.getenv("DASHSCOPE_API_KEY")
        )
        self._base_url = (
            base_url
            or os.getenv("MOBILEPILOT_VERIFIER_BASE_URL")
            or os.getenv("DASHSCOPE_BASE_URL")
        )
        self._model = model or os.getenv(
            "MOBILEPILOT_VERIFIER_MODEL", "qwen3.7-flash-2026-07-15"
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

    def verify_with_metrics(
        self,
        *,
        before_image: Image.Image,
        after_image: Image.Image,
        action_summary: str,
        task_goal: str,
        subgoal: str,
        evidence_kind: str,
        evidence_value: str,
        trigger: str,
        deterministic_signals: dict[str, Any],
        actor_claim: str = "",
    ) -> ProgressVerifierDecision:
        if not self._api_key or not self._base_url:
            return self._failed("Verifier API credentials are not configured.")
        context = {
            "whole_task_goal": task_goal,
            "frozen_subgoal": subgoal,
            "completion_evidence": {"kind": evidence_kind, "value": evidence_value},
            "executed_action": action_summary,
            "trigger": trigger,
            "deterministic_signals": deterministic_signals,
            "actor_claim_untrusted": actor_claim,
        }
        started = time.perf_counter()
        try:
            completion = self._make_client().chat.completions.create(
                model=self._model,
                messages=[
                    {"role": "system", "content": PROGRESS_VERIFIER_PROMPT},
                    {
                        "role": "user",
                        "content": [
                            {"type": "text", "text": "Before screenshot:"},
                            {
                                "type": "image_url",
                                "image_url": {"url": _image_to_data_url(before_image)},
                            },
                            {"type": "text", "text": "After screenshot:"},
                            {
                                "type": "image_url",
                                "image_url": {"url": _image_to_data_url(after_image)},
                            },
                            {
                                "type": "text",
                                "text": "Verifier context JSON:\n"
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
            verdict = str(payload.get("verdict", "")).strip().lower()
            evidence = str(payload.get("evidence", "")).strip()
            disposition = str(payload.get("disposition", "")).strip().lower()
            if verdict not in PROGRESS_VERDICTS:
                raise ValueError("invalid progress verdict")
            if disposition not in PROGRESS_DISPOSITIONS:
                raise ValueError("invalid progress disposition")
            if verdict == "completed" and disposition != "confirm_subgoal":
                raise ValueError("completed verdict must confirm_subgoal")
            if verdict != "completed" and disposition == "confirm_subgoal":
                raise ValueError("only completed verdict may confirm_subgoal")
            return ProgressVerifierDecision(
                verdict=verdict,
                evidence=evidence,
                disposition=disposition,
                metrics=self._metrics(
                    time.perf_counter() - started,
                    getattr(completion, "usage", None),
                ),
                raw_output=raw,
            )
        except Exception as exc:
            return self._failed(
                f"Progress Verifier failed: {exc}",
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
    ) -> ProgressVerifierDecision:
        return ProgressVerifierDecision(
            verdict="uncertain",
            evidence="",
            disposition="reobserve",
            metrics=self._metrics(latency),
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
