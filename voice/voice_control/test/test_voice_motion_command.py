from voice_control.voice_motion_command import parse_voice_motion_command


def test_parse_forward_duration_from_assistant_task():
    command = parse_voice_motion_command("执行任务：前进一秒")

    assert command is not None
    assert command.direction == "forward"
    assert command.duration_sec == 1.0


def test_parse_turn_left_without_duration_uses_short_default():
    command = parse_voice_motion_command("执行任务：左转")

    assert command is not None
    assert command.direction == "turn_left"
    assert command.duration_sec == 1.0


def test_parse_stop_command():
    command = parse_voice_motion_command("执行任务：停止")

    assert command is not None
    assert command.direction == "stop"
    assert command.duration_sec == 0.0


def test_ignore_conversational_text():
    assert parse_voice_motion_command("您好呀，需要帮忙吗？") is None
