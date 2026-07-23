from PIL import Image

from agent import Agent


def test_grid_overlay_preserves_size_and_returns_rgb():
    agent = Agent.__new__(Agent)
    original = Image.new("RGB", (100, 200), "white")

    processed = agent._preprocess_image(original)

    assert processed.size == original.size
    assert processed.mode == "RGB"
    assert processed.getpixel((10, 50)) != original.getpixel((10, 50))

