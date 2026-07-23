import json

from mobile_pilot.evaluation.screenspot.dataset import (
    build_integration_split,
    load_official_mobile,
)


def test_official_parser_uses_xywh_and_stable_ids(tmp_path):
    path = tmp_path / "mobile.json"
    path.write_text(
        json.dumps(
            [
                {
                    "img_filename": "a.png",
                    "bbox": [10, 20, 30, 40],
                    "instruction": "click a",
                    "data_type": "text",
                    "data_source": "android",
                }
            ]
        ),
        encoding="utf-8",
    )

    first = load_official_mobile(path, verify_sha256=False)
    second = load_official_mobile(path, verify_sha256=False)

    assert first[0].bbox_xyxy == (10, 20, 40, 60)
    assert first[0].sample_id == second[0].sample_id


def test_integration_split_is_deterministic_balanced_and_disjoint(tmp_path):
    rows = []
    for data_type in ("text", "icon"):
        for source in ("android", "ios", "shop"):
            for number in range(7):
                rows.append(
                    {
                        "img_filename": f"{data_type}-{source}-{number}.png",
                        "bbox": [number, number, 10, 10],
                        "instruction": f"click {data_type} {source} {number}",
                        "data_type": data_type,
                        "data_source": source,
                    }
                )
    path = tmp_path / "mobile.json"
    path.write_text(json.dumps(rows), encoding="utf-8")
    samples = load_official_mobile(path, verify_sha256=False)

    integration, held_out = build_integration_split(samples)
    integration_again, _ = build_integration_split(samples)

    assert len(integration) == 30
    assert len(held_out) == 12
    assert {sample.sample_id for sample in integration}.isdisjoint(
        sample.sample_id for sample in held_out
    )
    assert [sample.sample_id for sample in integration] == [
        sample.sample_id for sample in integration_again
    ]
    assert {sample.data_source for sample in integration} == {"android", "ios", "shop"}
    assert sum(sample.data_type == "text" for sample in integration) == 15
    assert sum(sample.data_type == "icon" for sample in integration) == 15
