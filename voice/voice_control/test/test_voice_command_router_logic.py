from voice_control.voice_command_router_logic import command_from_assistant_result


def test_plain_assistant_confirmation_is_not_a_motion_command():
    assert command_from_assistant_result("将前进一秒，请确认是否执行") is None


def test_marked_motion_is_extracted_for_the_llm_router():
    assert command_from_assistant_result("执行任务：前进一秒。") == "前进一秒"
