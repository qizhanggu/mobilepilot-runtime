from types import SimpleNamespace

from PIL import Image

from mobile_pilot.core import ActionType, ErrorKind
from mobile_pilot.policy import GuiPlusRequest, GuiPlusVisionPolicy, parse_gui_plus_output


VALID_RESPONSE = '''Action: Click the visual-only button.
<tool_call>
{"name":"computer_use","arguments":{"action":"left_click","coordinate":[500,750]}}
</tool_call>'''


def test_gui_plus_parser_accepts_only_normalized_clicks():
    result = parse_gui_plus_output(VALID_RESPONSE)

    assert result.is_success
    assert result.action.type is ActionType.CLICK_POINT
    assert result.action.parameters == {"point": [500, 750]}


def test_gui_plus_parser_rejects_out_of_range_coordinates():
    result = parse_gui_plus_output(
        '<tool_call>{"name":"computer_use","arguments":{"action":"left_click","coordinate":[1001,20]}}</tool_call>'
    )

    assert result.error_kind is ErrorKind.PARSE_ERROR
    assert "within" in result.message


def test_gui_plus_parser_accepts_actual_noncanonical_gui_plus_click_shape():
    result = parse_gui_plus_output(
        '<tool_call>{"action": "left_click", "coordinate": [505, 333]}}</tool_call>'
    )

    assert result.is_success
    assert result.action.parameters == {"point": [505, 333]}


def test_gui_plus_parser_accepts_complete_json_when_closing_xml_tag_is_missing():
    result = parse_gui_plus_output(
        'Action: Click target.\n<tool_call>\n{"action":"left_click","coordinate":[500,250]}'
    )

    assert result.is_success
    assert result.action.parameters == {"point": [500, 250]}


def test_gui_plus_parser_accepts_actual_shorthand_with_optional_final_brace():
    for raw in ('left_click\n{"coordinate": [333, 340]', 'left_click\n{"coordinate": [333, 340]}'):
        result = parse_gui_plus_output(raw)
        assert result.is_success
        assert result.action.parameters == {"point": [333, 340]}


def test_gui_plus_parser_accepts_parameters_wrapper_without_closing_tag():
    result = parse_gui_plus_output(
        '<tool_call>\n{"type":"function","name":"computer_use","parameters":{"action":"left_click","coordinate":[505,391]}}'
    )

    assert result.is_success
    assert result.action.parameters == {"point": [505, 391]}


def test_gui_plus_parser_accepts_observed_reasoning_or_duplicate_marker_tail():
    for tail in ("</think>", "<tool_call>"):
        result = parse_gui_plus_output(
            'Action: click.\n<tool_call>\n{"action":"left_click","coordinate":[500,477]}}\n' + tail
        )
        assert result.is_success
        assert result.action.parameters == {"point": [500, 477]}


def test_gui_plus_policy_sends_image_without_exposing_key():
    captured = {}

    class FakeClient:
        class chat:
            class completions:
                @staticmethod
                def create(**kwargs):
                    captured.update(kwargs)
                    return SimpleNamespace(
                        choices=[SimpleNamespace(message=SimpleNamespace(content=VALID_RESPONSE))],
                        usage=SimpleNamespace(prompt_tokens=120, completion_tokens=8, total_tokens=128),
                    )

    def factory(**kwargs):
        captured["client_kwargs"] = kwargs
        return FakeClient()

    result = GuiPlusVisionPolicy(
        api_key="not-a-real-key",
        base_url="https://example.invalid/v1",
        client_factory=factory,
    ).decide(GuiPlusRequest("Click the visual-only button.", Image.new("RGB", (10, 20), "white")))

    assert result.is_success
    assert captured["client_kwargs"]["api_key"] == "not-a-real-key"
    image_url = captured["messages"][1]["content"][0]["image_url"]["url"]
    assert image_url.startswith("data:image/png;base64,")


def test_gui_plus_policy_records_usage_latency_and_list_price():
    class FakeClient:
        class chat:
            class completions:
                @staticmethod
                def create(**kwargs):
                    return SimpleNamespace(
                        choices=[SimpleNamespace(message=SimpleNamespace(content=VALID_RESPONSE))],
                        usage=SimpleNamespace(prompt_tokens=1_000_000, completion_tokens=1_000_000, total_tokens=2_000_000),
                    )

    decision = GuiPlusVisionPolicy(
        api_key="not-a-real-key",
        base_url="https://example.invalid/v1",
        client_factory=lambda **_: FakeClient(),
    ).decide_with_metrics(GuiPlusRequest("Click target.", Image.new("RGB", (10, 20), "white")))

    assert decision.result.is_success
    assert decision.metrics.total_tokens == 2_000_000
    assert decision.metrics.estimated_list_cost_cny == 6.0
    assert decision.metrics.latency_seconds >= 0
