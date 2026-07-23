from PIL import Image

from mobile_pilot.device import Uiautomator2DeviceAdapter


class FakeUiObject:
    def __init__(self):
        self.text = ""

    def exists(self, timeout=0):
        return True

    def set_text(self, text):
        self.text = text


class FakeU2Client:
    info = {"productName": "fake", "displayWidth": 100, "displayHeight": 200}
    device_info = {"brand": "brand", "model": "model", "version": "16"}

    def __init__(self):
        self.focused = FakeUiObject()
        self.clicks = []
        self.dump_calls = 0

    def app_current(self):
        return {"package": "com.mobilepilot.lab", "activity": ".MainActivity"}

    def window_size(self):
        return (100, 200)

    def screenshot(self, format="pillow"):
        return Image.new("RGB", (100, 200), "white")

    def dump_hierarchy(self, compressed=False):
        self.dump_calls += 1
        return "<hierarchy />"

    def click(self, x, y):
        self.clicks.append((x, y))
        return True

    def __call__(self, **kwargs):
        assert kwargs == {"focused": True}
        return self.focused


def test_uiautomator2_tree_is_strictly_opt_in():
    client = FakeU2Client()
    adapter = Uiautomator2DeviceAdapter("serial", client=client)

    without_tree = adapter.observe()
    with_tree = adapter.observe(include_ui_tree=True)

    assert without_tree.ui_xml is None
    assert with_tree.ui_xml == "<hierarchy />"
    assert client.dump_calls == 1


def test_uiautomator2_unicode_input_and_click_use_adapter_boundary():
    client = FakeU2Client()
    adapter = Uiautomator2DeviceAdapter("serial", client=client)

    typed = adapter.type_text("咖啡")
    clicked = adapter.tap_point(10, 20)

    assert typed.executed is True
    assert client.focused.text == "咖啡"
    assert clicked.executed is True
    assert client.clicks == [(10, 20)]
