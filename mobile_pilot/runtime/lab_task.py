"""MobilePilot Lab 的受控自然语言纵向闭环。"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
import re

from mobile_pilot.device import DeviceAdapter
from mobile_pilot.perception import ScreenState
from mobile_pilot.policy import Grounder, SemanticTarget
from mobile_pilot.tracing import JsonlTraceWriter

from .critic import PreActionCritic
from .verifier import ScreenVerifier


class LabStepKind(str, Enum):
    CLICK = "CLICK"
    TYPE = "TYPE"


@dataclass(frozen=True)
class LabTaskStep:
    name: str
    kind: LabStepKind
    target_resource_id: str = ""
    text: str = ""
    expected_text: str = ""


@dataclass(frozen=True)
class LabTaskResult:
    success: bool
    completed_steps: int
    total_steps: int
    reason: str


def compile_lab_search_task(instruction: str) -> tuple[LabTaskStep, ...]:
    """把受控自然语言基准编译成可验证步骤，不接受隐式提交。"""

    match = re.search(r"搜索\s*([A-Za-z0-9_-]+)", instruction)
    if match is None:
        raise ValueError("Controlled Lab task currently requires an ASCII search keyword.")
    if "筛选" not in instruction or "确认页" not in instruction:
        raise ValueError("Controlled Lab task must request filtering and the confirmation page.")
    if "不要提交" not in instruction and "不提交" not in instruction:
        raise ValueError("Controlled Lab task must explicitly stop before submission.")

    keyword = match.group(1)
    package = "com.mobilepilot.lab"
    return (
        LabTaskStep("focus_search", LabStepKind.CLICK, f"{package}:id/search_input"),
        LabTaskStep("type_keyword", LabStepKind.TYPE, text=keyword, expected_text=keyword),
        LabTaskStep("run_search", LabStepKind.CLICK, f"{package}:id/search_button", expected_text="筛选评分 4.5 以上"),
        LabTaskStep("apply_filter", LabStepKind.CLICK, f"{package}:id/filter_button", expected_text="当前筛选：评分 4.5 以上"),
        LabTaskStep("open_confirmation", LabStepKind.CLICK, f"{package}:id/review_order_button", expected_text="订单确认页（测试）"),
    )


class LabTaskRuntime:
    """执行受控计划，每步重新观察、审查、执行并验证。"""

    def __init__(self, adapter: DeviceAdapter, trace: JsonlTraceWriter):
        self._adapter = adapter
        self._trace = trace
        self._grounder = Grounder()
        self._critic = PreActionCritic()
        self._verifier = ScreenVerifier()

    def run(self, instruction: str) -> LabTaskResult:
        steps = compile_lab_search_task(instruction)
        info = self._adapter.get_device_info()
        self._trace.write(
            "task_started",
            instruction=instruction,
            serial=info.serial,
            activity=info.current_activity,
            total_steps=len(steps),
        )

        completed = 0
        for index, step in enumerate(steps, start=1):
            self._trace.write("step_planned", index=index, name=step.name, kind=step.kind.value)
            state = ScreenState.from_observation(self._adapter.observe(include_ui_tree=True))
            self._trace.write(
                "observation",
                index=index,
                activity=state.package_activity,
                fingerprint=state.fingerprint,
                element_count=len(state.elements),
            )

            if step.kind is LabStepKind.CLICK:
                candidate = self._grounder.resolve(
                    SemanticTarget(resource_id=step.target_resource_id),
                    state,
                )
                decision = self._critic.review(candidate, state)
                self._trace.write(
                    "critic",
                    index=index,
                    allowed=decision.allowed,
                    reason=decision.reason,
                    point=candidate.point,
                    grounding_source=candidate.source.value,
                )
                if not decision.allowed:
                    return self._finish(False, completed, steps, decision.reason)
                action_result = self._adapter.tap_point(*candidate.point)
            else:
                action_result = self._adapter.type_text(step.text)

            self._trace.write(
                "action",
                index=index,
                executed=action_result.executed,
                action_type=action_result.action.type.value,
                parameters=action_result.action.parameters,
            )
            if not action_result.executed:
                return self._finish(False, completed, steps, action_result.message)

            if step.expected_text:
                verification = self._verifier.wait_for_text(self._adapter, step.expected_text)
                self._trace.write(
                    "verification",
                    index=index,
                    success=verification.success,
                    attempts=verification.attempts,
                    reason=verification.reason,
                    fingerprint=verification.state.fingerprint,
                )
                if not verification.success:
                    return self._finish(False, completed, steps, verification.reason)

            completed += 1
            self._trace.write("step_completed", index=index, name=step.name)

        return self._finish(True, completed, steps, "Reached confirmation page and stopped before submit.")

    def _finish(
        self,
        success: bool,
        completed: int,
        steps: tuple[LabTaskStep, ...],
        reason: str,
    ) -> LabTaskResult:
        self._trace.write(
            "task_finished",
            success=success,
            completed_steps=completed,
            total_steps=len(steps),
            reason=reason,
        )
        return LabTaskResult(success, completed, len(steps), reason)
