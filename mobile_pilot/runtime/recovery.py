"""视觉 grounding 失败后的有限恢复：缩小视野并映射回完整屏幕。"""

from __future__ import annotations

from dataclasses import dataclass

from PIL import Image


@dataclass(frozen=True)
class VisionViewport:
    left: int
    top: int
    right: int
    bottom: int

    def __post_init__(self) -> None:
        if self.left < 0 or self.top < 0 or self.right <= self.left or self.bottom <= self.top:
            raise ValueError("Vision viewport bounds are invalid.")

    def crop(self, image: Image.Image) -> Image.Image:
        width, height = image.size
        if self.right > width or self.bottom > height:
            raise ValueError("Vision viewport exceeds the screenshot.")
        return image.crop((self.left, self.top, self.right, self.bottom))

    def normalized_to_screen(self, point: list[int] | tuple[int, int]) -> tuple[int, int]:
        if len(point) != 2 or not all(isinstance(value, (int, float)) for value in point):
            raise ValueError("Normalized point must contain two numeric values.")
        x, y = point
        if not (0 <= x <= 1000 and 0 <= y <= 1000):
            raise ValueError("Normalized point must be within [0, 1000].")
        return (
            self.left + int(x / 1000 * (self.right - self.left)),
            self.top + int(y / 1000 * (self.bottom - self.top)),
        )


def viewport_below(
    anchor_bounds: tuple[int, int, int, int],
    image_size: tuple[int, int],
    *,
    height: int,
) -> VisionViewport:
    """创建从锚点下边缘开始、横跨整屏的有限恢复视野。"""

    _, _, _, anchor_bottom = anchor_bounds
    image_width, image_height = image_size
    return VisionViewport(0, anchor_bottom, image_width, min(anchor_bottom + height, image_height))
