from PIL import Image

from mobile_pilot.core import Action, ActionType, ParseResult
from mobile_pilot.evaluation.screenspot.dataset import ScreenSpotSample
from mobile_pilot.evaluation.screenspot.preprocess import ImageVariant
from mobile_pilot.evaluation.screenspot.runner import ScreenSpotConfig, ScreenSpotRunner
from mobile_pilot.policy import GuiPlusDecision, VisionCallMetrics


class RecordingPolicy:
    def __init__(self):
        self.requests = []

    def decide_with_metrics(self, request):
        self.requests.append(request)
        return GuiPlusDecision(
            ParseResult(
                action=Action(
                    type=ActionType.CLICK_POINT,
                    parameters={"point": [500, 500]},
                    source="fake",
                ),
                raw_output="raw-response",
            ),
            VisionCallMetrics(
                model="fake-model",
                latency_seconds=0.25,
                prompt_tokens=10,
                completion_tokens=2,
                total_tokens=12,
                estimated_list_cost_cny=0.01,
            ),
        )


def test_runner_changes_only_image_preprocessing_and_keeps_audit_fields(tmp_path):
    image_path = tmp_path / "screen.png"
    Image.new("RGB", (100, 200), "white").save(image_path)
    sample = ScreenSpotSample(
        index=0,
        sample_id="sample-0",
        img_filename="screen.png",
        bbox_xywh=(40, 80, 20, 40),
        instruction="click the target",
        data_type="text",
        data_source="android",
        image_path=image_path,
        subset="integration_audit",
    )
    policy = RecordingPolicy()
    runner = ScreenSpotRunner(output_dir=tmp_path / "output", policy=policy, max_calls=2)

    records = runner.run(
        [sample],
        [
            ScreenSpotConfig("raw", ImageVariant.RAW),
            ScreenSpotConfig("grid", ImageVariant.GRID_10X10),
        ],
    )

    assert [request.instruction for request in policy.requests] == [
        "click the target",
        "click the target",
    ]
    assert policy.requests[0].image.getpixel((10, 20)) != policy.requests[1].image.getpixel((10, 20))
    assert all(record["correct"] for record in records)
    assert all(record["raw_model_response"] == "raw-response" for record in records)
    assert all(record["target_bbox_xywh"] == [40, 80, 20, 40] for record in records)
    assert all(record["prediction_point"] == [50, 100] for record in records)
