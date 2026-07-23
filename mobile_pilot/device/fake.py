"""不依赖真机的设备适配器，用于 Runtime 和策略测试。"""

from PIL import Image

from mobile_pilot.core import Action, ActionResult, ActionType

from .base import DeviceAdapter
from .models import DeviceInfo, DeviceObservation


class FakeDeviceAdapter(DeviceAdapter):
    """返回预设观察值的最小 FakeDevice。"""

    def __init__(self, info: DeviceInfo, image: Image.Image, ui_xml: str | None = None):
        self._info = info
        self._image = image.copy()
        self._ui_xml = ui_xml
        self.taps: list[tuple[int, int]] = []
        self.typed_texts: list[str] = []

    def get_device_info(self) -> DeviceInfo:
        return self._info

    def observe(self, *, include_ui_tree: bool = False) -> DeviceObservation:
        return DeviceObservation(
            image=self._image.copy(),
            device_info=self._info,
            ui_xml=self._ui_xml if include_ui_tree else None,
            ui_tree_error=None if self._ui_xml or not include_ui_tree else "Fake UI XML was not configured",
        )

    def tap_point(self, x: int, y: int) -> ActionResult:
        self.taps.append((x, y))
        return ActionResult(
            executed=True,
            action=Action(ActionType.CLICK_POINT, {"point": [x, y]}, source="fake_device"),
            message="Fake tap recorded",
        )

    def type_text(self, text: str) -> ActionResult:
        if not text:
            raise ValueError("text is required")
        self.typed_texts.append(text)
        return ActionResult(
            executed=True,
            action=Action(ActionType.TYPE_TEXT, {"text": text}, source="fake_device"),
            message="Fake text input recorded",
        )
