"""AndroidWorld ``EnvironmentInteractingAgent`` powered by MobilePilot."""

from __future__ import annotations

from dataclasses import asdict
from pathlib import Path
from typing import Any

from mobile_pilot.androidworld.actor import (
    AndroidWorldActorDecision,
    AndroidWorldActorRequest,
    AndroidWorldGuiPlusPolicy,
    parse_androidworld_actor_output,
)
from mobile_pilot.androidworld.adapter import AndroidWorldAdapter, AndroidWorldTaskState
from mobile_pilot.androidworld.runtime_state import (
    RecoveryController,
    RuntimeProgress,
    action_signature,
    actions_are_similar,
)
from mobile_pilot.core import Action, ActionType, ErrorKind
from mobile_pilot.perception import ScreenState
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
        runtime_version: str = "v2",
    ) -> None:
        if mode not in {"vision_only", "hybrid"}:
            raise ValueError("mode must be vision_only or hybrid")
        if runtime_version not in {"v1", "v2"}:
            raise ValueError("runtime_version must be v1 or v2")
        super().__init__(
            env,
            name=f"MobilePilot[{runtime_version}:{mode}]",
            transition_pause=None,
        )
        self.set_max_steps(max_steps)
        self._mode = mode
        self._runtime_version = runtime_version
        self._adapter = AndroidWorldAdapter(env)
        self._policy = policy or AndroidWorldGuiPlusPolicy()
        self._trace = JsonlTraceWriter(trace_path)
        self._goal = ""
        self._reset_runtime_state()

    def _reset_runtime_state(self) -> None:
        self._step_index = 0
        self._history: list[str] = []
        self._last_verifier = ""
        self._recent_failure = ""
        self._protocol_retry_used = False
        self._model_tree_request_used = False
        self._pending_tree_reason = ""
        self._progress = RuntimeProgress()
        self._recovery = RecoveryController()
        self._tree_use_counter = 0
        self._open_tree_uses: list[dict[str, Any]] = []

    def step(self, goal: str) -> AgentInteractionResult:
        if self._goal and self._goal != goal:
            self._reset_runtime_state()
        self._goal = goal
        if self._step_index >= self._max_steps:
            return self._finish("step_budget_exhausted")

        include_tree, tree_reason = self._tree_plan()
        image, screen, tree_use = self._observe(include_tree, tree_reason, phase="decision")
        self._progress.remember_screen(screen.fingerprint)
        decision = self._decide(image, screen, include_tree, phase="primary")

        if (
            self._runtime_version == "v2"
            and decision.result.is_success
            and decision.result.action is not None
            and decision.result.action.type is ActionType.CALL_TOOL
        ):
            tool_result = self._handle_ui_tree_request(image, screen, include_tree)
            if isinstance(tool_result, AgentInteractionResult):
                return tool_result
            image, screen, decision, tree_use = tool_result

        if not decision.result.is_success and self._runtime_version == "v2":
            guarded = self._protocol_guard_retry(decision, screen)
            if guarded is not None:
                image, screen, decision, tree_use = guarded

        if not decision.result.is_success:
            self._recent_failure = decision.result.message
            return self._finish("invalid_actor_output")

        action = decision.result.action
        assert action is not None
        if action.type is ActionType.CALL_TOOL:
            self._recent_failure = (
                "Actor requested UI Tree after the on-demand tool opportunity was exhausted."
            )
            return self._finish("invalid_ui_tree_request")
        if tree_use is not None:
            self._record_tree_decision(tree_use, action)

        if self._runtime_version == "v2":
            recovery_change = self._recovery.review_replan(action)
            if recovery_change is not None:
                episode = self._recovery.active
                assert episode is not None
                if not recovery_change:
                    self._trace.write(
                        "agent_recovery_replan",
                        step=self._step_index,
                        recovery_id=episode.recovery_id,
                        changed_action=False,
                        candidate_action=action_signature(action),
                        reason="replan repeated the blocked or uncertain action",
                    )
                    return self._finish("unsafe_repeated_action_after_recovery")
                self._trace.write(
                    "agent_recovery_replan",
                    step=self._step_index,
                    recovery_id=episode.recovery_id,
                    changed_action=True,
                    candidate_action=action_signature(action),
                    reason="replan selected a different action",
                )
            else:
                repeated = self._progress.candidate_loop_signal(action)
                if repeated:
                    self._trace.write(
                        "loop_detected",
                        step=self._step_index,
                        signal=repeated,
                        candidate_action=action_signature(action),
                        recent_actions=self._progress.action_signatures[-4:],
                    )
                    if self._begin_recovery(repeated, blocked_action=action):
                        return AgentInteractionResult(
                            done=False,
                            data={
                                "reason": "agent_replan_requested",
                                "steps": self._step_index,
                                "trigger": repeated,
                                "runtime_version": self._runtime_version,
                            },
                        )
                    return self._finish("recovery_exhausted")

        blocked = _bounds_block(action, screen.image_size)
        self._trace.write(
            "critic",
            step=self._step_index,
            allowed=not blocked,
            reason=blocked or "coordinate bounds check passed",
            action=action.type.value,
            runtime_version=self._runtime_version,
        )
        if blocked:
            self._recent_failure = blocked
            if self._runtime_version == "v2" and self._begin_recovery(
                "critic_blocked",
                blocked_action=action,
            ):
                return AgentInteractionResult(
                    done=False,
                    data={
                        "reason": "agent_replan_requested",
                        "steps": self._step_index,
                        "trigger": "critic_blocked",
                        "runtime_version": self._runtime_version,
                    },
                )
            return self._finish("critic_blocked")
        if action.type is ActionType.PROPOSE_COMPLETE:
            self._trace.write("completion_proposed", step=self._step_index, reason=action.reason)
            return self._finish("actor_proposed_complete")

        result = self._adapter.execute(action)
        if self._runtime_version == "v1":
            self._history.append(_summary(action))
        else:
            self._progress.prepare_action(action)
        self._step_index += 1
        self._trace.write(
            "execution",
            step=self._step_index - 1,
            executed=result.executed,
            message=result.message,
            action=action.type.value,
            details=result.details,
            runtime_version=self._runtime_version,
        )
        if not result.executed:
            self._recent_failure = result.message
            self._progress.record_execution(action, executed=False, message=result.message)
            if self._runtime_version == "v2" and self._begin_recovery(
                "action_execution_failed",
                blocked_action=action,
            ):
                return AgentInteractionResult(
                    done=False,
                    data={
                        "reason": "agent_replan_requested",
                        "steps": self._step_index,
                        "trigger": "action_execution_failed",
                        "runtime_version": self._runtime_version,
                    },
                )
            return self._finish("action_execution_failed")

        if self._runtime_version == "v2":
            self._progress.record_execution(action, executed=True, message=result.message)
            self._recovery.mark_action_executed()
        _, after = self._adapter.observe(include_ui_tree=include_tree)
        self._last_verifier = "screen_changed" if screen.fingerprint != after.fingerprint else "screen_unchanged"
        self._trace.write(
            "verifier",
            step=self._step_index - 1,
            result=self._last_verifier,
            before_fingerprint=screen.fingerprint,
            after_fingerprint=after.fingerprint,
            next_verification=(
                self._progress.next_verification
                if self._runtime_version == "v2"
                else ""
            ),
            runtime_version=self._runtime_version,
        )

        if self._runtime_version == "v1" and self._last_verifier == "screen_unchanged" and action.type is not ActionType.WAIT:
            wait = Action(ActionType.WAIT, source="generic_recovery")
            recovery = self._adapter.execute(wait)
            self._trace.write("recovery", step=self._step_index - 1, strategy="wait_after_unchanged_screen", executed=recovery.executed)

        if self._runtime_version == "v2":
            self._progress.record_verification(
                changed=self._last_verifier == "screen_changed",
                action=action,
            )
            page_signal = self._progress.page_loop_signal(after.fingerprint)
            self._progress.remember_screen(after.fingerprint)
            self._trace.write(
                "progress_state",
                step=self._step_index,
                completed=list(self._progress.completed),
                current_subgoal=self._progress.current_subgoal,
                current_blocker=self._progress.current_blocker,
                next_verification=self._progress.next_verification,
            )
            if page_signal:
                self._trace.write(
                    "loop_detected",
                    step=self._step_index,
                    signal=page_signal,
                    screen_fingerprint=after.fingerprint,
                    unchanged_streak=self._progress.unchanged_streak,
                )
                if self._begin_recovery(page_signal, blocked_action=action):
                    return AgentInteractionResult(
                        done=False,
                        data={
                            "reason": "agent_replan_requested",
                            "steps": self._step_index,
                            "trigger": page_signal,
                            "runtime_version": self._runtime_version,
                        },
                    )
                return self._finish("recovery_exhausted")

        if self._step_index >= self._max_steps:
            return self._finish("step_budget_exhausted")
        return AgentInteractionResult(
            done=False,
            data={
                "step": self._step_index,
                "verifier": self._last_verifier,
                "runtime_version": self._runtime_version,
            },
        )

    def _finish(self, reason: str) -> AgentInteractionResult:
        self._trace.write(
            "agent_finished",
            step=self._step_index,
            reason=reason,
            mode=self._mode,
            runtime_version=self._runtime_version,
        )
        return AgentInteractionResult(
            done=True,
            data={
                "reason": reason,
                "steps": self._step_index,
                "mode": self._mode,
                "runtime_version": self._runtime_version,
            },
        )

    def reject_completion_proposal(self, reason: str) -> None:
        """Let the authoritative benchmark reject a premature model completion."""
        self._recent_failure = reason
        self._last_verifier = "official_completion_rejected"
        if getattr(self, "_runtime_version", "v1") == "v2":
            self._progress.recent_failure = reason
            self._progress.current_blocker = "official_completion_rejected"
            self._progress.last_verifier = "official_completion_rejected"
        self._trace.write(
            "official_completion_rejected",
            step=self._step_index,
            reason=reason,
            mode=self._mode,
            runtime_version=getattr(self, "_runtime_version", "v1"),
        )

    def record_official_reward(self, reward: float, *, terminal: bool) -> None:
        """Attach the authoritative benchmark outcome to recovery/tool events."""
        self._trace.write(
            "official_reward",
            step=self._step_index,
            reward=reward,
            terminal=terminal,
            runtime_version=self._runtime_version,
        )
        recovery_outcome = self._recovery.outcome(reward=reward, terminal=terminal)
        if recovery_outcome is not None:
            self._trace.write(
                "agent_recovery_outcome",
                step=self._step_index,
                **recovery_outcome,
            )
        if reward > 0 or terminal:
            for tree_use in self._open_tree_uses:
                self._trace.write(
                    "ui_tree_outcome",
                    step=self._step_index,
                    tree_use_id=tree_use["tree_use_id"],
                    trigger_reason=tree_use["trigger_reason"],
                    changed_action=tree_use.get("changed_action"),
                    official_success_after_use=reward > 0,
                )
            self._open_tree_uses.clear()

    def _tree_plan(self) -> tuple[bool, str]:
        if self._runtime_version == "v1":
            return self._mode == "hybrid", "v1_every_step" if self._mode == "hybrid" else ""
        if self._mode != "hybrid":
            self._pending_tree_reason = ""
            return False, ""
        reason = self._pending_tree_reason
        self._pending_tree_reason = ""
        return bool(reason), reason

    def _observe(
        self,
        include_tree: bool,
        tree_reason: str,
        *,
        phase: str,
    ) -> tuple[Any, ScreenState, dict[str, Any] | None]:
        image, screen = self._adapter.observe(include_ui_tree=include_tree)
        tree_use: dict[str, Any] | None = None
        summary = _ui_tree_summary(screen) if include_tree else None
        if include_tree and self._runtime_version == "v2":
            self._tree_use_counter += 1
            tree_use = {
                "tree_use_id": self._tree_use_counter,
                "trigger_reason": tree_reason,
                "changed_action": None,
            }
            self._open_tree_uses.append(tree_use)
        self._trace.write(
            "observation",
            step=self._step_index,
            mode=self._mode,
            runtime_version=self._runtime_version,
            phase=phase,
            screen_fingerprint=screen.fingerprint,
            image_size=screen.image_size,
            ui_element_count=len(screen.elements),
            ui_tree_requested=include_tree,
            ui_tree_trigger_reason=tree_reason,
            ui_tree_summary=summary,
            tree_use_id=tree_use["tree_use_id"] if tree_use else None,
        )
        return image, screen, tree_use

    def _task_state(self, *, protocol_feedback: str = "") -> AndroidWorldTaskState:
        progress = self._progress
        return AndroidWorldTaskState(
            goal=self._goal,
            step_index=self._step_index,
            remaining_steps=self._max_steps - self._step_index,
            completed_action_summaries=tuple(
                self._history if self._runtime_version == "v1" else progress.completed
            ),
            last_verifier_result=(
                self._last_verifier
                if self._runtime_version == "v1"
                else progress.last_verifier
            ),
            recent_failure=(
                self._recent_failure
                if self._runtime_version == "v1"
                else progress.recent_failure
            ),
            current_subgoal=progress.current_subgoal,
            current_blocker=progress.current_blocker,
            next_verification=progress.next_verification,
            recovery_reason=(
                self._recovery.active.trigger if self._recovery.active else ""
            ),
            protocol_feedback=protocol_feedback,
            runtime_version=self._runtime_version,
        )

    def _decide(
        self,
        image: Any,
        screen: ScreenState,
        include_tree: bool,
        *,
        phase: str,
        protocol_feedback: str = "",
    ) -> AndroidWorldActorDecision:
        request = AndroidWorldActorRequest(
            self._task_state(protocol_feedback=protocol_feedback),
            image,
            screen,
            include_tree,
        )
        decision = self._policy.decide_with_metrics(request)
        locally_normalized = False
        if (
            self._runtime_version == "v2"
            and decision.result.is_success
            and decision.result.raw_output
        ):
            locally_normalized = not parse_androidworld_actor_output(
                decision.result.raw_output,
                screen.image_size,
                allow_v2_repairs=False,
            ).is_success
        self._trace.write(
            "actor_decision",
            step=self._step_index,
            phase=phase,
            parsed=decision.result.is_success,
            error_kind=(
                decision.result.error_kind.value
                if decision.result.error_kind
                else ""
            ),
            message=decision.result.message,
            raw_response=decision.result.raw_output,
            protocol_normalized=locally_normalized,
            metrics=asdict(decision.metrics),
            runtime_version=self._runtime_version,
        )
        if locally_normalized:
            self._trace.write(
                "protocol_guard",
                step=self._step_index,
                strategy="unambiguous_local_normalization",
                outcome="action_obtained",
                action=decision.result.action.type.value,
            )
        return decision

    def _protocol_guard_retry(
        self,
        failed: AndroidWorldActorDecision,
        screen: ScreenState,
    ) -> tuple[Any, ScreenState, AndroidWorldActorDecision, dict[str, Any] | None] | None:
        if self._protocol_retry_used:
            self._trace.write(
                "protocol_guard",
                step=self._step_index,
                strategy="structured_retry",
                outcome="retry_limit_reached",
                original_error=failed.result.message,
            )
            return None
        self._protocol_retry_used = True
        feedback = (
            "Your previous response was invalid and no device action was executed. "
            f"Error: {failed.result.message}. Return exactly one valid JSON object "
            "using only the listed action schema. Do not repeat malformed text."
        )
        self._trace.write(
            "protocol_guard",
            step=self._step_index,
            strategy="structured_retry",
            outcome="triggered",
            original_error_kind=(
                failed.result.error_kind.value
                if failed.result.error_kind
                else ErrorKind.PARSE_ERROR.value
            ),
            original_error=failed.result.message,
            action_executed_before_retry=False,
        )
        include_tree = self._mode == "hybrid"
        image, retry_screen, tree_use = self._observe(
            include_tree,
            "invalid_actor_output" if include_tree else "",
            phase="protocol_retry",
        )
        retry = self._decide(
            image,
            retry_screen,
            include_tree,
            phase="protocol_retry",
            protocol_feedback=feedback,
        )
        self._trace.write(
            "protocol_guard",
            step=self._step_index,
            strategy="structured_retry",
            outcome="action_obtained" if retry.result.is_success else "retry_failed",
            retry_error=retry.result.message,
        )
        return image, retry_screen, retry, tree_use

    def _handle_ui_tree_request(
        self,
        image: Any,
        screen: ScreenState,
        include_tree: bool,
    ) -> (
        AgentInteractionResult
        | tuple[Any, ScreenState, AndroidWorldActorDecision, dict[str, Any] | None]
    ):
        if self._mode != "hybrid" or include_tree or self._model_tree_request_used:
            self._recent_failure = "UI Tree request is unavailable or already used."
            return self._finish("invalid_ui_tree_request")
        self._model_tree_request_used = True
        self._trace.write(
            "ui_tree_tool_requested",
            step=self._step_index,
            reason="visual_uncertainty",
            action_executed_before_request=False,
        )
        image, tree_screen, tree_use = self._observe(
            True,
            "visual_uncertainty",
            phase="ui_tree_tool",
        )
        decision = self._decide(
            image,
            tree_screen,
            True,
            phase="after_ui_tree_tool",
        )
        if (
            decision.result.is_success
            and decision.result.action is not None
            and decision.result.action.type is ActionType.CALL_TOOL
        ):
            self._recent_failure = "Actor repeated REQUEST_UI_TREE after receiving the tree."
            return self._finish("invalid_ui_tree_request")
        return image, tree_screen, decision, tree_use

    def _record_tree_decision(
        self,
        tree_use: dict[str, Any],
        action: Action,
    ) -> None:
        blocked_action = (
            self._recovery.active.blocked_action
            if self._recovery.active
            else None
        )
        changed = (
            None
            if blocked_action is None
            else not actions_are_similar(action, blocked_action)
        )
        tree_use["changed_action"] = changed
        self._trace.write(
            "ui_tree_decision",
            step=self._step_index,
            tree_use_id=tree_use["tree_use_id"],
            trigger_reason=tree_use["trigger_reason"],
            action=action.type.value,
            changed_action=changed,
        )

    def _begin_recovery(self, trigger: str, *, blocked_action: Action) -> bool:
        episode = self._recovery.begin(
            trigger,
            step=self._step_index,
            blocked_action=blocked_action,
        )
        if episode is None:
            self._trace.write(
                "agent_recovery_skipped",
                step=self._step_index,
                trigger=trigger,
                reason="single recovery budget already used",
            )
            return False
        self._progress.current_blocker = trigger
        blocked_signature = action_signature(blocked_action)
        navigation_hint = (
            " Navigation is looping: choose a different action family; when the "
            "goal depends on an installed app, consider direct OPEN_APP."
            if trigger in {"repeated_similar_action", "alternating_action_loop"}
            else ""
        )
        self._progress.recent_failure = (
            f"{trigger}; blocked action: {blocked_signature}. Re-observe and choose "
            "a meaningfully different safe action. Do not repeat an uncertain "
            f"side-effecting action.{navigation_hint}"
        )
        self._pending_tree_reason = trigger if self._mode == "hybrid" else ""
        self._trace.write(
            "agent_recovery_triggered",
            step=self._step_index,
            recovery_id=episode.recovery_id,
            trigger=trigger,
            blocked_action=action_signature(blocked_action),
            ui_tree_requested_next=self._mode == "hybrid",
            recovery_budget_remaining=0,
        )
        return True


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


def _ui_tree_summary(screen: ScreenState) -> dict[str, Any]:
    labels: list[str] = []
    for element in screen.elements:
        label = (
            element.text
            or element.content_description
            or element.resource_id.rsplit("/", 1)[-1]
        ).strip()
        if label and label not in labels:
            labels.append(label[:80])
        if len(labels) >= 12:
            break
    return {
        "element_count": len(screen.elements),
        "clickable_count": sum(item.clickable for item in screen.elements),
        "editable_count": sum(item.editable for item in screen.elements),
        "sample_labels": labels,
    }
