from mobile_pilot.evaluation.screenspot.evaluator import (
    normalized_to_pixel,
    point_in_bbox_xywh,
    summarize_records,
)
from mobile_pilot.evaluation.screenspot.statistics import paired_comparison


def test_point_in_xywh_bbox_counts_boundaries_and_rejects_outside():
    bbox = (10, 20, 30, 40)

    assert point_in_bbox_xywh((10, 20), bbox)
    assert point_in_bbox_xywh((40, 60), bbox)
    assert not point_in_bbox_xywh((41, 60), bbox)
    assert not point_in_bbox_xywh((40, 61), bbox)


def test_normalized_coordinate_maps_to_original_image_space():
    assert normalized_to_pixel([0, 0], (100, 200)) == (0, 0)
    assert normalized_to_pixel([500, 500], (100, 200)) == (50, 100)
    assert normalized_to_pixel([1000, 1000], (100, 200)) == (99, 199)


def test_summary_separates_text_icon_and_invalid_outputs():
    records = [
        {
            "config": "raw",
            "correct": True,
            "prediction_point": [1, 1],
            "model_call_count": 1,
            "prompt_tokens": 10,
            "completion_tokens": 2,
            "total_tokens": 12,
            "estimated_list_cost_cny": 0.1,
            "latency_seconds": 1.0,
            "failure_reason": "",
            "data_type": "text",
        },
        {
            "config": "raw",
            "correct": False,
            "prediction_point": None,
            "model_call_count": 1,
            "prompt_tokens": 10,
            "completion_tokens": 2,
            "total_tokens": 12,
            "estimated_list_cost_cny": 0.1,
            "latency_seconds": 3.0,
            "failure_reason": "invalid_model_output",
            "data_type": "icon",
        },
    ]

    summary = summarize_records(records)[0]

    assert summary["accuracy"] == 0.5
    assert summary["text_accuracy"] == 1.0
    assert summary["icon_accuracy"] == 0.0
    assert summary["invalid_output_rate"] == 0.5
    assert summary["mean_latency_seconds"] == 2.0


def test_paired_comparison_counts_outcomes_and_uses_exact_mcnemar():
    records = []
    outcomes = [(True, True)] * 3 + [(True, False)] + [(False, True)] * 5 + [(False, False)] * 2
    for index, (raw, grid) in enumerate(outcomes):
        records.extend(
            [
                {
                    "sample_id": f"sample-{index}",
                    "config": "raw__vision_only",
                    "correct": raw,
                },
                {
                    "sample_id": f"sample-{index}",
                    "config": "grid_10x10__vision_only",
                    "correct": grid,
                },
            ]
        )

    result = paired_comparison(records)

    assert result["samples"] == 11
    assert result["both_success"] == 3
    assert result["raw_only_success"] == 1
    assert result["grid_10x10_only_success"] == 5
    assert result["both_failed"] == 2
    assert result["accuracy_difference_grid_minus_raw"] == 4 / 11
    assert result["exact_mcnemar_two_sided_p_value"] == 0.21875
