"""动作后的有限轮询 Verifier。"""

from __future__ import annotations

from dataclasses import dataclass
import time
from typing import Callable

from mobile_pilot.device import DeviceAdapter
from mobile_pilot.perception import ScreenState


@dataclass(frozen=True)
class VerificationResult:
    success: bool
    attempts: int
    reason: str
    state: ScreenState


class ScreenVerifier:
    """重复观察新页面，避免用一次可能陈旧的 UI dump 判定失败。"""

    def __init__(self, sleep: Callable[[float], None] = time.sleep):
        self._sleep = sleep

    def wait_for_text(
        self,
        adapter: DeviceAdapter,
        expected_text: str,
        *,
        max_attempts: int = 5,
        interval_seconds: float = 0.35,
    ) -> VerificationResult:
        if not expected_text:
            raise ValueError("expected_text is required")
        if max_attempts < 1:
            raise ValueError("max_attempts must be positive")

        last_state: ScreenState | None = None
        for attempt in range(1, max_attempts + 1):
            last_state = ScreenState.from_observation(adapter.observe(include_ui_tree=True))
            if any(element.text == expected_text for element in last_state.elements):
                return VerificationResult(True, attempt, f"Found expected text: {expected_text}", last_state)
            if attempt < max_attempts:
                self._sleep(interval_seconds)

        assert last_state is not None
        return VerificationResult(
            False,
            max_attempts,
            f"Expected text did not appear after {max_attempts} observations: {expected_text}",
            last_state,
        )
