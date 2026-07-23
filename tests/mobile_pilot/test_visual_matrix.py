from PIL import Image

from mobile_pilot.device import DeviceInfo, DeviceObservation
from mobile_pilot.evaluation.visual_matrix import (
    EXPERIMENT_CONFIGS,
    TASKS,
    EvaluationMode,
    _tree_auxiliary_check,
    _audited_task_success,
    add_grid,
    crop_around,
    normalized_to_pixels,
)
from mobile_pilot.perception import ScreenState


def test_visual_matrix_has_eight_tasks_seven_configs_and_explicit_modes():
    assert len(TASKS) == 8
    assert len(EXPERIMENT_CONFIGS) == 7
    assert {config.mode for config in EXPERIMENT_CONFIGS} == set(EvaluationMode)


def test_grid_and_crop_are_deterministic_without_mutating_source():
    source = Image.new("RGB", (100, 200), "white")
    grid = add_grid(source, 10, 10)

    assert source.getpixel((10, 10)) == (255, 255, 255)
    assert grid.getpixel((10, 10)) != source.getpixel((10, 10))
    assert crop_around((100, 200), (0, 0)) == (0, 0, 60, 90)
    assert normalized_to_pixels([500, 500], (100, 200)) == (50, 100)


def test_tree_aux_allows_expected_semantic_target_and_blocks_conflict():
    xml = """<hierarchy>
      <node resource-id="com.mobilepilot.lab:id/search_button" text="搜索" class="android.widget.Button" bounds="[0,50][100,100]" clickable="true" enabled="true" />
      <node resource-id="com.mobilepilot.lab:id/debug_dialog_button" text="弹窗" class="android.widget.Button" bounds="[0,100][100,150]" clickable="true" enabled="true" />
    </hierarchy>"""
    state = ScreenState.from_observation(DeviceObservation(
        image=Image.new("RGB", (100, 200), "white"),
        device_info=DeviceInfo(serial="fake", state="device"),
        ui_xml=xml,
    ))
    task = TASKS[1]

    assert _tree_auxiliary_check((50, 75), task, state) == (False, "")
    blocked, reason = _tree_auxiliary_check((50, 125), task, state)
    assert blocked is True
    assert "debug_dialog_button" in reason


def test_filter_verifier_false_negative_is_audited_without_rewriting_raw_result():
    row = {
        "task_id": "results_filter",
        "failure_reason": "post_action_screen_unchanged",
        "candidate_correct": True,
        "executed": True,
        "task_success": False,
    }

    assert _audited_task_success(row) is True
    assert row["task_success"] is False
