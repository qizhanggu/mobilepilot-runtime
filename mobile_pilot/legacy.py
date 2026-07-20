"""旧竞赛动作协议到 MobilePilot Runtime 协议的兼容层。"""

import re
from typing import Any, Dict

from mobile_pilot.core import Action, ActionType, ErrorKind, ParseResult


_LEGACY_ACTION_MAP = {
    "CLICK": ActionType.CLICK_POINT,
    "TYPE": ActionType.TYPE_TEXT,
    "SCROLL": ActionType.SCROLL,
    "OPEN": ActionType.OPEN_APP,
}


def adapt_legacy_output(action: str, parameters: Dict[str, Any], raw_output: str = "") -> ParseResult:
    """把旧 ``AgentOutput`` 的字段转换为新协议。

    旧 ``OutputParser`` 会把无法解析的自由文本兜底为 ``COMPLETE``。新运行时
    不能把这个兜底误判为成功，因此只接受原始文本中明确表达的 COMPLETE。
    """

    raw = raw_output or ""
    normalized = (action or "").upper()

    if raw.lstrip().startswith("Error:"):
        return ParseResult(
            error_kind=ErrorKind.MODEL_ERROR,
            message="旧 Agent 捕获到模型或基础设施异常。",
            raw_output=raw,
        )

    if not raw.strip():
        return ParseResult(
            error_kind=ErrorKind.EMPTY_OUTPUT,
            message="策略没有提供原始输出，不能推断任务成功。",
            raw_output=raw,
        )

    if normalized == "COMPLETE":
        if _is_explicit_legacy_complete(raw):
            return ParseResult(
                action=Action(
                    type=ActionType.PROPOSE_COMPLETE,
                    parameters={},
                    source="legacy_agent",
                ),
                raw_output=raw,
            )
        return ParseResult(
            error_kind=ErrorKind.PARSE_ERROR,
            message="旧解析器以 COMPLETE 兜底，但原始输出没有明确完成动作。",
            raw_output=raw,
        )

    action_type = _LEGACY_ACTION_MAP.get(normalized)
    if action_type is None:
        return ParseResult(
            error_kind=ErrorKind.UNKNOWN_ACTION,
            message=f"不支持的旧动作: {action!r}",
            raw_output=raw,
        )

    return ParseResult(
        action=Action(
            type=action_type,
            parameters=dict(parameters or {}),
            source="legacy_agent",
        ),
        raw_output=raw,
    )


def _is_explicit_legacy_complete(raw_output: str) -> bool:
    """判断 COMPLETE 是否由模型显式提出，而不是解析器的兜底。"""

    return bool(
        re.search(r"Action:\s*COMPLETE\s*\|\s*\{.*?\}", raw_output, re.IGNORECASE | re.DOTALL)
        or re.search(r"\bcomplete\s*\(.*?\)", raw_output, re.IGNORECASE | re.DOTALL)
    )
