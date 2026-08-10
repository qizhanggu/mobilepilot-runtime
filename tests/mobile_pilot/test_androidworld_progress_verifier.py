from types import SimpleNamespace

from PIL import Image

from mobile_pilot.androidworld.progress_verifier import QwenProgressVerifier


class _FakeCompletions:
    def __init__(self, content):
        self.content = content
        self.requests = []

    def create(self, **request):
        self.requests.append(request)
        return SimpleNamespace(
            choices=[SimpleNamespace(message=SimpleNamespace(content=self.content))],
            usage=SimpleNamespace(
                prompt_tokens=100,
                completion_tokens=10,
                total_tokens=110,
            ),
        )


class _FakeClient:
    def __init__(self, completions):
        self.chat = SimpleNamespace(completions=completions)


def test_qwen_progress_verifier_uses_two_images_non_thinking_and_json_output():
    completions = _FakeCompletions(
        '{"verdict":"progress","evidence":"editor opened",'
        '"disposition":"continue"}'
    )
    verifier = QwenProgressVerifier(
        api_key="test",
        base_url="https://example.invalid/v1",
        client_factory=lambda **_: _FakeClient(completions),
    )

    result = verifier.verify_with_metrics(
        before_image=Image.new("RGB", (20, 30), "white"),
        after_image=Image.new("RGB", (20, 30), "black"),
        action_summary="CLICK_POINT:1,1",
        task_goal="create a contact named Alice",
        subgoal="open editor",
        evidence_kind="visual_state",
        evidence_value="editor is visible",
        trigger="visual_state_progress_check",
        deterministic_signals={"screen_change": "meaningful_ui_change"},
    )

    assert result.verdict == "progress"
    request = completions.requests[0]
    assert request["model"] == "qwen3.7-flash-2026-07-15"
    assert request["extra_body"] == {"enable_thinking": False}
    assert request["response_format"] == {"type": "json_object"}
    content = request["messages"][1]["content"]
    assert sum(item["type"] == "image_url" for item in content) == 2
    context_text = content[-1]["text"]
    assert '"whole_task_goal": "create a contact named Alice"' in context_text
    assert '"frozen_subgoal": "open editor"' in context_text
    assert result.metrics.estimated_list_cost_cny is not None


def test_progress_verifier_fails_closed_on_invalid_completed_disposition():
    completions = _FakeCompletions(
        '{"verdict":"completed","evidence":"looks done",'
        '"disposition":"continue"}'
    )
    verifier = QwenProgressVerifier(
        api_key="test",
        base_url="https://example.invalid/v1",
        client_factory=lambda **_: _FakeClient(completions),
    )

    result = verifier.verify_with_metrics(
        before_image=Image.new("RGB", (20, 30)),
        after_image=Image.new("RGB", (20, 30)),
        action_summary="WAIT",
        task_goal="wait until the page is ready, then continue",
        subgoal="wait",
        evidence_kind="visual_state",
        evidence_value="page is ready",
        trigger="actor_proposed_subgoal_complete",
        deterministic_signals={},
    )

    assert result.verdict == "uncertain"
    assert result.disposition == "reobserve"
    assert "must confirm_subgoal" in result.message
