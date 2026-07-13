from llm_gateway.complex_task import (
    ComplexTaskRunner,
    build_rule_plan,
    normalize_plan_steps,
)


def test_rule_plan_waits_for_patrol_before_audio_and_query():
    call = build_rule_plan(
        "巡检 A、B 点，完成后播放完成提示音，然后查询视觉",
        ["A", "B", "C"],
    )
    assert call["tool_name"] == "execute_plan"
    steps = call["arguments"]["steps"]
    assert [step["tool_name"] for step in steps] == [
        "start_patrol",
        "play_audio",
        "query_vision",
    ]
    assert steps[0]["wait_for"] == "task_completed"


def test_runner_continues_only_after_patrol_completed():
    runner = ComplexTaskRunner()
    first = runner.start(
        [
            {"tool_name": "start_patrol", "arguments": {"route": ["A"]}},
            {"tool_name": "check_safety", "arguments": {}},
        ]
    )
    assert first.tool_name == "start_patrol"
    assert runner.record_result(True) is None
    assert runner.state == "WAITING"
    assert runner.on_task_status("NAVIGATING") is None
    second = runner.on_task_status("COMPLETED")
    assert second.tool_name == "check_safety"
    assert runner.record_result(True) is None
    assert runner.state == "COMPLETED"


def test_runner_aborts_remaining_steps_when_patrol_fails():
    runner = ComplexTaskRunner()
    runner.start(
        [
            {"tool_name": "start_patrol", "arguments": {"route": ["A"]}},
            {"tool_name": "play_audio", "arguments": {"name": "complete"}},
        ]
    )
    runner.record_result(True)
    assert runner.on_task_status("FAILED") is None
    assert runner.state == "FAILED"


def test_plan_rejects_direct_or_recursive_tools():
    try:
        normalize_plan_steps([{"tool_name": "execute_plan", "arguments": {}}])
    except ValueError as exc:
        assert "unsupported" in str(exc)
    else:
        raise AssertionError("recursive plan should be rejected")
