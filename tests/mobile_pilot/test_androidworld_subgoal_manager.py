from types import SimpleNamespace

from PIL import Image

from mobile_pilot.androidworld.subgoal_manager import QwenSubgoalManager


class _FakeCompletions:
    def __init__(self, content):
        self.content = content
        self.requests = []

    def create(self, **request):
        self.requests.append(request)
        return SimpleNamespace(
            choices=[SimpleNamespace(message=SimpleNamespace(content=self.content))],
            usage=SimpleNamespace(
                prompt_tokens=80,
                completion_tokens=12,
                total_tokens=92,
            ),
        )


class _FakeClient:
    def __init__(self, completions):
        self.chat = SimpleNamespace(completions=completions)


def test_qwen_subgoal_manager_downgrades_ungrounded_package_to_visual_evidence():
    completions = _FakeCompletions(
        '{"subgoal":"open Messages","evidence":'
        '{"kind":"package_activity","value":"messages"},'
        '"reason":"the task starts in Messages"}'
    )
    manager = QwenSubgoalManager(
        api_key="test",
        base_url="https://example.invalid/v1",
        client_factory=lambda **_: _FakeClient(completions),
    )

    decision = manager.propose_with_metrics(
        image=Image.new("RGB", (20, 30), "white"),
        task_goal="reply to Alice in Messages",
        completed_subgoals=(),
        trigger="initial",
        package_activity="launcher",
        visible_ui_text=("Messages", "Camera"),
    )

    assert decision.is_success
    assert decision.subgoal == "open Messages"
    assert decision.evidence.kind == "visual_state"
    assert "open Messages" in decision.evidence.value
    assert "downgraded" in decision.message
    request = completions.requests[0]
    assert request["model"] == "qwen3.7-flash-2026-07-15"
    assert request["response_format"] == {"type": "json_object"}
    assert request["extra_body"] == {"enable_thinking": False}
    assert sum(
        item["type"] == "image_url"
        for item in request["messages"][1]["content"]
    ) == 1
    assert decision.metrics.estimated_list_cost_cny is not None


def test_qwen_subgoal_manager_keeps_package_evidence_grounded_by_runtime():
    completions = _FakeCompletions(
        '{"subgoal":"stay in Messages","evidence":'
        '{"kind":"package_activity","value":"com.example.messages"},'
        '"reason":"the package is supplied by Runtime"}'
    )
    manager = QwenSubgoalManager(
        api_key="test",
        base_url="https://example.invalid/v1",
        client_factory=lambda **_: _FakeClient(completions),
    )

    decision = manager.propose_with_metrics(
        image=Image.new("RGB", (20, 30), "white"),
        task_goal="reply in Messages",
        completed_subgoals=(),
        trigger="recovery_revision",
        package_activity="com.example.messages/.MainActivity",
    )

    assert decision.is_success
    assert decision.evidence.kind == "package_activity"
    assert decision.evidence.value == "com.example.messages"
    assert decision.message == ""


def test_qwen_subgoal_manager_fails_closed_on_invalid_evidence_kind():
    completions = _FakeCompletions(
        '{"subgoal":"the target button is visible","evidence":'
        '{"kind":"action","value":"button tapped"},"reason":"bad schema"}'
    )
    manager = QwenSubgoalManager(
        api_key="test",
        base_url="https://example.invalid/v1",
        client_factory=lambda **_: _FakeClient(completions),
    )

    decision = manager.propose_with_metrics(
        image=Image.new("RGB", (20, 30)),
        task_goal="open settings",
        completed_subgoals=(),
        trigger="initial",
    )

    assert not decision.is_success
    assert decision.evidence is None
    assert "unsupported completion evidence kind" in decision.message
