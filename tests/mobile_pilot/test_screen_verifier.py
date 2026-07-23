from PIL import Image

from mobile_pilot.device.fake import FakeDeviceAdapter
from mobile_pilot.device.models import DeviceInfo, DeviceObservation
from mobile_pilot.runtime import ScreenVerifier


class SequenceAdapter(FakeDeviceAdapter):
    def __init__(self, xml_sequence):
        super().__init__(
            DeviceInfo(serial="fake", state="device", current_activity="com.mobilepilot.lab/.MainActivity"),
            Image.new("RGB", (100, 200), "white"),
        )
        self._xml_sequence = list(xml_sequence)
        self._index = 0

    def observe(self, *, include_ui_tree=False):
        xml = self._xml_sequence[min(self._index, len(self._xml_sequence) - 1)]
        self._index += 1
        return DeviceObservation(
            image=self._image.copy(),
            device_info=self._info,
            ui_xml=xml if include_ui_tree else None,
        )


def xml_with_text(text):
    return (
        '<hierarchy><node resource-id="" text="' + text + '" content-desc="" '
        'class="android.widget.TextView" bounds="[0,0][100,50]" clickable="false" '
        'enabled="true" editable="false" /></hierarchy>'
    )


def test_verifier_recovers_from_one_stale_ui_tree_read():
    sleeps = []
    adapter = SequenceAdapter([xml_with_text("旧页面"), xml_with_text("视觉定位验证成功")])

    result = ScreenVerifier(sleep=sleeps.append).wait_for_text(
        adapter,
        "视觉定位验证成功",
        max_attempts=3,
        interval_seconds=0.1,
    )

    assert result.success
    assert result.attempts == 2
    assert sleeps == [0.1]


def test_verifier_reports_bounded_failure():
    result = ScreenVerifier(sleep=lambda _: None).wait_for_text(
        SequenceAdapter([xml_with_text("仍是旧页面")]),
        "不会出现",
        max_attempts=2,
    )

    assert not result.success
    assert result.attempts == 2
