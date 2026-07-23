"""按需使用 uiautomator2 的 Android DeviceAdapter。"""

from __future__ import annotations

from typing import Any

from PIL import Image

from mobile_pilot.core import Action, ActionResult, ActionType

from .base import DeviceAdapter
from .models import DeviceInfo, DeviceObservation


class Uiautomator2CommandError(RuntimeError):
    """uiautomator2 无法完成设备操作。"""


class Uiautomator2DeviceAdapter(DeviceAdapter):
    """为 Unicode 输入、控件等待和按需 UI Tree 提供补充能力。

    截图始终获取；只有 ``include_ui_tree=True`` 时才读取 hierarchy。Runtime
    不应因为使用该 Adapter 就把 UI Tree 变成视觉策略的强制前置条件。
    """

    def __init__(self, serial: str, *, client: Any | None = None):
        if not serial:
            raise ValueError("serial is required; refusing to target an implicit device")
        self.serial = serial
        if client is None:
            try:
                import uiautomator2 as u2
            except ImportError as exc:
                raise Uiautomator2CommandError(
                    "uiautomator2 is not installed; install the optional device dependency first"
                ) from exc
            client = u2.connect(serial)
        self._client = client

    def get_device_info(self) -> DeviceInfo:
        try:
            info = self._client.info
            device_info = self._client.device_info
            current = self._client.app_current()
            size = self._client.window_size()
        except Exception as exc:
            raise Uiautomator2CommandError(f"failed to read device info: {exc}") from exc

        return DeviceInfo(
            serial=self.serial,
            state="device",
            manufacturer=str(device_info.get("brand", "")),
            model=str(device_info.get("model", info.get("productName", ""))),
            android_version=str(device_info.get("version", "")),
            physical_size=(int(size[0]), int(size[1])),
            current_activity=_format_activity(current),
        )

    def observe(self, *, include_ui_tree: bool = False) -> DeviceObservation:
        info = self.get_device_info()
        try:
            screenshot = self._client.screenshot(format="pillow")
            if not isinstance(screenshot, Image.Image):
                raise TypeError(f"unexpected screenshot type: {type(screenshot).__name__}")
            image = screenshot.copy()
        except Exception as exc:
            raise Uiautomator2CommandError(f"failed to capture screenshot: {exc}") from exc

        ui_xml = None
        ui_tree_error = None
        if include_ui_tree:
            try:
                ui_xml = self._client.dump_hierarchy(compressed=False)
            except Exception as exc:
                ui_tree_error = f"uiautomator2 hierarchy failed: {exc}"

        return DeviceObservation(
            image=image,
            device_info=info,
            ui_xml=ui_xml,
            ui_tree_error=ui_tree_error,
        )

    def tap_point(self, x: int, y: int) -> ActionResult:
        if x < 0 or y < 0:
            raise ValueError("tap coordinates must be non-negative")
        action = Action(ActionType.CLICK_POINT, {"point": [x, y]}, source="uiautomator2")
        try:
            result = self._client.click(x, y)
        except Exception as exc:
            raise Uiautomator2CommandError(f"coordinate click failed: {exc}") from exc
        if result is False:
            raise Uiautomator2CommandError("coordinate click returned false")
        return ActionResult(
            executed=True,
            action=action,
            message="uiautomator2 coordinate click completed",
            details={"serial": self.serial},
        )

    def type_text(self, text: str) -> ActionResult:
        if not text:
            raise ValueError("text is required")
        action = Action(ActionType.TYPE_TEXT, {"text": text}, source="uiautomator2")
        try:
            focused = self._client(focused=True)
            if not focused.exists(timeout=1.0):
                raise Uiautomator2CommandError("no focused editable element was found")
            focused.set_text(text)
        except Uiautomator2CommandError:
            raise
        except Exception as exc:
            raise Uiautomator2CommandError(f"Unicode text input failed: {exc}") from exc
        return ActionResult(
            executed=True,
            action=action,
            message="uiautomator2 Unicode text input completed",
            details={"serial": self.serial},
        )


def _format_activity(current: Any) -> str:
    if not isinstance(current, dict):
        return ""
    package = current.get("package") or ""
    activity = current.get("activity") or ""
    if not package:
        return str(activity)
    if str(activity).startswith("."):
        return f"{package}/{activity}"
    return f"{package}/{activity}" if activity else str(package)
