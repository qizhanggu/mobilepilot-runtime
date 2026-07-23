from PIL import Image
import pytest

from mobile_pilot.runtime import VisionViewport, viewport_below


def test_viewport_maps_crop_coordinates_back_to_full_screen():
    viewport = VisionViewport(0, 1000, 1260, 1600)

    assert viewport.normalized_to_screen([500, 250]) == (630, 1150)
    assert viewport.crop(Image.new("RGB", (1260, 2800))).size == (1260, 600)


def test_viewport_below_starts_after_semantic_anchor():
    viewport = viewport_below((70, 1015, 1190, 1183), (1260, 2800), height=600)

    assert viewport == VisionViewport(0, 1183, 1260, 1783)


def test_viewport_rejects_out_of_range_model_point():
    with pytest.raises(ValueError, match="within"):
        VisionViewport(0, 1000, 1260, 1600).normalized_to_screen([500, 1001])
