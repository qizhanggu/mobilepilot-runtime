"""设备层的只读数据模型。"""

from dataclasses import dataclass
from typing import Optional, Tuple

from PIL import Image


@dataclass(frozen=True)
class DeviceInfo:
    """一次连接诊断得到的设备元数据。"""

    serial: str
    state: str
    manufacturer: str = ""
    model: str = ""
    android_version: str = ""
    physical_size: Optional[Tuple[int, int]] = None
    current_activity: str = ""


@dataclass
class DeviceObservation:
    """设备当前的只读观察结果。

    截图只保存在内存中；调用者决定是否脱敏并持久化。UI XML 会先尝试无文件
    流式读取，失败时使用随机临时文件读取后立即删除。
    """

    image: Image.Image
    device_info: DeviceInfo
    ui_xml: Optional[str] = None
    ui_tree_error: Optional[str] = None
