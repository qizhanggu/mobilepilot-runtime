import json

import pytest

from mobile_pilot.runtime import compile_lab_search_task
from mobile_pilot.tracing import JsonlTraceWriter


def test_compiler_extracts_keyword_and_stops_before_submit():
    steps = compile_lab_search_task(
        "在 MobilePilot Lab 搜索 coffee，筛选评分 4.5 以上，进入确认页并停下，不要提交。"
    )

    assert [step.name for step in steps] == [
        "focus_search",
        "type_keyword",
        "run_search",
        "apply_filter",
        "open_confirmation",
    ]
    assert steps[1].text == "coffee"
    assert all("submit" not in step.name for step in steps)


def test_compiler_rejects_instruction_without_explicit_stop():
    with pytest.raises(ValueError, match="stop before submission"):
        compile_lab_search_task("在 MobilePilot Lab 搜索 coffee，筛选评分 4.5 以上，进入确认页。")


def test_jsonl_trace_redacts_secret_fields(tmp_path):
    path = tmp_path / "trace.jsonl"
    writer = JsonlTraceWriter(path, run_id="test-run")

    writer.write("model_call", api_key="secret-value", nested={"authorization": "bearer"}, ok=True)

    record = json.loads(path.read_text(encoding="utf-8"))
    assert record["api_key"] == "[REDACTED]"
    assert record["nested"]["authorization"] == "[REDACTED]"
    assert record["ok"] is True
