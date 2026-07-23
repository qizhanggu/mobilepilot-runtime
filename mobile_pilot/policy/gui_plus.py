"""DashScope GUI-Plus 的最小视觉动作策略。

该模块只把截图和指令转换为候选动作，绝不直接控制设备。
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

from mobile_pilot.core import Action, ActionType, ErrorKind, ParseResult


GUI_PLUS_SYSTEM_PROMPT = """# Tools
You may call the computer_use function. The screen coordinate system is normalized to 1000 by 1000.
<tools>
{"type":"function","function":{"name":"computer_use","parameters":{"type":"object","properties":{"action":{"type":"string","enum":["left_click"]},"coordinate":{"type":"array","items":{"type":"integer"},"minItems":2,"maxItems":2}},"required":["action","coordinate"]}}}
</tools>

# Response format
Return exactly two parts: a short Action line, then one <tool_call> block containing JSON only.
Do not use an action other than left_click. Do not claim task completion.
"""


@dataclass(frozen=True)
class GuiPlusRequest:
    """一次视觉定位请求所需的最小输入。"""

    instruction: str
    image: Image.Image


@dataclass(frozen=True)
class VisionCallMetrics:
    """一次模型调用的可审计计量；费用是公开目录价估算，不代表实际账单。"""

    model: str
    latency_seconds: float
    prompt_tokens: int | None
    completion_tokens: int | None
    total_tokens: int | None
    estimated_list_cost_cny: float | None


@dataclass(frozen=True)
class GuiPlusDecision:
    result: ParseResult
    metrics: VisionCallMetrics


class GuiPlusVisionPolicy:
    """通过 DashScope OpenAI-compatible API 调用 GUI-Plus。

    输出点位仍是旧协议的 ``[0, 1000]`` 归一化坐标，供 ``HybridGrounder``
    转为真实截图像素；设备点击必须由 Runtime 的安全层单独执行。
    """

    def __init__(
        self,
        *,
        api_key: str | None = None,
        base_url: str | None = None,
        model: str | None = None,
        request_timeout_seconds: float | None = None,
        client_factory: Callable[..., Any] | None = None,
    ):
        self._api_key = api_key or os.getenv("DASHSCOPE_API_KEY")
        self._base_url = base_url or os.getenv("DASHSCOPE_BASE_URL")
        self._model = model or os.getenv("MOBILEPILOT_ACTOR_MODEL", "gui-plus-2026-02-26")
        self._request_timeout_seconds = request_timeout_seconds or float(
            os.getenv("MOBILEPILOT_API_TIMEOUT_SECONDS", "90")
        )
        self._client_factory = client_factory

    def decide(self, request: GuiPlusRequest) -> ParseResult:
        return self.decide_with_metrics(request).result

    def decide_with_metrics(self, request: GuiPlusRequest) -> GuiPlusDecision:
        if not self._api_key:
            return self._failed_decision("DASHSCOPE_API_KEY is not configured.")
        if not self._base_url:
            return self._failed_decision("DASHSCOPE_BASE_URL is not configured.")
        if not request.instruction.strip():
            return self._failed_decision("Vision instruction is empty.", ErrorKind.PARSE_ERROR)

        started = time.perf_counter()
        try:
            client = self._make_client()
            completion = client.chat.completions.create(
                model=self._model,
                messages=[
                    {"role": "system", "content": GUI_PLUS_SYSTEM_PROMPT},
                    {
                        "role": "user",
                        "content": [
                            {"type": "image_url", "image_url": {"url": _image_to_data_url(request.image)}},
                            {"type": "text", "text": request.instruction},
                        ],
                    },
                ],
                extra_body={"vl_high_resolution_images": True},
            )
            raw_output = completion.choices[0].message.content or ""
        except Exception as exc:
            return GuiPlusDecision(
                ParseResult(error_kind=ErrorKind.MODEL_ERROR, message=f"GUI-Plus request failed: {exc}"),
                self._metrics(time.perf_counter() - started),
            )

        usage = getattr(completion, "usage", None)
        return GuiPlusDecision(
            parse_gui_plus_output(raw_output),
            self._metrics(time.perf_counter() - started, usage),
        )

    def _failed_decision(
        self,
        message: str,
        error_kind: ErrorKind = ErrorKind.MODEL_ERROR,
    ) -> GuiPlusDecision:
        return GuiPlusDecision(ParseResult(error_kind=error_kind, message=message), self._metrics(0.0))

    def _metrics(self, latency_seconds: float, usage: Any = None) -> VisionCallMetrics:
        prompt = _usage_int(usage, "prompt_tokens")
        completion = _usage_int(usage, "completion_tokens")
        total = _usage_int(usage, "total_tokens")
        cost = None
        if prompt is not None and completion is not None:
            cost = prompt * 1.5 / 1_000_000 + completion * 4.5 / 1_000_000
        return VisionCallMetrics(
            model=self._model,
            latency_seconds=latency_seconds,
            prompt_tokens=prompt,
            completion_tokens=completion,
            total_tokens=total,
            estimated_list_cost_cny=cost,
        )

    def _make_client(self) -> Any:
        if self._client_factory is not None:
            return self._client_factory(api_key=self._api_key, base_url=self._base_url)
        from openai import OpenAI

        # Benchmark 需要真实调用次数可审计，因此禁用 SDK 隐式重试；失败由上层显式记录。
        return OpenAI(
            api_key=self._api_key,
            base_url=self._base_url,
            timeout=self._request_timeout_seconds,
            max_retries=0,
        )


def parse_gui_plus_output(raw_output: str) -> ParseResult:
    """只接受 GUI-Plus 的 ``computer_use.left_click`` 候选动作。"""

    marker = "<tool_call>"
    marker_start = (raw_output or "").find(marker)
    if marker_start < 0:
        shorthand = re.fullmatch(
            r"\s*left_click\s*\n\s*\{?\s*\"coordinate\"\s*:\s*\[\s*(-?\d+(?:\.\d+)?)\s*,\s*(-?\d+(?:\.\d+)?)\s*\]\s*\}?\s*",
            raw_output or "",
        )
        if shorthand:
            point = [float(shorthand.group(1)), float(shorthand.group(2))]
            try:
                _validate_normalized_point(point)
            except ValueError as exc:
                return ParseResult(error_kind=ErrorKind.PARSE_ERROR, message=f"Invalid GUI-Plus action: {exc}", raw_output=raw_output)
            return ParseResult(
                action=Action(
                    type=ActionType.CLICK_POINT,
                    parameters={"point": [int(point[0]), int(point[1])]},
                    source="gui_plus",
                ),
                raw_output=raw_output,
            )
        return ParseResult(
            error_kind=ErrorKind.PARSE_ERROR,
            message="GUI-Plus response did not contain a tool_call JSON block.",
            raw_output=raw_output,
        )
    try:
        payload = raw_output[marker_start + len(marker):]
        closing_start = payload.find("</tool_call>")
        if closing_start >= 0:
            payload = payload[:closing_start]
        payload = payload.strip()
        call, end = json.JSONDecoder().raw_decode(payload)
        trailing = payload[end:].strip()
        if re.fullmatch(r"}?\s*(?:</think>|<tool_call>)?", trailing) is None:
            raise ValueError("tool_call contains unexpected trailing content")
        arguments = call.get("arguments", call.get("parameters", call))
        if call.get("name", "computer_use") != "computer_use" or arguments["action"] != "left_click":
            raise ValueError("only computer_use.left_click is allowed in this policy")
        point = arguments["coordinate"]
        _validate_normalized_point(point)
    except (KeyError, TypeError, ValueError, json.JSONDecodeError) as exc:
        return ParseResult(
            error_kind=ErrorKind.PARSE_ERROR,
            message=f"Invalid GUI-Plus action: {exc}",
            raw_output=raw_output,
        )

    return ParseResult(
        action=Action(
            type=ActionType.CLICK_POINT,
            parameters={"point": [int(point[0]), int(point[1])]},
            source="gui_plus",
        ),
        raw_output=raw_output,
    )


def _validate_normalized_point(value: object) -> None:
    if not isinstance(value, list) or len(value) != 2:
        raise ValueError("coordinate must be a two-item list")
    x, y = value
    if isinstance(x, bool) or isinstance(y, bool) or not isinstance(x, (int, float)) or not isinstance(y, (int, float)):
        raise ValueError("coordinate values must be numeric")
    if not (0 <= x <= 1000 and 0 <= y <= 1000):
        raise ValueError("coordinate must be within [0, 1000]")


def _image_to_data_url(image: Image.Image) -> str:
    buffer = io.BytesIO()
    image.save(buffer, format="PNG")
    encoded = base64.b64encode(buffer.getvalue()).decode("ascii")
    return f"data:image/png;base64,{encoded}"


def _usage_int(usage: Any, key: str) -> int | None:
    if usage is None:
        return None
    value = getattr(usage, key, None)
    if value is None and isinstance(usage, dict):
        value = usage.get(key)
    return int(value) if value is not None else None
