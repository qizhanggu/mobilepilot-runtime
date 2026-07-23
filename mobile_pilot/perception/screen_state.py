"""统一的 ScreenState：截图、设备元数据和语义 UI 元素。"""

from __future__ import annotations

from dataclasses import dataclass
import hashlib
import io
from typing import Optional

from mobile_pilot.device.models import DeviceObservation

from .ui_tree import UiElement, parse_ui_xml


@dataclass(frozen=True)
class ScreenState:
    image_size: tuple[int, int]
    package_activity: str
    elements: tuple[UiElement, ...]
    fingerprint: str
    ui_tree_error: Optional[str] = None

    @classmethod
    def from_observation(cls, observation: DeviceObservation) -> "ScreenState":
        elements = tuple(parse_ui_xml(observation.ui_xml)) if observation.ui_xml else ()
        image_bytes = io.BytesIO()
        observation.image.save(image_bytes, format="PNG")
        digest_input = "|".join(
            [
                observation.device_info.current_activity,
                str(observation.image.size),
                observation.ui_xml or "",
                hashlib.sha256(image_bytes.getvalue()).hexdigest(),
            ]
        )
        return cls(
            image_size=observation.image.size,
            package_activity=observation.device_info.current_activity,
            elements=elements,
            fingerprint=hashlib.sha256(digest_input.encode("utf-8")).hexdigest()[:24],
            ui_tree_error=observation.ui_tree_error,
        )
