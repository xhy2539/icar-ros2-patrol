import json

import pytest

from app_control.command_parser import Motion, parse_command


def test_stop_is_always_zero():
    assert parse_command(json.dumps({"command": "stop", "speed": 1})) == Motion(0, 0, 0)


def test_json_speed_scales_and_clamps():
    assert parse_command('{"command":"forward","speed":0.5}', 0.4, 1.0) == Motion(0.2, 0, 0)
    assert parse_command('{"command":"turn_left","speed":9}', 0.4, 1.0) == Motion(0, 0, 1.0)


def test_motion_values_are_bounded():
    assert parse_command("motion:99:-99:99", 0.35, 1.2) == Motion(0.35, -0.35, 1.2)


def test_unknown_command_is_rejected():
    with pytest.raises(ValueError):
        parse_command("launch_missiles")
