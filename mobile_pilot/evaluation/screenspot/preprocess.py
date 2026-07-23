"""ScreenSpot 图像预处理；所有变体保持原始图片尺寸。"""

from __future__ import annotations

from enum import Enum

from PIL import Image

from mobile_pilot.evaluation.visual_matrix import add_grid


class ImageVariant(str, Enum):
    RAW = "raw"
    GRID_10X10 = "grid_10x10"
    GRID_8X16 = "grid_8x16"
    GRID_10X20 = "grid_10x20"


GRID_DIMENSIONS = {
    ImageVariant.GRID_10X10: (10, 10),
    ImageVariant.GRID_8X16: (8, 16),
    ImageVariant.GRID_10X20: (10, 20),
}


def apply_image_variant(image: Image.Image, variant: ImageVariant) -> Image.Image:
    if variant is ImageVariant.RAW:
        return image.convert("RGB").copy()
    columns, rows = GRID_DIMENSIONS[variant]
    processed = add_grid(image, columns, rows)
    if processed.size != image.size:
        raise AssertionError("grid preprocessing must preserve image dimensions")
    return processed
