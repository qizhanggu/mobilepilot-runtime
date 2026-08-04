"""Small, auditable state machines for the AndroidWorld Agent runtime.

This module deliberately contains no model or device calls.  It makes progress,
loop, and recovery decisions independently testable instead of hiding them in
the main Agent loop.
"""

from __future__ import annotations

from dataclasses import dataclass, field
import hashlib
from typing import Any

from mobile_pilot.core import Action, ActionType


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

    def record_verification(self, *, changed: bool, action: Action) -> None:
        self.last_verifier = "screen_changed" if changed else "screen_unchanged"
        if changed:
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


@dataclass
class RecoveryController:
    """Permit one replan and retain the evidence needed to score its outcome."""

    used: bool = False
    active: RecoveryEpisode | None = None

    def begin(self, trigger: str, *, step: int, blocked_action: Action) -> RecoveryEpisode | None:
        if self.used:
            return None
        self.used = True
        self.active = RecoveryEpisode(1, trigger, step, blocked_action)
        return self.active

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
        if episode is None or not (reward > 0 or terminal):
            return None
        self.active = None
        return {
            "recovery_id": episode.recovery_id,
            "trigger": episode.trigger,
            "rescued": reward > 0 and episode.recovery_action_executed,
            "misfire": reward > 0 and not episode.recovery_action_executed,
            "official_reward": reward,
            "changed_action": episode.changed_action,
        }


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
