"""设备适配器的稳定、只读接口。"""

from abc import ABC, abstractmethod

from .models import DeviceInfo, DeviceObservation


class DeviceAdapter(ABC):
    """运行时使用的设备抽象。

    Phase 1 只开放观察接口。点击、输入、Intent 等有状态动作会在获得针对性
    用户确认后，随统一安全策略一起加入此接口。
    """

    @abstractmethod
    def get_device_info(self) -> DeviceInfo:
        """返回已连接设备的当前只读元数据。"""

    @abstractmethod
    def observe(self, *, include_ui_tree: bool = False) -> DeviceObservation:
        """在内存中获取截图，并可选尝试获取 UI Tree。"""
