"""真实 Android 与可重复 Fake 设备的统一适配层。"""

from .adb import ADBDeviceAdapter, AdbCommandError, AdbDevice
from .base import DeviceAdapter
from .fake import FakeDeviceAdapter
from .models import DeviceInfo, DeviceObservation
from .uiautomator2 import Uiautomator2CommandError, Uiautomator2DeviceAdapter

__all__ = [
    "ADBDeviceAdapter",
    "AdbCommandError",
    "AdbDevice",
    "DeviceAdapter",
    "DeviceInfo",
    "DeviceObservation",
    "FakeDeviceAdapter",
    "Uiautomator2CommandError",
    "Uiautomator2DeviceAdapter",
]
