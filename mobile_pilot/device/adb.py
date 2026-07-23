"""基于 ADB 的真实 Android 只读适配器。"""

from __future__ import annotations

from dataclasses import dataclass
import io
import re
import subprocess
import uuid
from pathlib import Path
from typing import Iterable, List, Optional, Sequence, Tuple

from PIL import Image

from mobile_pilot.core import Action, ActionResult, ActionType

from .base import DeviceAdapter
from .models import DeviceInfo, DeviceObservation


class AdbCommandError(RuntimeError):
    """ADB 命令无法完成时抛出的明确错误。"""


@dataclass(frozen=True)
class AdbDevice:
    """``adb devices -l`` 中的一条设备记录。"""

    serial: str
    state: str
    details: str = ""


class ADBDeviceAdapter(DeviceAdapter):
    """只读 ADB Adapter。

    所有命令都显式携带 ``-s <serial>``。``tap_point`` 仅执行已经由上层策略、
    Safety Gate 和用户授权批准的坐标点击；它不包含任何自动决策逻辑。
    """

    def __init__(self, serial: str, adb_path: str | Path = r"D:\Android\platform-tools\adb.exe"):
        if not serial:
            raise ValueError("serial is required; refusing to target an implicit device")
        self.serial = serial
        self.adb_path = Path(adb_path)

    @staticmethod
    def list_devices(adb_path: str | Path = r"D:\Android\platform-tools\adb.exe") -> List[AdbDevice]:
        """列出 ADB 可见设备，不改变设备状态。"""

        path = Path(adb_path)
        completed = subprocess.run(
            [str(path), "devices", "-l"],
            capture_output=True,
            check=False,
        )
        if completed.returncode != 0:
            raise AdbCommandError(_decode_error(completed))
        return _parse_adb_devices(_decode(completed.stdout))

    def get_device_info(self) -> DeviceInfo:
        """读取设备、系统、分辨率与当前前台 Activity。"""

        state = self._text("get-state").strip()
        if state != "device":
            raise AdbCommandError(f"device {self.serial!r} is not ready: {state or 'unknown'}")

        manufacturer = self._text("shell", "getprop", "ro.product.manufacturer").strip()
        model = self._text("shell", "getprop", "ro.product.model").strip()
        android_version = self._text("shell", "getprop", "ro.build.version.release").strip()
        size = _parse_physical_size(self._text("shell", "wm", "size"))
        activity = _parse_current_activity(
            self._text("shell", "dumpsys", "activity", "activities")
        )
        return DeviceInfo(
            serial=self.serial,
            state=state,
            manufacturer=manufacturer,
            model=model,
            android_version=android_version,
            physical_size=size,
            current_activity=activity,
        )

    def observe(self, *, include_ui_tree: bool = False) -> DeviceObservation:
        """把截图读取到内存；不在电脑或手机上持久化截图。"""

        info = self.get_device_info()
        screenshot = self._bytes("exec-out", "screencap", "-p")
        try:
            image = Image.open(io.BytesIO(screenshot))
            image.load()
        except Exception as exc:  # Pillow 会提供具体解码原因
            raise AdbCommandError(f"failed to decode in-memory screenshot: {exc}") from exc

        ui_xml = None
        ui_tree_error = None
        if include_ui_tree:
            ui_xml, ui_tree_error = self._stream_ui_xml()

        return DeviceObservation(
            image=image,
            device_info=info,
            ui_xml=ui_xml,
            ui_tree_error=ui_tree_error,
        )

    def tap_point(self, x: int, y: int) -> ActionResult:
        """点击已验证的真实屏幕坐标；调用方负责安全审批。"""

        if x < 0 or y < 0:
            raise ValueError("tap coordinates must be non-negative")
        action = Action(
            type=ActionType.CLICK_POINT,
            parameters={"point": [x, y]},
            source="adb_input",
        )
        self._run("shell", "input", "tap", str(x), str(y))
        return ActionResult(
            executed=True,
            action=action,
            message="ADB input tap completed",
            details={"serial": self.serial},
        )

    def type_text(self, text: str) -> ActionResult:
        """使用 Android ``input text`` 输入文本；调用方负责先聚焦目标输入框。"""

        if not text:
            raise ValueError("text is required")
        action = Action(
            type=ActionType.TYPE_TEXT,
            parameters={"text": text},
            source="adb_input",
        )
        adb_text = text.replace(" ", "%s")
        self._run("shell", "input", "text", adb_text)
        return ActionResult(
            executed=True,
            action=action,
            message="ADB input text completed",
            details={"serial": self.serial},
        )

    def _stream_ui_xml(self) -> tuple[Optional[str], Optional[str]]:
        """读取 UI XML，并保证临时设备文件在读取后立即删除。"""

        response = self._text("shell", "uiautomator", "dump", "/dev/tty")
        xml_start = response.find("<?xml")
        if xml_start >= 0:
            return response[xml_start:], None

        stream_message = " ".join(response.split()) or "no output"
        temp_path = f"/data/local/tmp/mobilepilot-ui-{uuid.uuid4().hex}.xml"
        try:
            self._text("shell", "uiautomator", "dump", temp_path)
            xml = self._text("exec-out", "cat", temp_path)
            xml_start = xml.find("<?xml")
            if xml_start >= 0:
                return xml[xml_start:], None
            compact = " ".join(xml.split()) or "no XML content"
            return None, f"temporary UI XML read failed: {compact}; stream: {stream_message}"
        except AdbCommandError as exc:
            return None, f"temporary UI XML dump failed: {exc}; stream: {stream_message}"
        finally:
            try:
                self._run("shell", "rm", "-f", temp_path)
            except AdbCommandError:
                pass

    def _text(self, *args: str) -> str:
        return _decode(self._run(*args).stdout)

    def _bytes(self, *args: str) -> bytes:
        return self._run(*args).stdout

    def _run(self, *args: str) -> subprocess.CompletedProcess[bytes]:
        if not self.adb_path.is_file():
            raise AdbCommandError(f"ADB executable not found: {self.adb_path}")
        completed = subprocess.run(
            [str(self.adb_path), "-s", self.serial, *args],
            capture_output=True,
            check=False,
        )
        if completed.returncode != 0:
            raise AdbCommandError(_decode_error(completed))
        return completed


def _parse_adb_devices(output: str) -> List[AdbDevice]:
    devices: List[AdbDevice] = []
    for line in output.splitlines():
        stripped = line.strip()
        if not stripped or stripped.startswith("List of devices") or stripped.startswith("*"):
            continue
        parts = stripped.split(maxsplit=2)
        if len(parts) >= 2:
            devices.append(AdbDevice(serial=parts[0], state=parts[1], details=parts[2] if len(parts) == 3 else ""))
    return devices


def _parse_physical_size(output: str) -> Optional[Tuple[int, int]]:
    match = re.search(r"Physical size:\s*(\d+)x(\d+)", output)
    return (int(match.group(1)), int(match.group(2))) if match else None


def _parse_current_activity(output: str) -> str:
    for pattern in (r"topResumedActivity=.*?\s([\w.$]+/[\w.$]+)", r"mResumedActivity:.*?\s([\w.$]+/[\w.$]+)"):
        match = re.search(pattern, output)
        if match:
            return match.group(1)
    return ""


def _decode(value: bytes) -> str:
    return value.decode("utf-8", errors="replace")


def _decode_error(completed: subprocess.CompletedProcess[bytes]) -> str:
    stderr = _decode(completed.stderr).strip()
    stdout = _decode(completed.stdout).strip()
    return stderr or stdout or f"ADB exited with code {completed.returncode}"
