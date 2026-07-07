from utils.output_parser import OutputParser


def test_parses_standard_click():
    action, params = OutputParser().parse(
        'Thought: target center\nAction: CLICK | {"point": [321, 654]}'
    )
    assert action == "CLICK"
    assert params == {"point": [321, 654]}


def test_parses_all_standard_non_click_actions():
    parser = OutputParser()
    cases = [
        ('Action: TYPE | {"text": "coffee"}', "TYPE", {"text": "coffee"}),
        (
            'Action: SCROLL | {"start_point": [500, 800], "end_point": [500, 300]}',
            "SCROLL",
            {"start_point": [500, 800], "end_point": [500, 300]},
        ),
        ('Action: OPEN | {"app_name": "美团"}', "OPEN", {"app_name": "美团"}),
        ('Action: COMPLETE | {}', "COMPLETE", {}),
    ]
    for raw, expected_action, expected_params in cases:
        assert parser.parse(raw) == (expected_action, expected_params)


def test_parses_base_class_syntax():
    assert OutputParser().parse("click(point='<point>120 340</point>')") == (
        "CLICK",
        {"point": [120, 340]},
    )


def test_repairs_single_quoted_json():
    assert OutputParser().parse("Action: OPEN | {'app_name': '美团'}") == (
        "OPEN",
        {"app_name": "美团"},
    )


def test_clamps_out_of_range_coordinates():
    assert OutputParser().parse('Action: CLICK | {"point": [-5, 1200]}') == (
        "CLICK",
        {"point": [0, 999]},
    )


def test_malformed_output_falls_back_to_complete():
    assert OutputParser().parse("I cannot decide what to do") == ("COMPLETE", {})

