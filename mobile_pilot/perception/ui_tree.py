"""Android UIAutomator XML 的最小、可解释解析器。"""

from __future__ import annotations

from dataclasses import dataclass
import hashlib
import re
import xml.etree.ElementTree as ET
from typing import Optional, Tuple


_BOUNDS_PATTERN = re.compile(r"\[(\d+),(\d+)\]\[(\d+),(\d+)\]")


@dataclass(frozen=True)
class UiElement:
    """一个可由 UI Tree 解释和定位的 Android 控件。"""

    stable_id: str
    resource_id: str
    text: str
    content_description: str
    class_name: str
    bounds: Tuple[int, int, int, int]
    clickable: bool
    enabled: bool
    editable: bool

    @property
    def center(self) -> Tuple[int, int]:
        left, top, right, bottom = self.bounds
        return ((left + right) // 2, (top + bottom) // 2)


def parse_ui_xml(raw_xml: str) -> list[UiElement]:
    """解析 XML，只保留可操作或带语义的节点。"""

    root = ET.fromstring(raw_xml)
    elements: list[UiElement] = []
    for index, node in enumerate(root.iter("node")):
        bounds = _parse_bounds(node.attrib.get("bounds", ""))
        if bounds is None:
            continue
        resource_id = node.attrib.get("resource-id", "")
        text = node.attrib.get("text", "")
        content_description = node.attrib.get("content-desc", "")
        clickable = node.attrib.get("clickable", "false") == "true"
        editable = node.attrib.get("editable", "false") == "true"
        if not (clickable or editable or resource_id or text or content_description):
            continue
        class_name = node.attrib.get("class", "")
        stable_source = "|".join(
            [resource_id, text, content_description, class_name, str(bounds), str(index)]
        )
        elements.append(
            UiElement(
                stable_id=hashlib.sha256(stable_source.encode("utf-8")).hexdigest()[:16],
                resource_id=resource_id,
                text=text,
                content_description=content_description,
                class_name=class_name,
                bounds=bounds,
                clickable=clickable,
                enabled=node.attrib.get("enabled", "true") == "true",
                editable=editable,
            )
        )
    return elements


def _parse_bounds(value: str) -> Optional[Tuple[int, int, int, int]]:
    match = _BOUNDS_PATTERN.fullmatch(value)
    if not match:
        return None
    left, top, right, bottom = (int(group) for group in match.groups())
    if right <= left or bottom <= top:
        return None
    return left, top, right, bottom
