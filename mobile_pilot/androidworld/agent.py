"""AndroidWorld ``EnvironmentInteractingAgent`` powered by MobilePilot."""

from __future__ import annotations

from dataclasses import asdict
from pathlib import Path
from typing import Any

from mobile_pilot.androidworld.actor import AndroidWorldActorRequest, AndroidWorldGuiPlusPolicy
from mobile_pilot.androidworld.adapter import AndroidWorldAdapter, AndroidWorldTaskState
from mobile_pilot.core import Action, ActionType
from mobile_pilot.tracing import JsonlTraceWriter

try:  # Keep the normal MobilePilot test environment free of AndroidWorld.
    from android_world.agents.base_agent import AgentInteractionResult, EnvironmentInteractingAgent
except ImportError:  # pragma: no cover - exercised only without AndroidWorld installed
    class EnvironmentInteractingAgent:  # type: ignore[no-redef]
        def __init__(self, env: Any, name: str = "", transition_pause: float | None = None) -> None:
            self._env, self._name, self._max_steps = env, name, None

        def set_max_steps(self, max_steps: int) -> None:
            self._max_steps = max_steps

    class AgentInteractionResult:  # type: ignore[no-redef]
        def __init__(self, done: bool, data: dict[str, Any]) -> None:
            self.done, self.data = done, data


class MobilePilotAndroidWorldAgent(EnvironmentInteractingAgent):
    """One action per ``step``; only the benchmark task can award success."""

    def __init__(
        self,
        env: Any,
        *,
        mode: str,
        max_steps: int,
        policy: AndroidWorldGuiPlusPolicy | None = None,
        trace_path: str | Path,
    ) -> None:
        if mode not in {"vision_only", "hybrid"}:
            raise ValueError("mode must be vision_only or hybrid")
        super().__init__(env, name=f"MobilePilot[{mode}]", transition_pause=None)
        self.set_max_steps(max_steps)
        self._mode = mode
        self._adapter = AndroidWorldAdapter(env)
        self._policy = policy or AndroidWorldGuiPlusPolicy()
        self._trace = JsonlTraceWriter(trace_path)
        self._goal = ""
        self._step_index = 0
        self._history: list[str] = []
        self._last_verifier = ""
        self._recent_failure = ""

    def step(self, goal: str) -> AgentInteractionResult:
        if self._goal and self._goal != goal:
            self._step_index, self._history, self._last_verifier, self._recent_failure = 0, [], "", ""
        self._goal = goal
        if self._step_index >= self._max_steps:
            return self._finish("step_budget_exhausted")
        include_tree = self._mode == "hybrid"
        image, screen = self._adapter.observe(include_ui_tree=include_tree)
        task_state = AndroidWorldTaskState(
            goal=goal,
            step_index=self._step_index,
            remaining_steps=self._max_steps - self._step_index,
            completed_action_summaries=tuple(self._history),
            last_verifier_result=self._last_verifier,
            recent_failure=self._recent_failure,
        )
        self._trace.write("observation", step=self._step_index, mode=self._mode, screen_fingerprint=screen.fingerprint, image_size=screen.image_size, ui_element_count=len(screen.elements))
        decision = self._policy.decide_with_metrics(AndroidWorldActorRequest(task_state, image, screen, include_tree))
        self._trace.write("actor_decision", step=self._step_index, parsed=decision.result.is_success, error_kind=decision.result.error_kind.value if decision.result.error_kind else "", message=decision.result.message, raw_response=decision.result.raw_output, metrics=asdict(decision.metrics))
        if not decision.result.is_success:
            self._recent_failure = decision.result.message
            return self._finish("invalid_actor_output")

        action = decision.result.action
        assert action is not None
        blocked = _bounds_block(action, screen.image_size)
        self._trace.write("critic", step=self._step_index, allowed=not blocked, reason=blocked or "coordinate bounds check passed", action=action.type.value)
        if blocked:
            self._recent_failure = blocked
            return self._finish("critic_blocked")
        if action.type is ActionType.PROPOSE_COMPLETE:
            self._trace.write("completion_proposed", step=self._step_index, reason=action.reason)
            return self._finish("actor_proposed_complete")

        result = self._adapter.execute(action)
        self._history.append(_summary(action))
        self._step_index += 1
        self._trace.write("execution", step=self._step_index - 1, executed=result.executed, message=result.message, action=action.type.value, details=result.details)
        if not result.executed:
            self._recent_failure = result.message
            return self._finish("action_execution_failed")
        _, after = self._adapter.observe(include_ui_tree=include_tree)
        self._last_verifier = "screen_changed" if screen.fingerprint != after.fingerprint else "screen_unchanged"
        self._trace.write("verifier", step=self._step_index - 1, result=self._last_verifier, before_fingerprint=screen.fingerprint, after_fingerprint=after.fingerprint)
        if self._last_verifier == "screen_unchanged" and action.type is not ActionType.WAIT:
            wait = Action(ActionType.WAIT, source="generic_recovery")
            recovery = self._adapter.execute(wait)
            self._trace.write("recovery", step=self._step_index - 1, strategy="wait_after_unchanged_screen", executed=recovery.executed)
        return AgentInteractionResult(done=False, data={"step": self._step_index, "verifier": self._last_verifier})

    def _finish(self, reason: str) -> AgentInteractionResult:
        self._trace.write("agent_finished", step=self._step_index, reason=reason, mode=self._mode)
        return AgentInteractionResult(done=True, data={"reason": reason, "steps": self._step_index, "mode": self._mode})


def _bounds_block(action: Action, image_size: tuple[int, int]) -> str:
    if action.type is not ActionType.CLICK_POINT:
        return ""
    point = action.parameters.get("point", [])
    if not isinstance(point, list) or len(point) != 2:
        return "CLICK_POINT requires a valid point"
    x, y = point
    width, height = image_size
    if not isinstance(x, int) or not isinstance(y, int) or not (0 <= x < width and 0 <= y < height):
        return "candidate point is outside the current screenshot"
    return ""


def _summary(action: Action) -> str:
    if action.type is ActionType.TYPE_TEXT:
        return "TYPE[text omitted]"
    return action.type.value
