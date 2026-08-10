"""Small, auditable state machines for the AndroidWorld Agent runtime.

This module deliberately contains no model or device calls.  It makes progress,
loop, and recovery decisions independently testable instead of hiding them in
the main Agent loop.
"""

from __future__ import annotations

from dataclasses import dataclass, field
import hashlib
from typing import Any, Iterable

from mobile_pilot.core import Action, ActionType
from mobile_pilot.perception import ScreenState
from mobile_pilot.androidworld.evaluation import is_official_success


SCREEN_EXACTLY_UNCHANGED = "exactly_unchanged"
SCREEN_VISUALLY_SIMILAR = "visually_similar"
SCREEN_MEANINGFUL_CHANGE = "meaningful_ui_change"
SCREEN_CONTEXT_CHANGE = "navigation_or_context_change"

COMPLETION_EVIDENCE_KINDS = frozenset(
    {"ui_text", "package_activity", "visual_state"}
)


@dataclass(frozen=True)
class CompletionEvidence:
    """Frozen completion evidence for one Actor-proposed subgoal."""

    kind: str
    value: str

    def __post_init__(self) -> None:
        if self.kind not in COMPLETION_EVIDENCE_KINDS:
            raise ValueError(f"unsupported completion evidence kind: {self.kind}")
        if not self.value.strip():
            raise ValueError("completion evidence value cannot be empty")

    def describe(self) -> str:
        return f"{self.kind}: {self.value}"


@dataclass
class SubgoalState:
    """One soft subgoal with a hard Runtime-owned lifecycle.

    The Actor proposes content.  Runtime freezes it until verification confirms
    completion or an explicit subgoal-level Recovery permits revision.
    """

    active_goal: str = ""
    active_evidence: CompletionEvidence | None = None
    completed_goals: list[str] = field(default_factory=list)
    revision_count: int = 0
    last_revision_reason: str = ""

    @property
    def active(self) -> bool:
        return bool(self.active_goal and self.active_evidence is not None)

    def accept_proposal(
        self,
        goal: str,
        evidence: CompletionEvidence,
        *,
        allow_revision: bool = False,
        revision_reason: str = "",
    ) -> str:
        goal = goal.strip()
        if not goal:
            raise ValueError("subgoal cannot be empty")
        if not self.active:
            self.active_goal = goal
            self.active_evidence = evidence
            return "accepted"
        if (
            self.active_goal.casefold() == goal.casefold()
            and self.active_evidence == evidence
        ):
            return "unchanged"
        if not allow_revision:
            return "mutation_blocked"
        self.active_goal = goal
        self.active_evidence = evidence
        self.revision_count += 1
        self.last_revision_reason = revision_reason
        return "revised"

    def confirm_active(self) -> str:
        if not self.active:
            return ""
        confirmed = self.active_goal
        self.completed_goals.append(confirmed)
        del self.completed_goals[:-6]
        self.active_goal = ""
        self.active_evidence = None
        return confirmed

    def snapshot(self) -> dict[str, Any]:
        return {
            "active_goal": self.active_goal,
            "active_evidence": (
                {
                    "kind": self.active_evidence.kind,
                    "value": self.active_evidence.value,
                }
                if self.active_evidence
                else None
            ),
            "completed_goals": list(self.completed_goals),
            "revision_count": self.revision_count,
            "last_revision_reason": self.last_revision_reason,
        }


@dataclass(frozen=True)
class CheckpointEvidence:
    """A stable success condition proposed by Planner and checked by Runtime."""

    kind: str
    value: str

    def describe(self) -> str:
        return f"{self.kind}: {self.value}"


@dataclass
class Checkpoint:
    goal: str
    evidence: CheckpointEvidence
    status: str = "pending"


@dataclass
class PlanState:
    """Explicit task progress; the Actor may propose, but cannot mark it done."""

    mode: str = "direct"
    reason: str = ""
    checkpoints: list[Checkpoint] = field(default_factory=list)
    revision_count: int = 0
    last_revision_reason: str = ""

    @classmethod
    def direct(cls, reason: str) -> "PlanState":
        return cls(mode="direct", reason=reason)

    @property
    def active(self) -> Checkpoint | None:
        return next((item for item in self.checkpoints if item.status == "active"), None)

    @property
    def is_complete(self) -> bool:
        return self.mode == "checklist" and bool(self.checkpoints) and all(
            item.status == "done" for item in self.checkpoints
        )

    def activate_first(self) -> None:
        if self.mode != "checklist" or self.active is not None:
            return
        first = next((item for item in self.checkpoints if item.status == "pending"), None)
        if first is not None:
            first.status = "active"

    def confirm_active(self) -> Checkpoint | None:
        current = self.active
        if current is None:
            return None
        current.status = "done"
        self.activate_first()
        return current

    def revise_remaining(
        self,
        checkpoints: Iterable[Checkpoint],
        *,
        reason: str,
    ) -> bool:
        """Replace only unfinished work; already-confirmed evidence is immutable."""
        replacements = list(checkpoints)
        if not replacements:
            return False
        done = [item for item in self.checkpoints if item.status == "done"]
        for item in replacements:
            item.status = "pending"
        self.mode = "checklist"
        self.reason = reason
        self.checkpoints = done + replacements
        self.revision_count += 1
        self.last_revision_reason = reason
        self.activate_first()
        return True

    def completed_goals(self) -> tuple[str, ...]:
        return tuple(item.goal for item in self.checkpoints if item.status == "done")

    def remaining_goals(self) -> tuple[str, ...]:
        return tuple(item.goal for item in self.checkpoints if item.status == "pending")


@dataclass
class RuntimeProgress:
    """Bounded short-term memory supplied to the Actor on every step."""

    completed: list[str] = field(default_factory=list)
    action_signatures: list[str] = field(default_factory=list)
    screen_fingerprints: list[str] = field(default_factory=list)
    last_verifier: str = ""
    recent_failure: str = ""
    current_subgoal: str = ""
    current_blocker: str = ""
    next_verification: str = ""
    unchanged_streak: int = 0

    def remember_screen(self, fingerprint: str) -> None:
        # The post-action state becomes the next step's pre-action state.  Do
        # not count that normal duplicate observation as a page revisit.
        if self.screen_fingerprints and self.screen_fingerprints[-1] == fingerprint:
            return
        self.screen_fingerprints.append(fingerprint)
        del self.screen_fingerprints[:-8]

    def prepare_action(self, action: Action) -> None:
        self.current_subgoal = (
            str(action.parameters.get("subgoal", "")).strip()
            or action.reason
            or action.type.value
        )
        self.next_verification = action.expected_outcome or default_expected_outcome(action)

    def record_execution(self, action: Action, *, executed: bool, message: str) -> None:
        if not executed:
            self.recent_failure = message
            self.current_blocker = message
            return
        self.completed.append(progress_summary(action))
        del self.completed[:-5]
        self.action_signatures.append(action_signature(action))
        del self.action_signatures[:-8]

    def record_verification(
        self,
        *,
        action: Action,
        changed: bool | None = None,
        result: str | None = None,
    ) -> None:
        # ``changed`` remains supported so frozen V2 behavior and its tests do
        # not move when V2.1 introduces richer progress signals.
        if result is None:
            result = "screen_changed" if changed else "screen_unchanged"
        self.last_verifier = result
        if result not in {"screen_unchanged", SCREEN_EXACTLY_UNCHANGED, SCREEN_VISUALLY_SIMILAR}:
            self.unchanged_streak = 0
            self.current_blocker = ""
            return
        self.unchanged_streak += 1
        self.current_blocker = f"screen remained unchanged after {action.type.value}"

    def candidate_loop_signal(self, candidate: Action) -> str:
        signature = action_signature(candidate)
        recent = self.action_signatures
        if len(recent) >= 2 and recent[-2:] == [signature, signature]:
            return "repeated_similar_action"
        if len(recent) >= 3 and recent[-3] == recent[-1] and recent[-2] == signature:
            return "alternating_action_loop"
        return ""

    def page_loop_signal(self, fingerprint: str) -> str:
        if self.unchanged_streak >= 2:
            return "two_consecutive_unchanged_screens"
        if self.screen_fingerprints[-5:].count(fingerprint) >= 2:
            return "revisited_same_screen"
        return ""


@dataclass
class RecoveryEpisode:
    recovery_id: int
    trigger: str
    trigger_step: int
    blocked_action: Action
    changed_action: bool | None = None
    replan_checked: bool = False
    recovery_action_executed: bool = False
    level: str = "action"


@dataclass
class RecoveryController:
    """Bound recovery and retain the evidence needed to score each attempt."""

    used: bool = False
    active: RecoveryEpisode | None = None
    max_attempts: int = 1
    attempts_started: int = 0
    secondary_level: str = "plan"

    def begin(self, trigger: str, *, step: int, blocked_action: Action) -> RecoveryEpisode | None:
        if self.attempts_started >= self.max_attempts:
            return None
        self.attempts_started += 1
        self.used = True
        level = "action" if self.attempts_started == 1 else self.secondary_level
        self.active = RecoveryEpisode(
            self.attempts_started,
            trigger,
            step,
            blocked_action,
            level=level,
        )
        return self.active

    @property
    def remaining(self) -> int:
        return max(0, self.max_attempts - self.attempts_started)

    def review_replan(self, candidate: Action) -> bool | None:
        episode = self.active
        if episode is None or episode.replan_checked:
            return None
        episode.replan_checked = True
        episode.changed_action = not actions_are_similar(candidate, episode.blocked_action)
        return episode.changed_action

    def mark_action_executed(self) -> None:
        if self.active is not None:
            self.active.recovery_action_executed = True

    def outcome(self, *, reward: float, terminal: bool) -> dict[str, Any] | None:
        episode = self.active
        full_success = is_official_success(reward)
        if episode is None or not (full_success or terminal):
            return None
        self.active = None
        return {
            "recovery_id": episode.recovery_id,
            "trigger": episode.trigger,
            "rescued": full_success and episode.recovery_action_executed,
            "misfire": full_success and not episode.recovery_action_executed,
            "official_reward": reward,
            "changed_action": episode.changed_action,
            "level": episode.level,
        }


def classify_screen_change(before: ScreenState, after: ScreenState) -> tuple[str, dict[str, Any]]:
    """Combine exact, visual, semantic and package signals without guessing success."""
    before_exact = before.exact_fingerprint or before.fingerprint
    after_exact = after.exact_fingerprint or after.fingerprint
    distance = visual_hamming_distance(before.visual_fingerprint, after.visual_fingerprint)
    details: dict[str, Any] = {
        "exact_match": before_exact == after_exact,
        "visual_hamming_distance": distance,
        "package_before": before.package_activity,
        "package_after": after.package_activity,
        "semantic_match": (
            before.semantic_fingerprint == after.semantic_fingerprint
            if before.semantic_fingerprint and after.semantic_fingerprint
            else None
        ),
    }
    if before_exact == after_exact:
        return SCREEN_EXACTLY_UNCHANGED, details
    if (
        before.package_activity
        and after.package_activity
        and before.package_activity != after.package_activity
    ):
        return SCREEN_CONTEXT_CHANGE, details
    if distance is not None and distance <= 0.035:
        return SCREEN_VISUALLY_SIMILAR, details
    return SCREEN_MEANINGFUL_CHANGE, details


def visual_hamming_distance(before: str, after: str) -> float | None:
    if not before or not after or len(before) != len(after):
        return None
    try:
        differing = (int(before, 16) ^ int(after, 16)).bit_count()
    except ValueError:
        return None
    return differing / (len(before) * 4)


def checkpoint_evidence_matches(
    checkpoint: Checkpoint,
    screen: ScreenState,
) -> tuple[bool | None, str]:
    """Use deterministic evidence first; ``None`` means a VLM must judge it."""
    needle = checkpoint.evidence.value.strip().casefold()
    if not needle:
        return False, "checkpoint evidence is empty"
    if checkpoint.evidence.kind == "package_activity":
        package = screen.package_activity.casefold()
        short_name = needle.rsplit(".", 1)[-1].rsplit("/", 1)[-1]
        matched = needle in package or (len(short_name) >= 4 and short_name in package)
        return matched, f"package/activity={screen.package_activity or 'unknown'}"
    if checkpoint.evidence.kind == "ui_text":
        if not screen.elements:
            return None, "UI Tree is required for deterministic evidence"
        haystacks = [
            " | ".join(
                [item.text, item.content_description, item.resource_id, item.class_name]
            ).casefold()
            for item in screen.elements
        ]
        matched = any(needle in value for value in haystacks)
        return matched, f"searched {len(haystacks)} UI elements for {checkpoint.evidence.value!r}"
    if checkpoint.evidence.kind in {"ui_state", "visual"}:
        return None, f"{checkpoint.evidence.kind} checkpoint requires constrained Verifier"
    return False, f"unsupported evidence kind: {checkpoint.evidence.kind}"


def completion_evidence_matches(
    evidence: CompletionEvidence,
    screen: ScreenState,
) -> tuple[bool | None, str]:
    """Check hard evidence first; ``None`` delegates visual semantics to VLM."""
    needle = evidence.value.strip().casefold()
    if evidence.kind == "package_activity":
        package = screen.package_activity.strip().casefold()
        short_name = needle.rsplit(".", 1)[-1].rsplit("/", 1)[-1]
        matched = bool(package) and (
            needle in package or (len(short_name) >= 4 and short_name in package)
        )
        return matched, f"package/activity={screen.package_activity or 'unknown'}"
    if evidence.kind == "ui_text":
        haystacks = list(screen.verification_texts)
        if not haystacks:
            haystacks = [
                " | ".join(
                    [item.text, item.content_description, item.resource_id, item.class_name]
                )
                for item in screen.elements
            ]
        if not haystacks:
            return None, "no deterministic UI text signal is available"
        matched = any(needle in value.casefold() for value in haystacks)
        return matched, f"searched {len(haystacks)} visible UI text records"
    if evidence.kind == "visual_state":
        return None, "visual_state requires the event-triggered VLM Verifier"
    return False, f"unsupported completion evidence kind: {evidence.kind}"


def progress_summary(action: Action) -> str:
    """Describe progress without copying typed user data into short-term memory."""
    if action.type is ActionType.TYPE_TEXT:
        return "TYPE_TEXT[text omitted]"
    if action.type is ActionType.OPEN_APP:
        return f"OPEN_APP[{action.parameters.get('app_name', '')}]"
    if action.type in {ActionType.SWIPE, ActionType.SCROLL}:
        return f"{action.type.value}[{action.parameters.get('direction', '')}]"
    if action.type is ActionType.CLICK_POINT:
        return f"CLICK_POINT[{_point_bucket(action)}]"
    return action.type.value


def default_expected_outcome(action: Action) -> str:
    expectations = {
        ActionType.CLICK_POINT: "the tapped control should visibly respond",
        ActionType.TYPE_TEXT: "the intended field should show the entered text",
        ActionType.SWIPE: "the visible page region should move",
        ActionType.SCROLL: "the visible page region should move",
        ActionType.PRESS_BACK: "the previous page or surface should appear",
        ActionType.OPEN_APP: "the requested app should become foreground",
        ActionType.WAIT: "the pending page transition should settle",
    }
    return expectations.get(action.type, "the next observation should confirm progress")


def action_signature(action: Action) -> str:
    if action.type is ActionType.TYPE_TEXT:
        text = str(action.parameters.get("text", ""))
        digest = hashlib.sha256(text.encode("utf-8")).hexdigest()[:10]
        return f"TYPE_TEXT:{digest}"
    if action.type is ActionType.OPEN_APP:
        return f"OPEN_APP:{str(action.parameters.get('app_name', '')).strip().lower()}"
    if action.type in {ActionType.SWIPE, ActionType.SCROLL}:
        return f"{action.type.value}:{action.parameters.get('direction', '')}"
    if action.type is ActionType.CLICK_POINT:
        return f"CLICK_POINT:{_point_bucket(action)}"
    return action.type.value


def actions_are_similar(candidate: Action, blocked: object) -> bool:
    return isinstance(blocked, Action) and action_signature(candidate) == action_signature(blocked)


def _point_bucket(action: Action) -> str:
    point = action.parameters.get("point", [])
    if not isinstance(point, (list, tuple)) or len(point) != 2:
        return "invalid"
    x, y = point
    if not isinstance(x, (int, float)) or not isinstance(y, (int, float)):
        return "invalid"
    return f"{round(x / 80)}:{round(y / 80)}"
