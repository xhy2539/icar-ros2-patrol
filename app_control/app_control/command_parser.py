"""Pure command parsing logic, kept independent from ROS for unit testing."""

import json
from dataclasses import dataclass


@dataclass(frozen=True)
class Motion:
    x: float
    y: float
    z: float


def _clamp(value: float, low: float, high: float) -> float:
    return max(low, min(high, value))


def parse_command(
    raw: str, max_linear: float = 0.35, max_angular: float = 1.2
) -> Motion:
    text = raw.strip()
    if not text:
        raise ValueError("empty command — send a text command or JSON with 'command'/'direction' field")

    speed = 0.5
    command = text.lower()
    if text.startswith("{"):
        data = json.loads(text)
        command = str(data.get("command", data.get("direction", ""))).lower()
        speed = _clamp(float(data.get("speed", speed)), 0.0, 1.0)

    if command.startswith("motion:"):
        parts = command.split(":")
        if len(parts) != 4:
            raise ValueError("motion requires x:y:z")
        return Motion(
            _clamp(float(parts[1]), -max_linear, max_linear),
            _clamp(float(parts[2]), -max_linear, max_linear),
            _clamp(float(parts[3]), -max_angular, max_angular),
        )

    linear = max_linear * speed
    angular = max_angular * speed
    commands = {
        "forward": Motion(linear, 0.0, 0.0),
        "backward": Motion(-linear, 0.0, 0.0),
        "left": Motion(0.0, linear, 0.0),
        "right": Motion(0.0, -linear, 0.0),
        "turn_left": Motion(0.0, 0.0, angular),
        "turn_right": Motion(0.0, 0.0, -angular),
        "stop": Motion(0.0, 0.0, 0.0),
    }
    if command not in commands:
        raise ValueError(f"unsupported command: {command}")
    return commands[command]
