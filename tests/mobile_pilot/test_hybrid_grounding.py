from types import SimpleNamespace

from PIL import Image
import pytest

from mobile_pilot.device.models import DeviceInfo, DeviceObservation
from mobile_pilot.perception import ScreenState
from mobile_pilot.policy import GroundingMode, HybridGrounder, LegacyVisionPolicy, SemanticTarget


def make_state() -> ScreenState:
    observation = DeviceObservation(
        image=Image.new("RGB", (1260, 2800), "white"),
        device_info=DeviceInfo(serial="fake", state="device", current_activity="com.mobilepilot.lab/.MainActivity"),
        ui_xml="""<hierarchy>
          <node resource-id="com.mobilepilot.lab:id/search_button" text="Search" content-desc="" class="android.widget.Button" bounds="[20,260][1240,360]" clickable="true" enabled="true" editable="false" />
        </hierarchy>""",
    )
    return ScreenState.from_observation(observation)


class FakeLegacyAgent:
    def __init__(self, output):
        self.output = output
        self.calls = 0

    def act(self, _agent_input):
        self.calls += 1
        return self.output


def test_hybrid_grounder_uses_ui_tree_without_calling_vision_policy():
    agent = FakeLegacyAgent(
        SimpleNamespace(action="CLICK", parameters={"point": [500, 500]}, raw_output="Action: CLICK | {}")
    )

    candidate = HybridGrounder().resolve(
        SemanticTarget(resource_id="com.mobilepilot.lab:id/search_button"),
        make_state(),
        vision_policy=LegacyVisionPolicy(agent),
        vision_input=object(),
    )

    assert candidate.source.value == "UI_TREE"
    assert agent.calls == 0


def test_hybrid_grounder_uses_legacy_vision_only_after_ui_tree_miss():
    agent = FakeLegacyAgent(
        SimpleNamespace(
            action="CLICK",
            parameters={"point": [500, 250]},
            raw_output='Action: CLICK | {"point": [500, 250]}',
        )
    )

    candidate = HybridGrounder().resolve(
        SemanticTarget(text="missing icon-only control"),
        make_state(),
        vision_policy=LegacyVisionPolicy(agent),
        vision_input=object(),
    )

    assert candidate.source.value == "VISION"
    assert candidate.point == (630, 700)
    assert agent.calls == 1


def test_hybrid_grounder_rejects_out_of_range_legacy_vision_point():
    agent = FakeLegacyAgent(
        SimpleNamespace(
            action="CLICK",
            parameters={"point": [1200, 10]},
            raw_output='Action: CLICK | {"point": [1200, 10]}',
        )
    )

    with pytest.raises(LookupError, match="outside"):
        HybridGrounder().resolve(
            SemanticTarget(text="missing"),
            make_state(),
            vision_policy=LegacyVisionPolicy(agent),
            vision_input=object(),
        )


def test_hybrid_grounder_preserves_invalid_visual_policy_reason():
    agent = FakeLegacyAgent(
        SimpleNamespace(action="COMPLETE", parameters={}, raw_output="Error: API timeout")
    )

    with pytest.raises(LookupError, match="invalid candidate") as exc_info:
        HybridGrounder().resolve(
            SemanticTarget(text="missing"),
            make_state(),
            vision_policy=LegacyVisionPolicy(agent),
            vision_input=object(),
        )

    assert exc_info.value.__cause__ is not None


@pytest.mark.parametrize("mode", [GroundingMode.VISION_ONLY, GroundingMode.VISION_WITH_TREE_AUX])
def test_visual_primary_modes_do_not_replace_visual_candidate_with_tree_match(mode):
    agent = FakeLegacyAgent(
        SimpleNamespace(
            action="CLICK",
            parameters={"point": [250, 500]},
            raw_output='Action: CLICK | {"point": [250, 500]}',
        )
    )
    grounder = HybridGrounder(mode=mode)

    candidate = grounder.resolve(
        SemanticTarget(resource_id="com.mobilepilot.lab:id/search_button"),
        make_state(),
        vision_policy=LegacyVisionPolicy(agent),
        vision_input=object(),
    )

    assert candidate.source.value == "VISION"
    assert candidate.point == (315, 1400)
    assert agent.calls == 1
    assert grounder.requires_ui_tree is (mode is GroundingMode.VISION_WITH_TREE_AUX)
