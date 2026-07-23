"""ScreenSpot-v2 Mobile 的独立数据、评测与运行适配层。"""

from .dataset import (
    OFFICIAL_DATASET_COMMIT,
    OFFICIAL_MOBILE_JSON_SHA256,
    ScreenSpotSample,
    build_integration_split,
    load_official_mobile,
)
from .evaluator import point_in_bbox_xywh
from .preprocess import ImageVariant, apply_image_variant

__all__ = [
    "OFFICIAL_DATASET_COMMIT",
    "OFFICIAL_MOBILE_JSON_SHA256",
    "ImageVariant",
    "ScreenSpotSample",
    "apply_image_variant",
    "build_integration_split",
    "load_official_mobile",
    "point_in_bbox_xywh",
]
