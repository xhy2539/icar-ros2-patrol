from llm_gateway.tool_intent import parse_tool_intent


def test_emergency_stop_is_local_fast_path():
    result = parse_tool_intent("立即停下")
    assert result["tool_name"] == "stop_robot"


def test_patrol_route_is_extracted_without_duplicates():
    result = parse_tool_intent("巡检 A、B、A、C 三个点")
    assert result["tool_name"] == "start_patrol"
    assert result["arguments"]["route"] == ["A", "B", "C"]


def test_tracking_start_and_stop_are_distinct():
    start = parse_tool_intent("跟踪前面的人")
    stop = parse_tool_intent("停止跟踪")
    assert start["tool_name"] == "start_tracking"
    assert start["arguments"]["target_classes"] == ["person"]
    assert stop["tool_name"] == "stop_tracking"


def test_unknown_text_is_left_for_model():
    assert parse_tool_intent("今天天气怎么样") is None
