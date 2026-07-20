from PIL import Image

from mobile_pilot.device.adb import _parse_adb_devices, _parse_current_activity, _parse_physical_size
from mobile_pilot.device.fake import FakeDeviceAdapter
from mobile_pilot.device.models import DeviceInfo


def test_parses_ready_and_unauthorized_adb_devices():
    devices = _parse_adb_devices(
        "List of devices attached\n"
        "10CE8Q0P8U000B1 device product:V2352A model:V2352A\n"
        "emulator-5554 unauthorized transport_id:2\n"
    )

    assert [(device.serial, device.state) for device in devices] == [
        ("10CE8Q0P8U000B1", "device"),
        ("emulator-5554", "unauthorized"),
    ]


def test_parses_device_screen_and_activity_metadata():
    assert _parse_physical_size("Physical size: 1260x2800\n") == (1260, 2800)
    assert _parse_current_activity(
        "topResumedActivity=ActivityRecord{1 u0 com.example.lab/.HomeActivity t1}"
    ) == "com.example.lab/.HomeActivity"


def test_fake_device_observes_without_a_real_phone():
    info = DeviceInfo(serial="fake-1", state="device", physical_size=(100, 200))
    adapter = FakeDeviceAdapter(info, Image.new("RGB", (100, 200), "white"), "<hierarchy />")

    observation = adapter.observe(include_ui_tree=True)

    assert observation.device_info.serial == "fake-1"
    assert observation.image.size == (100, 200)
    assert observation.ui_xml == "<hierarchy />"
