from agent import Agent


def make_agent():
    return Agent.__new__(Agent)


def test_non_click_action_passes_through():
    action, params = make_agent()._post_process_coordinates(
        "TYPE", {"text": "coffee"}, ""
    )
    assert (action, params) == ("TYPE", {"text": "coffee"})


def test_edge_y_coordinate_is_clamped():
    action, params = make_agent()._post_process_coordinates(
        "CLICK", {"point": [100, 5]}, ""
    )
    assert action == "CLICK"
    assert params["point"] == [100, 30]


def test_thought_bounds_move_point_inside_estimated_element():
    raw = "Thought: (x1=100,y1=200)(x2=300,y2=400)"
    _, params = make_agent()._post_process_coordinates(
        "CLICK", {"point": [100, 200]}, raw
    )
    assert params["point"] == [103, 203]


def test_suspicious_center_uses_thought_coordinate_when_safer():
    raw = "Thought: target center x=900, y=80"
    _, params = make_agent()._post_process_coordinates(
        "CLICK", {"point": [500, 200]}, raw
    )
    assert params["point"] == [900, 80]

