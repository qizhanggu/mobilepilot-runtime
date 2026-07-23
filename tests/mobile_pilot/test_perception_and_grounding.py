from PIL import Image
import pytest

from mobile_pilot.device.models import DeviceInfo, DeviceObservation
from mobile_pilot.perception import ScreenState, parse_ui_xml
from mobile_pilot.policy import Grounder, GroundingSource, PointTarget, SemanticTarget


UI_XML = """<?xml version='1.0' encoding='UTF-8'?>
<hierarchy>
  <node resource-id="com.mobilepilot.lab:id/search_input" text="" content-desc="搜索关键词输入框" class="android.widget.EditText" bounds="[20,120][1240,240]" clickable="true" enabled="true" editable="true" />
  <node resource-id="com.mobilepilot.lab:id/search_button" text="搜索" content-desc="执行本地搜索" class="android.widget.Button" bounds="[20,260][1240,360]" clickable="true" enabled="true" editable="false" />
</hierarchy>"""


def make_state() -> ScreenState:
    observation = DeviceObservation(
        image=Image.new("RGB", (1260, 2800), "white"),
        device_info=DeviceInfo(serial="fake", state="device", current_activity="com.mobilepilot.lab/.MainActivity"),
        ui_xml=UI_XML,
    )
    return ScreenState.from_observation(observation)


def test_ui_xml_parser_exposes_semantic_elements_and_centers():
    elements = parse_ui_xml(UI_XML)

    assert len(elements) == 2
    assert elements[1].resource_id.endswith("search_button")
    assert elements[1].center == (630, 310)


def test_grounder_prefers_resource_id_over_other_signals():
    candidate = Grounder().resolve(
        SemanticTarget(resource_id="com.mobilepilot.lab:id/search_button", text="错误文本"),
        make_state(),
    )

    assert candidate.source is GroundingSource.UI_TREE
    assert candidate.point == (630, 310)
    assert candidate.confidence == 0.99


def test_grounder_keeps_visual_fallback_explicit():
    candidate = Grounder().resolve(
        PointTarget(point=(500, 800), source=GroundingSource.VISION, reason="Icon is absent from UI Tree."),
        make_state(),
    )

    assert candidate.source is GroundingSource.VISION
    assert candidate.point == (500, 800)


def test_missing_semantic_target_requires_explicit_fallback():
    with pytest.raises(LookupError, match="visual fallback"):
        Grounder().resolve(SemanticTarget(text="不存在"), make_state())
