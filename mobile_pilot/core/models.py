"""新运行时的动作、结果和终止状态协议。

这里故意不依赖竞赛的 ``agent_base.py``。竞赛接口可能被替换；真实设备
运行时需要保持自己的稳定语义，并通过兼容层消费旧输出。
"""

from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Dict, Optional


class TaskStatus(str, Enum):
    """任务运行时的明确终止/等待状态。"""

    RUNNING = "RUNNING"
    SUCCEEDED = "SUCCEEDED"
    FAILED = "FAILED"
    NEED_USER = "NEED_USER"
    CANCELLED = "CANCELLED"
    TIMEOUT = "TIMEOUT"
    DEVICE_ERROR = "DEVICE_ERROR"
    MODEL_ERROR = "MODEL_ERROR"
    POLICY_BLOCKED = "POLICY_BLOCKED"


class ActionType(str, Enum):
    """新运行时支持的动作类型。

    ``PROPOSE_COMPLETE`` 只是策略对完成的提议，不能直接转换为
    ``TaskStatus.SUCCEEDED``；必须由后续 Verifier 检查成功条件。
    """

    CLICK_ELEMENT = "CLICK_ELEMENT"
    CLICK_POINT = "CLICK_POINT"
    LONG_PRESS = "LONG_PRESS"
    DRAG = "DRAG"
    ANSWER = "ANSWER"
    TYPE_TEXT = "TYPE_TEXT"
    CLEAR_TEXT = "CLEAR_TEXT"
    SCROLL = "SCROLL"
    SWIPE = "SWIPE"
    PRESS_BACK = "PRESS_BACK"
    PRESS_HOME = "PRESS_HOME"
    OPEN_APP = "OPEN_APP"
    CALL_INTENT = "CALL_INTENT"
    CALL_TOOL = "CALL_TOOL"
    WAIT = "WAIT"
    ASK_USER = "ASK_USER"
    REQUEST_TAKEOVER = "REQUEST_TAKEOVER"
    PROPOSE_CHECKPOINT_COMPLETE = "PROPOSE_CHECKPOINT_COMPLETE"
    PROPOSE_SUBGOAL_COMPLETE = "PROPOSE_SUBGOAL_COMPLETE"
    PROPOSE_COMPLETE = "PROPOSE_COMPLETE"
    ABORT = "ABORT"


class ErrorKind(str, Enum):
    """可审计的策略/协议错误分类。"""

    EMPTY_OUTPUT = "EMPTY_OUTPUT"
    PARSE_ERROR = "PARSE_ERROR"
    UNKNOWN_ACTION = "UNKNOWN_ACTION"
    UNSUPPORTED_ACTION_CAPABILITY = "UNSUPPORTED_ACTION_CAPABILITY"
    MODEL_ERROR = "MODEL_ERROR"


@dataclass(frozen=True)
class Action:
    """已解析但尚未执行的候选动作。"""

    type: ActionType
    parameters: Dict[str, Any] = field(default_factory=dict)
    reason: str = ""
    expected_outcome: str = ""
    source: str = ""


@dataclass(frozen=True)
class ParseResult:
    """策略输出进入 Runtime 前的解析结果。"""

    action: Optional[Action] = None
    error_kind: Optional[ErrorKind] = None
    message: str = ""
    raw_output: str = ""

    @property
    def is_success(self) -> bool:
        return self.action is not None and self.error_kind is None


@dataclass(frozen=True)
class ActionResult:
    """设备动作的结构化执行结果；Phase 1 的 Adapter 将使用它。"""

    executed: bool
    action: Action
    message: str = ""
    error_kind: Optional[ErrorKind] = None
    duration_ms: Optional[int] = None
    details: Dict[str, Any] = field(default_factory=dict)
