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
    CompletionEvidence,
    PlanState,
    RecoveryController,
    RuntimeProgress,
    SCREEN_CONTEXT_CHANGE,
    SCREEN_EXACTLY_UNCHANGED,
    SCREEN_VISUALLY_SIMILAR,
    SubgoalState,
    action_signature,
    actions_are_similar,
    checkpoint_evidence_matches,
    classify_screen_change,
    completion_evidence_matches,
)
from mobile_pilot.androidworld.progress_verifier import QwenProgressVerifier
from mobile_pilot.androidworld.evaluation import is_official_success
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
        progress_verifier: Any | None = None,
        subgoal_manager: Any | None = None,
        progress_verifier_mode: str = "hybrid",
        trace_path: str | Path,
        runtime_version: str = "v2",
    ) -> None:
        if mode not in {"vision_only", "hybrid"}:
            raise ValueError("mode must be vision_only or hybrid")
        if runtime_version not in {"v1", "v2", "v2.1", "v2.2"}:
            raise ValueError("runtime_version must be v1, v2, v2.1, or v2.2")
        if progress_verifier_mode not in {"off", "hybrid"}:
            raise ValueError("progress_verifier_mode must be off or hybrid")
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
        self._progress_verifier_mode = (
            progress_verifier_mode if runtime_version == "v2.2" else "off"
        )
        self._progress_verifier = progress_verifier
        if runtime_version == "v2.2" and progress_verifier_mode == "hybrid":
            self._progress_verifier = progress_verifier or QwenProgressVerifier()
        self._subgoal_manager = subgoal_manager
        self._trace = JsonlTraceWriter(trace_path)
        self._trace_path = Path(trace_path)
        self._goal = ""
        self._reset_runtime_state()

    def _reset_runtime_state(self) -> None:
        self._step_index = 0
        self._history: list[str] = []
        self._last_verifier = ""
        self._recent_failure = ""
        self._protocol_retry_used = False
        self._checkpoint_correction_pending = False
        self._model_tree_request_used = False
        self._pending_tree_reason = ""
        self._progress = RuntimeProgress()
        self._recovery = RecoveryController(
            max_attempts=2 if self._runtime_version in {"v2.1", "v2.2"} else 1,
            secondary_level="subgoal" if self._runtime_version == "v2.2" else "plan",
        )
        self._plan = PlanState.direct("V1/V2 has no explicit checklist")
        self._plan_initialized = False
        self._plan_replan_pending = False
        self._subgoals = SubgoalState()
        self._subgoal_start_image: Any | None = None
        self._last_executed_action: Action | None = None
        self._subgoal_revision_pending = False
        self._subgoal_boundary_pending = self._runtime_version == "v2.2"
        self._verifier_call_counter = 0
        self._tree_use_counter = 0
        self._open_tree_uses: list[dict[str, Any]] = []

    def step(self, goal: str) -> AgentInteractionResult:
        if self._goal and self._goal != goal:
            self._reset_runtime_state()
        self._goal = goal
        if self._runtime_version in {"v2.1", "v2.2"}:
            # One retry is safe at each decision point because an invalid
            # response has not executed a device action. V2 keeps its frozen
            # task-global retry behavior for historical comparison.
            self._protocol_retry_used = False
        if self._step_index >= self._max_steps:
            return self._finish("step_budget_exhausted")

        include_tree, tree_reason = self._tree_plan()
        image, screen, tree_use = self._observe(include_tree, tree_reason, phase="decision")
        if self._runtime_version == "v2.1":
            planning_result = self._ensure_plan(image)
            if planning_result is not None:
                return planning_result
            if self._plan_replan_pending:
                replan_result = self._revise_plan(image)
                if replan_result is not None:
                    return replan_result
        if self._runtime_version == "v2.2":
            self._ensure_managed_subgoal(image, screen)
        self._progress.remember_screen(self._screen_loop_key(screen))
        decision = self._decide(image, screen, include_tree, phase="primary")

        if (
            self._runtime_version in {"v2", "v2.1", "v2.2"}
            and decision.result.is_success
            and decision.result.action is not None
            and decision.result.action.type is ActionType.CALL_TOOL
        ):
            tool_result = self._handle_ui_tree_request(
                image,
                screen,
                include_tree,
                tree_use,
            )
            if isinstance(tool_result, AgentInteractionResult):
                return tool_result
            image, screen, decision, tree_use = tool_result

        if not decision.result.is_success and self._runtime_version in {"v2", "v2.1", "v2.2"}:
            guarded = self._protocol_guard_retry(decision, screen)
            if guarded is not None:
                image, screen, decision, tree_use = guarded

        if not decision.result.is_success:
            self._recent_failure = decision.result.message
            if decision.result.error_kind is ErrorKind.UNSUPPORTED_ACTION_CAPABILITY:
                return self._finish("unsupported_action_capability")
            return self._finish("invalid_actor_output")

        action = decision.result.action
        assert action is not None
        if action.type is ActionType.CALL_TOOL:
            self._recent_failure = (
                "Actor requested UI Tree after the on-demand tool opportunity was exhausted."
            )
            return self._finish("invalid_ui_tree_request")
        if tree_use is not None:
            tree_grounded = self._record_tree_decision(tree_use, action, screen)
            if (
                self._runtime_version == "v2.2"
                and self._recovery.active is not None
                and not tree_grounded
            ):
                episode = self._recovery.active
                task_grounding = _task_grounded_recovery_action(
                    action,
                    goal=self._goal,
                    active_subgoal=self._subgoals.active_goal,
                    completed_subgoals=self._subgoals.completed_goals,
                )
                self._trace.write(
                    "agent_recovery_replan",
                    step=self._step_index,
                    recovery_id=episode.recovery_id,
                    changed_action=(
                        not actions_are_similar(action, episode.blocked_action)
                    ),
                    candidate_action=action_signature(action),
                    blocked_action=action_signature(episode.blocked_action),
                    new_evidence=tree_use.get("new_evidence", ""),
                    chosen_ui_element=tree_use.get("chosen_ui_element"),
                    result=(
                        "task_grounded_fallback"
                        if task_grounding
                        else "insufficient_new_evidence"
                    ),
                    reason=(
                        task_grounding
                        or "Recovery action was not grounded in the supplied UI Tree."
                    ),
                )
                if not task_grounding:
                    self._progress.recent_failure = "insufficient_new_evidence"
                    return self._finish("insufficient_new_evidence")

        if (
            self._runtime_version == "v2.1"
            and action.type is ActionType.PROPOSE_CHECKPOINT_COMPLETE
        ):
            return self._handle_checkpoint_proposal(action, image, screen, include_tree)

        if (
            self._runtime_version == "v2.2"
            and action.type is ActionType.PROPOSE_SUBGOAL_COMPLETE
        ):
            return self._handle_subgoal_completion_proposal(action, image, screen)

        if self._runtime_version == "v2.2":
            self._accept_actor_subgoal_proposal(action, image)

        if self._runtime_version in {"v2", "v2.1", "v2.2"}:
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
                    if self._runtime_version in {"v2.1", "v2.2"} and self._begin_recovery(
                        "action_recovery_repeated_blocked_action",
                        blocked_action=action,
                    ):
                        return AgentInteractionResult(
                            done=False,
                            data={
                                "reason": "plan_replan_requested",
                                "steps": self._step_index,
                                "trigger": "action_recovery_repeated_blocked_action",
                                "runtime_version": self._runtime_version,
                            },
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
            if self._runtime_version in {"v2", "v2.1", "v2.2"} and self._begin_recovery(
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

        self._checkpoint_correction_pending = False
        result = self._adapter.execute(action)
        if self._runtime_version == "v1":
            self._history.append(_summary(action))
        else:
            self._progress.prepare_action(action)
            if self._runtime_version == "v2.2" and self._subgoals.active:
                self._progress.current_subgoal = self._subgoals.active_goal
                self._progress.next_verification = (
                    self._subgoals.active_evidence.describe()
                    if self._subgoals.active_evidence
                    else ""
                )
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
            if self._runtime_version in {"v2", "v2.1", "v2.2"} and self._begin_recovery(
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

        if self._runtime_version in {"v2", "v2.1", "v2.2"}:
            self._progress.record_execution(action, executed=True, message=result.message)
            self._recovery.mark_action_executed()
        after_image, after = self._adapter.observe(
            include_ui_tree=include_tree,
            include_context_signals=self._runtime_version in {"v2.1", "v2.2"},
        )
        if self._runtime_version in {"v2.1", "v2.2"}:
            self._last_verifier, verifier_details = classify_screen_change(screen, after)
        else:
            self._last_verifier = "screen_changed" if screen.fingerprint != after.fingerprint else "screen_unchanged"
            verifier_details = {"exact_match": screen.fingerprint == after.fingerprint}
        self._trace.write(
            "verifier",
            step=self._step_index - 1,
            result=self._last_verifier,
            before_fingerprint=screen.fingerprint,
            after_fingerprint=after.fingerprint,
            before_visual_fingerprint=screen.visual_fingerprint,
            after_visual_fingerprint=after.visual_fingerprint,
            signal_details=verifier_details,
            next_verification=(
                self._progress.next_verification
                if self._runtime_version in {"v2", "v2.1", "v2.2"}
                else ""
            ),
            runtime_version=self._runtime_version,
        )

        if self._runtime_version == "v2.2":
            self._last_executed_action = action
            subgoal_result = self._verify_subgoal_after_action(
                before_image=image,
                before_screen=screen,
                after_image=after_image,
                after_screen=after,
                action=action,
                screen_change=self._last_verifier,
                signal_details=verifier_details,
            )
            if subgoal_result is not None:
                return subgoal_result
            if action.type is ActionType.ANSWER:
                # ANSWER writes AndroidWorld's official interaction cache and
                # intentionally leaves the screenshot unchanged. Let the
                # benchmark judge it before visual loop logic can intervene.
                return AgentInteractionResult(
                    done=False,
                    data={
                        "reason": "answer_submitted_for_official_reward",
                        "steps": self._step_index,
                        "runtime_version": self._runtime_version,
                    },
                )

        if self._runtime_version == "v1" and self._last_verifier == "screen_unchanged" and action.type is not ActionType.WAIT:
            wait = Action(ActionType.WAIT, source="generic_recovery")
            recovery = self._adapter.execute(wait)
            self._trace.write("recovery", step=self._step_index - 1, strategy="wait_after_unchanged_screen", executed=recovery.executed)

        if self._runtime_version in {"v2", "v2.1", "v2.2"}:
            if self._runtime_version in {"v2.1", "v2.2"}:
                self._progress.record_verification(result=self._last_verifier, action=action)
            else:
                self._progress.record_verification(
                    changed=self._last_verifier == "screen_changed",
                    action=action,
                )
            loop_key = self._screen_loop_key(after)
            page_signal = self._progress.page_loop_signal(loop_key)
            self._progress.remember_screen(loop_key)
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

    def _ensure_plan(self, image: Any) -> AgentInteractionResult | None:
        if self._plan_initialized:
            return None
        self._plan_initialized = True
        planner = getattr(self._policy, "plan_with_metrics", None)
        if not callable(planner):
            self._plan = PlanState.direct("Policy has no Planner; safe direct fallback")
            self._trace.write(
                "planner_decision",
                step=self._step_index,
                outcome="fallback_direct",
                reason=self._plan.reason,
                runtime_version=self._runtime_version,
            )
            return None
        decision = planner(goal=self._goal, image=image)
        if decision.plan is None:
            self._plan = PlanState.direct(
                "Planner output was unavailable; continue with bounded reactive execution"
            )
            outcome = "fallback_direct"
        else:
            self._plan = decision.plan
            outcome = "plan_created"
        self._trace.write(
            "planner_decision",
            step=self._step_index,
            outcome=outcome,
            message=decision.message,
            raw_response=decision.raw_output,
            metrics=asdict(decision.metrics),
            plan=_plan_payload(self._plan),
            runtime_version=self._runtime_version,
        )
        return None

    def _revise_plan(self, image: Any) -> AgentInteractionResult | None:
        episode = self._recovery.active
        self._plan_replan_pending = False
        if episode is None or episode.level != "plan":
            return None
        planner = getattr(self._policy, "plan_with_metrics", None)
        if not callable(planner):
            return self._finish("plan_recovery_unavailable")
        before = _plan_payload(self._plan)
        decision = planner(
            goal=self._goal,
            image=image,
            current_plan=self._plan,
            recovery_reason=episode.trigger,
        )
        revised = bool(
            decision.plan is not None
            and self._plan.revise_remaining(
                decision.plan.checkpoints,
                reason=decision.plan.reason or episode.trigger,
            )
        )
        self._trace.write(
            "plan_recovery",
            step=self._step_index,
            recovery_id=episode.recovery_id,
            revised=revised,
            reason=decision.message or (decision.plan.reason if decision.plan else ""),
            raw_response=decision.raw_output,
            metrics=asdict(decision.metrics),
            before_plan=before,
            after_plan=_plan_payload(self._plan),
        )
        if not revised:
            return self._finish("plan_recovery_failed")
        return None

    def _handle_checkpoint_proposal(
        self,
        action: Action,
        image: Any,
        screen: ScreenState,
        include_tree: bool,
    ) -> AgentInteractionResult:
        checkpoint = self._plan.active
        if self._plan.mode != "checklist" or checkpoint is None:
            if self._checkpoint_correction_pending:
                self._recent_failure = (
                    "Actor repeated checkpoint completion without an active checkpoint."
                )
                return self._finish("repeated_invalid_checkpoint_proposal")
            self._checkpoint_correction_pending = True
            correction = (
                "No active checkpoint exists. Continue with a normal action; "
                "use PROPOSE_COMPLETE only when the whole task is visibly complete."
            )
            self._progress.current_blocker = "checkpoint_proposal_without_active_checkpoint"
            self._progress.recent_failure = correction
            self._trace.write(
                "checkpoint_proposal_corrected",
                step=self._step_index,
                plan_mode=self._plan.mode,
                plan_complete=self._plan.is_complete,
                action_executed=False,
                correction=correction,
            )
            return AgentInteractionResult(
                done=False,
                data={
                    "reason": "checkpoint_proposal_corrected",
                    "steps": self._step_index,
                    "runtime_version": self._runtime_version,
                },
            )

        actor_claim = str(action.parameters.get("observed_evidence", "")).strip()
        matched, evidence = checkpoint_evidence_matches(checkpoint, screen)
        verification_image, verification_screen = image, screen
        used_tree = include_tree
        if matched is None and not include_tree and self._mode == "hybrid":
            verification_image, verification_screen, tree_use = self._observe(
                True,
                "checkpoint_evidence",
                phase="checkpoint_verification",
            )
            used_tree = True
            if tree_use is not None:
                self._record_tree_decision(tree_use, action, verification_screen)
            matched, evidence = checkpoint_evidence_matches(checkpoint, verification_screen)

        verifier_decision = "deterministic_confirmed" if matched else ""
        verifier_metrics: dict[str, Any] | None = None
        verifier_message = ""
        if matched is None:
            verifier = getattr(self._policy, "verify_checkpoint_with_metrics", None)
            if callable(verifier):
                model_result = verifier(
                    checkpoint=checkpoint,
                    claimed_evidence=actor_claim,
                    image=verification_image,
                    screen=verification_screen,
                    include_ui_tree=used_tree,
                )
                verifier_decision = model_result.decision
                evidence = model_result.evidence
                verifier_message = model_result.message
                verifier_metrics = asdict(model_result.metrics)
                matched = model_result.decision == "confirmed"
            else:
                verifier_decision = "uncertain"
                verifier_message = "Policy has no constrained checkpoint Verifier."
                matched = False
        elif matched is False:
            verifier_decision = "deterministic_not_confirmed"

        self._trace.write(
            "checkpoint_verifier",
            step=self._step_index,
            checkpoint=checkpoint.goal,
            frozen_evidence=checkpoint.evidence.describe(),
            actor_claim=actor_claim,
            decision=verifier_decision,
            evidence=evidence,
            message=verifier_message,
            metrics=verifier_metrics,
            ui_tree_used=used_tree,
            actor_self_certified=False,
        )
        if matched:
            self._checkpoint_correction_pending = False
            confirmed = self._plan.confirm_active()
            self._progress.current_subgoal = self._plan.active.goal if self._plan.active else ""
            self._progress.current_blocker = ""
            self._progress.next_verification = (
                self._plan.active.evidence.describe() if self._plan.active else "official task reward"
            )
            self._trace.write(
                "checkpoint_advanced",
                step=self._step_index,
                confirmed=confirmed.goal if confirmed else "",
                plan=_plan_payload(self._plan),
                whole_task_success_claimed=False,
            )
            return AgentInteractionResult(
                done=False,
                data={
                    "reason": "checkpoint_confirmed",
                    "steps": self._step_index,
                    "checkpoint": confirmed.goal if confirmed else "",
                    "runtime_version": self._runtime_version,
                },
            )

        trigger = "checkpoint_evidence_not_confirmed"
        self._progress.current_blocker = trigger
        self._progress.recent_failure = f"{trigger}: {evidence or verifier_message}"
        if self._begin_recovery(trigger, blocked_action=action):
            return AgentInteractionResult(
                done=False,
                data={
                    "reason": "agent_replan_requested",
                    "steps": self._step_index,
                    "trigger": trigger,
                    "runtime_version": self._runtime_version,
                },
            )
        return self._finish("checkpoint_not_confirmed")

    def _accept_actor_subgoal_proposal(self, action: Action, image: Any) -> None:
        goal = str(action.parameters.get("subgoal", "")).strip()
        kind = str(action.parameters.get("completion_evidence_kind", "")).strip()
        value = str(action.parameters.get("completion_evidence_value", "")).strip()
        normalized = False
        if goal and (not kind or not value) and action.expected_outcome.strip():
            # V2 already asked for an expected visible outcome. Treating that
            # exact text as visual_state is an unambiguous compatibility path,
            # not a Runtime-invented success condition.
            kind, value = "visual_state", action.expected_outcome.strip()
            normalized = True
        if not goal or not kind or not value:
            return
        try:
            evidence = CompletionEvidence(kind, value)
        except ValueError as exc:
            self._trace.write(
                "subgoal_proposal",
                step=self._step_index,
                outcome="invalid_ignored",
                goal=goal,
                evidence={"kind": kind, "value": value},
                message=str(exc),
                action_executed=False,
            )
            return
        outcome = self._subgoals.accept_proposal(
            goal,
            evidence,
            allow_revision=self._subgoal_revision_pending,
            revision_reason=(
                self._recovery.active.trigger if self._recovery.active else ""
            ),
        )
        if outcome in {"accepted", "revised"}:
            self._subgoal_start_image = image.copy()
            self._progress.current_subgoal = self._subgoals.active_goal
            self._progress.next_verification = evidence.describe()
            if outcome == "revised":
                self._subgoal_revision_pending = False
        elif outcome == "mutation_blocked":
            self._progress.recent_failure = (
                "Actor proposed changing the frozen subgoal; Runtime kept the original."
            )
        self._trace.write(
            "subgoal_proposal",
            step=self._step_index,
            outcome=outcome,
            proposed_goal=goal,
            proposed_evidence={"kind": kind, "value": value},
            normalized_from_expected_outcome=normalized,
            frozen_state=self._subgoals.snapshot(),
            lifecycle_owned_by_runtime=True,
        )

    def _ensure_managed_subgoal(self, image: Any, screen: ScreenState) -> None:
        """Ask for one subgoal only at a lifecycle boundary.

        Failure is fail-open for phone execution: the Actor can still choose a
        safe action from the whole goal, but Runtime does not invent evidence
        and does not retry the manager on every step.
        """
        if not self._subgoal_boundary_pending:
            return
        self._subgoal_boundary_pending = False
        if self._subgoals.active and not self._subgoal_revision_pending:
            return
        trigger = (
            "recovery_revision"
            if self._subgoal_revision_pending
            else "previous_completed"
            if self._subgoals.completed_goals
            else "initial"
        )
        manager = self._subgoal_manager
        call = getattr(manager, "propose_with_metrics", None)
        if not callable(call):
            self._trace.write(
                "subgoal_manager",
                step=self._step_index,
                trigger=trigger,
                outcome="unavailable",
                message="No Subgoal Manager was configured; Actor remains action-only.",
                action_executed=False,
            )
            return
        evidence_before = (
            self._subgoals.active_evidence.describe()
            if self._subgoals.active_evidence
            else ""
        )
        manager_request = dict(
            image=image,
            task_goal=self._goal,
            completed_subgoals=tuple(self._subgoals.completed_goals),
            trigger=trigger,
            current_subgoal=self._subgoals.active_goal,
            current_evidence=evidence_before,
            recovery_reason=(
                self._recovery.active.trigger if self._recovery.active else ""
            ),
            package_activity=screen.package_activity,
            visible_ui_text=screen.verification_texts,
        )
        decision = call(**manager_request)
        outcome = "invalid_ignored"
        manager_message = decision.message
        regeneration_attempt = 0
        if decision.is_success and decision.evidence is not None:
            already_matched, current_evidence = completion_evidence_matches(
                decision.evidence,
                screen,
            )
            if already_matched is True:
                rejected_message = (
                    "Proposed evidence was already satisfied before any action: "
                    + current_evidence
                )
                self._trace.write(
                    "subgoal_manager",
                    step=self._step_index,
                    trigger=trigger,
                    outcome="invalid_already_satisfied_regenerating",
                    proposed_subgoal=decision.subgoal,
                    proposed_evidence={
                        "kind": decision.evidence.kind,
                        "value": decision.evidence.value,
                    },
                    reason=decision.reason,
                    message=rejected_message,
                    raw_response=decision.raw_output,
                    metrics=asdict(decision.metrics),
                    frozen_state=self._subgoals.snapshot(),
                    action_executed=False,
                    lifecycle_owned_by_runtime=True,
                    regeneration_attempt=0,
                )
                regeneration_attempt = 1
                decision = call(
                    **manager_request,
                    rejected_evidence_feedback=(
                        rejected_message
                        + ". Provide one different postcondition that is not "
                        "already visible; do not repeat the rejected evidence."
                    ),
                )
                manager_message = decision.message
                if decision.is_success and decision.evidence is not None:
                    already_matched, current_evidence = completion_evidence_matches(
                        decision.evidence,
                        screen,
                    )
                    if already_matched is True:
                        outcome = "invalid_already_satisfied"
                        manager_message = (
                            "Regenerated evidence was also already satisfied before "
                            "any action: " + current_evidence
                        )
                    else:
                        outcome = self._subgoals.accept_proposal(
                            decision.subgoal,
                            decision.evidence,
                            allow_revision=self._subgoal_revision_pending,
                            revision_reason=(
                                self._recovery.active.trigger
                                if self._recovery.active
                                else ""
                            ),
                        )
                else:
                    outcome = "invalid_regeneration_failed"
            else:
                outcome = self._subgoals.accept_proposal(
                    decision.subgoal,
                    decision.evidence,
                    allow_revision=self._subgoal_revision_pending,
                    revision_reason=(
                        self._recovery.active.trigger if self._recovery.active else ""
                    ),
                )
            if outcome in {"accepted", "revised", "unchanged"}:
                if outcome in {"accepted", "revised"}:
                    self._subgoal_start_image = image.copy()
                self._progress.current_subgoal = self._subgoals.active_goal
                self._progress.next_verification = (
                    self._subgoals.active_evidence.describe()
                    if self._subgoals.active_evidence
                    else ""
                )
                self._subgoal_revision_pending = False
        self._trace.write(
            "subgoal_manager",
            step=self._step_index,
            trigger=trigger,
            outcome=outcome,
            proposed_subgoal=decision.subgoal,
            proposed_evidence=(
                {
                    "kind": decision.evidence.kind,
                    "value": decision.evidence.value,
                }
                if decision.evidence
                else None
            ),
            reason=decision.reason,
            message=manager_message,
            raw_response=decision.raw_output,
            metrics=asdict(decision.metrics),
            frozen_state=self._subgoals.snapshot(),
            action_executed=False,
            lifecycle_owned_by_runtime=True,
            regeneration_attempt=regeneration_attempt,
        )

    def _handle_subgoal_completion_proposal(
        self,
        action: Action,
        image: Any,
        screen: ScreenState,
    ) -> AgentInteractionResult:
        if not self._subgoals.active or self._subgoals.active_evidence is None:
            self._progress.recent_failure = (
                "No frozen subgoal exists; continue with a normal action or propose whole-task completion."
            )
            self._trace.write(
                "subgoal_completion_proposed",
                step=self._step_index,
                outcome="no_active_subgoal",
                action_executed=False,
            )
            return AgentInteractionResult(
                done=False,
                data={
                    "reason": "subgoal_proposal_corrected",
                    "steps": self._step_index,
                    "runtime_version": self._runtime_version,
                },
            )

        evidence = self._subgoals.active_evidence
        matched, deterministic_evidence = completion_evidence_matches(evidence, screen)
        actor_claim = str(action.parameters.get("observed_evidence", "")).strip()
        self._trace.write(
            "subgoal_completion_proposed",
            step=self._step_index,
            subgoal=self._subgoals.active_goal,
            frozen_evidence=evidence.describe(),
            actor_claim=actor_claim,
            deterministic_match=matched,
            deterministic_evidence=deterministic_evidence,
            actor_self_certified=False,
            action_executed=False,
        )
        if matched is True:
            confirmed = self._confirm_active_subgoal(
                source="deterministic",
                evidence=deterministic_evidence,
            )
            return AgentInteractionResult(
                done=False,
                data={
                    "reason": "subgoal_confirmed",
                    "subgoal": confirmed,
                    "steps": self._step_index,
                    "runtime_version": self._runtime_version,
                },
            )

        decision = self._call_progress_verifier(
            before_image=self._subgoal_start_image or image,
            after_image=image,
            action=action,
            trigger="actor_proposed_subgoal_complete",
            signal_details={
                "deterministic_match": matched,
                "deterministic_evidence": deterministic_evidence,
            },
            actor_claim=actor_claim,
        )
        if decision is not None and decision.verdict == "completed" and matched is None:
            confirmed = self._confirm_active_subgoal(
                source="vlm_progress_verifier",
                evidence=decision.evidence,
            )
            return AgentInteractionResult(
                done=False,
                data={
                    "reason": "subgoal_confirmed",
                    "subgoal": confirmed,
                    "steps": self._step_index,
                    "runtime_version": self._runtime_version,
                },
            )

        trigger = (
            "subgoal_regressed"
            if decision is not None and decision.verdict == "regressed"
            else "subgoal_evidence_not_confirmed"
        )
        self._progress.current_blocker = trigger
        self._progress.recent_failure = (
            decision.evidence if decision is not None else deterministic_evidence
        )
        blocked_action = self._last_executed_action or action
        if self._begin_recovery(trigger, blocked_action=blocked_action):
            return AgentInteractionResult(
                done=False,
                data={
                    "reason": "agent_replan_requested",
                    "trigger": trigger,
                    "steps": self._step_index,
                    "runtime_version": self._runtime_version,
                },
            )
        return self._finish("subgoal_not_confirmed")

    def _verify_subgoal_after_action(
        self,
        *,
        before_image: Any,
        before_screen: ScreenState,
        after_image: Any,
        after_screen: ScreenState,
        action: Action,
        screen_change: str,
        signal_details: dict[str, Any],
    ) -> AgentInteractionResult | None:
        if not self._subgoals.active or self._subgoals.active_evidence is None:
            return None
        evidence = self._subgoals.active_evidence
        matched, deterministic_evidence = completion_evidence_matches(
            evidence, after_screen
        )
        self._trace.write(
            "deterministic_progress_verifier",
            step=self._step_index - 1,
            subgoal=self._subgoals.active_goal,
            frozen_evidence=evidence.describe(),
            matched=matched,
            evidence=deterministic_evidence,
            screen_change=screen_change,
            action=action_signature(action),
        )
        if matched is True:
            confirmed = self._confirm_active_subgoal(
                source="deterministic",
                evidence=deterministic_evidence,
            )
            return AgentInteractionResult(
                done=False,
                data={
                    "reason": "subgoal_confirmed",
                    "subgoal": confirmed,
                    "steps": self._step_index,
                    "runtime_version": self._runtime_version,
                },
            )

        predicted_unchanged = self._progress.unchanged_streak + (
            1
            if screen_change in {SCREEN_EXACTLY_UNCHANGED, SCREEN_VISUALLY_SIMILAR}
            else 0
        )
        trigger = ""
        if evidence.kind == "visual_state" and screen_change not in {
            SCREEN_EXACTLY_UNCHANGED,
            SCREEN_VISUALLY_SIMILAR,
        }:
            trigger = "visual_state_progress_check"
        elif screen_change == SCREEN_CONTEXT_CHANGE:
            trigger = "navigation_context_changed"
        elif predicted_unchanged >= 2:
            trigger = "suspected_stalled"
        if not trigger:
            return None

        decision = self._call_progress_verifier(
            before_image=before_image,
            after_image=after_image,
            action=action,
            trigger=trigger,
            signal_details={
                **signal_details,
                "deterministic_match": matched,
                "deterministic_evidence": deterministic_evidence,
            },
        )
        if decision is None:
            return None
        if decision.verdict == "completed" and matched is None:
            confirmed = self._confirm_active_subgoal(
                source="vlm_progress_verifier",
                evidence=decision.evidence,
            )
            return AgentInteractionResult(
                done=False,
                data={
                    "reason": "subgoal_confirmed",
                    "subgoal": confirmed,
                    "steps": self._step_index,
                    "runtime_version": self._runtime_version,
                },
            )
        if decision.verdict in {"stalled", "regressed"}:
            recovery_trigger = f"progress_verifier_{decision.verdict}"
            self._progress.current_blocker = recovery_trigger
            self._progress.recent_failure = decision.evidence
            if self._begin_recovery(recovery_trigger, blocked_action=action):
                return AgentInteractionResult(
                    done=False,
                    data={
                        "reason": "agent_replan_requested",
                        "trigger": recovery_trigger,
                        "steps": self._step_index,
                        "runtime_version": self._runtime_version,
                    },
                )
        elif decision.verdict == "uncertain" and self._mode == "hybrid":
            self._pending_tree_reason = "progress_verifier_uncertain"
            self._progress.recent_failure = decision.evidence or decision.message
        return None

    def _call_progress_verifier(
        self,
        *,
        before_image: Any,
        after_image: Any,
        action: Action,
        trigger: str,
        signal_details: dict[str, Any],
        actor_claim: str = "",
    ) -> Any | None:
        verifier = self._progress_verifier
        call = getattr(verifier, "verify_with_metrics", None)
        if self._progress_verifier_mode != "hybrid" or not callable(call):
            self._trace.write(
                "vlm_progress_verifier_skipped",
                step=self._step_index,
                trigger=trigger,
                reason="verifier_mode_off_or_unavailable",
            )
            return None
        evidence = self._subgoals.active_evidence
        if evidence is None:
            return None
        before_path, after_path = self._persist_verifier_images(
            before_image,
            after_image,
            trigger,
        )
        decision = call(
            before_image=before_image,
            after_image=after_image,
            action_summary=action_signature(action),
            task_goal=self._goal,
            subgoal=self._subgoals.active_goal,
            evidence_kind=evidence.kind,
            evidence_value=evidence.value,
            trigger=trigger,
            deterministic_signals=signal_details,
            actor_claim=actor_claim,
        )
        self._trace.write(
            "vlm_progress_verifier",
            step=self._step_index,
            trigger=trigger,
            whole_task_goal=self._goal,
            subgoal=self._subgoals.active_goal,
            frozen_evidence=evidence.describe(),
            verdict=decision.verdict,
            evidence=decision.evidence,
            disposition=decision.disposition,
            message=decision.message,
            raw_response=decision.raw_output,
            metrics=asdict(decision.metrics),
            before_image=before_path,
            after_image=after_path,
            actor_self_certified=False,
        )
        return decision

    def _confirm_active_subgoal(self, *, source: str, evidence: str) -> str:
        confirmed = self._subgoals.confirm_active()
        self._subgoal_start_image = None
        self._subgoal_revision_pending = False
        self._subgoal_boundary_pending = True
        self._progress.current_subgoal = ""
        self._progress.current_blocker = ""
        self._progress.next_verification = "propose the next useful subgoal or whole-task completion"
        self._progress.mark_subgoal_progress()
        self._trace.write(
            "subgoal_completed",
            step=self._step_index,
            subgoal=confirmed,
            source=source,
            evidence=evidence,
            frozen_state=self._subgoals.snapshot(),
            whole_task_success_claimed=False,
        )
        return confirmed

    def _persist_verifier_images(
        self,
        before_image: Any,
        after_image: Any,
        trigger: str,
    ) -> tuple[str, str]:
        self._verifier_call_counter += 1
        safe_trigger = "".join(
            character if character.isalnum() or character in {"-", "_"} else "_"
            for character in trigger
        )[:48]
        media_dir = self._trace_path.parent / f"{self._trace_path.stem}.verifier-media"
        media_dir.mkdir(parents=True, exist_ok=True)
        prefix = f"{self._verifier_call_counter:03d}-step-{self._step_index}-{safe_trigger}"
        before_path = media_dir / f"{prefix}-before.png"
        after_path = media_dir / f"{prefix}-after.png"
        before_image.save(before_path, format="PNG")
        after_image.save(after_path, format="PNG")
        return str(before_path), str(after_path)

    def _screen_loop_key(self, screen: ScreenState) -> str:
        if self._runtime_version in {"v2.1", "v2.2"} and screen.visual_fingerprint:
            return f"{screen.package_activity}|{screen.visual_fingerprint}"
        return screen.fingerprint

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
        if getattr(self, "_runtime_version", "v1") in {"v2", "v2.1", "v2.2"}:
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
        full_success = is_official_success(reward)
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
        if full_success or terminal:
            for tree_use in self._open_tree_uses:
                self._trace.write(
                    "ui_tree_outcome",
                    step=self._step_index,
                    tree_use_id=tree_use["tree_use_id"],
                    trigger_reason=tree_use["trigger_reason"],
                    changed_action=tree_use.get("changed_action"),
                    new_evidence=tree_use.get("new_evidence", ""),
                    chosen_ui_element=tree_use.get("chosen_ui_element"),
                    official_success_after_use=full_success,
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
        image, screen = self._adapter.observe(
            include_ui_tree=include_tree,
            include_context_signals=self._runtime_version in {"v2.1", "v2.2"},
        )
        tree_use: dict[str, Any] | None = None
        summary = _ui_tree_summary(screen) if include_tree else None
        if include_tree and self._runtime_version in {"v2", "v2.1", "v2.2"}:
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
            exact_fingerprint=screen.exact_fingerprint or screen.fingerprint,
            visual_fingerprint=screen.visual_fingerprint,
            semantic_fingerprint=screen.semantic_fingerprint,
            package_activity=screen.package_activity,
            deterministic_ui_text_count=len(screen.verification_texts),
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
            current_subgoal=(
                self._subgoals.active_goal
                if self._runtime_version == "v2.2" and self._subgoals.active
                else progress.current_subgoal
            ),
            current_blocker=progress.current_blocker,
            next_verification=progress.next_verification,
            recovery_reason=(
                self._recovery.active.trigger if self._recovery.active else ""
            ),
            protocol_feedback=protocol_feedback,
            runtime_version=self._runtime_version,
            plan_mode=self._plan.mode,
            completed_checkpoints=self._plan.completed_goals(),
            active_checkpoint=self._plan.active.goal if self._plan.active else "",
            active_checkpoint_evidence=(
                self._plan.active.evidence.describe() if self._plan.active else ""
            ),
            remaining_checkpoints=self._plan.remaining_goals(),
            recovery_level=(
                self._recovery.active.level if self._recovery.active else ""
            ),
            active_subgoal=self._subgoals.active_goal,
            active_subgoal_evidence=(
                self._subgoals.active_evidence.describe()
                if self._subgoals.active_evidence
                else ""
            ),
            completed_subgoals=tuple(self._subgoals.completed_goals),
            subgoal_revision_allowed=self._subgoal_revision_pending,
            progress_verifier_mode=self._progress_verifier_mode,
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
            self._runtime_version in {"v2", "v2.1", "v2.2"}
            and decision.result.is_success
            and decision.result.raw_output
        ):
            locally_normalized = not parse_androidworld_actor_output(
                decision.result.raw_output,
                screen.image_size,
                allow_v2_repairs=False,
                allow_v21_actions=self._runtime_version == "v2.1",
                allow_v22_actions=self._runtime_version == "v2.2",
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
        if failed.result.error_kind is ErrorKind.UNSUPPORTED_ACTION_CAPABILITY:
            self._trace.write(
                "protocol_guard",
                step=self._step_index,
                strategy="structured_retry",
                outcome="not_attempted_for_semantic_capability_gap",
                original_error_kind=ErrorKind.UNSUPPORTED_ACTION_CAPABILITY.value,
                original_error=failed.result.message,
                action_executed_before_retry=False,
            )
            return None
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
        tree_use: dict[str, Any] | None,
    ) -> (
        AgentInteractionResult
        | tuple[Any, ScreenState, AndroidWorldActorDecision, dict[str, Any] | None]
    ):
        if self._mode != "hybrid" or include_tree or self._model_tree_request_used:
            return self._correct_redundant_ui_tree_request(
                image,
                screen,
                include_tree,
                tree_use,
                reason="UI Tree is unavailable, already included, or already used.",
            )
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
            return self._correct_redundant_ui_tree_request(
                image,
                tree_screen,
                True,
                tree_use,
                reason="Actor repeated REQUEST_UI_TREE after receiving the tree.",
            )
        return image, tree_screen, decision, tree_use

    def _correct_redundant_ui_tree_request(
        self,
        image: Any,
        screen: ScreenState,
        include_tree: bool,
        tree_use: dict[str, Any] | None,
        *,
        reason: str,
    ) -> (
        AgentInteractionResult
        | tuple[Any, ScreenState, AndroidWorldActorDecision, dict[str, Any] | None]
    ):
        """Use one no-action protocol retry for a redundant tool request."""
        if self._protocol_retry_used:
            self._recent_failure = reason
            return self._finish("invalid_ui_tree_request")
        self._protocol_retry_used = True
        feedback = (
            reason
            + " No device action was executed. Choose one concrete phone action "
            "from the current screenshot and supplied context; do not request UI Tree again."
        )
        self._trace.write(
            "protocol_guard",
            step=self._step_index,
            strategy="redundant_ui_tree_request",
            outcome="triggered",
            reason=reason,
            action_executed_before_retry=False,
        )
        retry = self._decide(
            image,
            screen,
            include_tree,
            phase="protocol_retry",
            protocol_feedback=feedback,
        )
        repeated = bool(
            retry.result.is_success
            and retry.result.action is not None
            and retry.result.action.type is ActionType.CALL_TOOL
        )
        self._trace.write(
            "protocol_guard",
            step=self._step_index,
            strategy="redundant_ui_tree_request",
            outcome=(
                "retry_repeated_tool"
                if repeated
                else "action_obtained"
                if retry.result.is_success
                else "retry_failed"
            ),
            retry_error=retry.result.message,
        )
        if repeated:
            self._recent_failure = (
                "Actor repeated REQUEST_UI_TREE after one safe correction."
            )
            return self._finish("invalid_ui_tree_request")
        return image, screen, retry, tree_use

    def _record_tree_decision(
        self,
        tree_use: dict[str, Any],
        action: Action,
        screen: ScreenState,
    ) -> bool:
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
        chosen_element, new_evidence = _tree_grounding(screen, action)
        tree_use["changed_action"] = changed
        tree_use["new_evidence"] = new_evidence
        tree_use["chosen_ui_element"] = chosen_element
        self._trace.write(
            "ui_tree_decision",
            step=self._step_index,
            tree_use_id=tree_use["tree_use_id"],
            trigger_reason=tree_use["trigger_reason"],
            action=action.type.value,
            blocked_action=(action_signature(blocked_action) if blocked_action else ""),
            new_evidence=new_evidence,
            chosen_ui_element=chosen_element,
            changed_action=changed,
            result="grounded" if chosen_element else "insufficient_new_evidence",
        )
        return chosen_element is not None

    def _begin_recovery(self, trigger: str, *, blocked_action: Action) -> bool:
        previous = self._recovery.active
        if previous is not None and self._recovery.remaining > 0:
            self._trace.write(
                "agent_recovery_outcome",
                step=self._step_index,
                recovery_id=previous.recovery_id,
                trigger=previous.trigger,
                level=previous.level,
                rescued=False,
                misfire=False,
                outcome="no_progress_before_next_recovery",
                changed_action=previous.changed_action,
            )
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
                reason="bounded recovery budget already used",
            )
            return False
        self._progress.current_blocker = trigger
        self._plan_replan_pending = episode.level == "plan"
        self._subgoal_revision_pending = episode.level == "subgoal"
        if self._subgoal_revision_pending:
            self._subgoal_boundary_pending = True
        blocked_signature = action_signature(blocked_action)
        navigation_hint = (
            " Navigation is looping: choose a different action family; when the "
            "goal depends on an installed app, consider direct OPEN_APP."
            if trigger in {"repeated_similar_action", "alternating_action_loop"}
            else ""
        )
        self._progress.recent_failure = (
            f"{trigger}; recovery level: {episode.level}; blocked action: {blocked_signature}. "
            "Re-observe and choose a meaningfully different safe action. Do not repeat "
            f"an uncertain side-effecting action.{navigation_hint}"
        )
        self._pending_tree_reason = trigger if self._mode == "hybrid" else ""
        self._trace.write(
            "agent_recovery_triggered",
            step=self._step_index,
            recovery_id=episode.recovery_id,
            recovery_level=episode.level,
            trigger=trigger,
            blocked_action=action_signature(blocked_action),
            ui_tree_requested_next=self._mode == "hybrid",
            recovery_budget_remaining=self._recovery.remaining,
        )
        return True


def _bounds_block(action: Action, image_size: tuple[int, int]) -> str:
    if action.type not in {ActionType.CLICK_POINT, ActionType.LONG_PRESS, ActionType.DRAG}:
        return ""
    width, height = image_size
    keys = ("start_point", "end_point") if action.type is ActionType.DRAG else ("point",)
    for key in keys:
        point = action.parameters.get(key, [])
        if not isinstance(point, list) or len(point) != 2:
            return f"{action.type.value} requires a valid {key}"
        x, y = point
        if not isinstance(x, int) or not isinstance(y, int) or not (0 <= x < width and 0 <= y < height):
            return f"{action.type.value} {key} is outside the current screenshot"
    if action.type is ActionType.DRAG and action.parameters.get("start_point") == action.parameters.get("end_point"):
        return "DRAG start_point and end_point must differ"
    return ""


def _summary(action: Action) -> str:
    if action.type in {ActionType.TYPE_TEXT, ActionType.ANSWER}:
        return f"{action.type.value}[text omitted]"
    return action.type.value


def _plan_payload(plan: PlanState) -> dict[str, Any]:
    return {
        "mode": plan.mode,
        "reason": plan.reason,
        "revision_count": plan.revision_count,
        "last_revision_reason": plan.last_revision_reason,
        "checkpoints": [
            {
                "goal": item.goal,
                "evidence": {
                    "kind": item.evidence.kind,
                    "value": item.evidence.value,
                },
                "status": item.status,
            }
            for item in plan.checkpoints
        ],
    }


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


def _tree_grounding(
    screen: ScreenState,
    action: Action,
) -> tuple[dict[str, Any] | None, str]:
    """Find deterministic Tree evidence for one Recovery action."""
    reference = str(action.parameters.get("ui_tree_reference", "")).strip()
    normalized_reference = reference.casefold()
    candidates = list(screen.elements)
    chosen = None
    if normalized_reference:
        for element in candidates:
            searchable = " | ".join(
                [
                    element.text,
                    element.content_description,
                    element.resource_id,
                    element.class_name,
                ]
            ).casefold()
            if normalized_reference in searchable:
                chosen = element
                break
    if chosen is None:
        point_keys = (
            ("end_point", "start_point")
            if action.type is ActionType.DRAG
            else ("point",)
            if action.type in {ActionType.CLICK_POINT, ActionType.LONG_PRESS}
            else ()
        )
        for key in point_keys:
            point = action.parameters.get(key)
            if not isinstance(point, (list, tuple)) or len(point) != 2:
                continue
            x, y = point
            chosen = next(
                (
                    element
                    for element in candidates
                    if element.bounds[0] <= x <= element.bounds[2]
                    and element.bounds[1] <= y <= element.bounds[3]
                ),
                None,
            )
            if chosen is not None:
                break
    if chosen is None and action.type is ActionType.TYPE_TEXT:
        editable = [element for element in candidates if element.editable]
        if len(editable) == 1:
            chosen = editable[0]
    if chosen is None:
        return None, reference or "UI Tree supplied no element supporting the candidate action"
    label = chosen.text or chosen.content_description or chosen.resource_id
    return {
        "label": label,
        "resource_id": chosen.resource_id,
        "class_name": chosen.class_name,
        "bounds": list(chosen.bounds),
    }, reference or f"coordinate/editable match: {label or chosen.class_name}"


def _task_grounded_recovery_action(
    action: Action,
    *,
    goal: str,
    active_subgoal: str,
    completed_subgoals: list[str],
) -> str:
    """Allow only a named-app fallback when Tree evidence is genuinely absent."""
    if action.type is not ActionType.OPEN_APP:
        return ""
    app_name = str(action.parameters.get("app_name", "")).strip().casefold()
    if len(app_name) < 3:
        return ""
    runtime_text = " | ".join(
        [goal, active_subgoal, *completed_subgoals]
    ).casefold()
    if app_name not in runtime_text:
        return ""
    return (
        f"UI Tree supplied insufficient new evidence; OPEN_APP[{app_name}] is "
        "instead grounded by the frozen task/subgoal state."
    )
