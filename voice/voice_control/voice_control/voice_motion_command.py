"""Parse short assistant-authorized motion commands."""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Optional


CONTROL_PREFIX = "执行任务："


@dataclass(frozen=True)
class VoiceMotionCommand:
    direction: str
    duration_sec: float


_DIRECTIONS = (
    ("前进", "forward"),
    ("向前", "forward"),
    ("后退", "backward"),
    ("左移", "left"),
    ("向左", "left"),
    ("右移", "right"),
    ("向右", "right"),
    ("左转", "turn_left"),
    ("右转", "turn_right"),
    ("停止", "stop"),
    ("停下", "stop"),
)

_CHINESE_DIGITS = {
    "零": 0,
    "〇": 0,
    "一": 1,
    "二": 2,
    "两": 2,
    "三": 3,
    "四": 4,
    "五": 5,
}


def parse_voice_motion_command(text: str) -> Optional[VoiceMotionCommand]:
    if CONTROL_PREFIX not in text:
        return None
    command_text = text.split(CONTROL_PREFIX, 1)[1].strip()
    command_text = re.split(r"[。！？\n]", command_text, maxsplit=1)[0].strip()
    if not command_text:
        return None

    direction = None
    for phrase, candidate in _DIRECTIONS:
        if phrase in command_text:
            direction = candidate
            break
    if direction is None:
        return None
    if direction == "stop":
        return VoiceMotionCommand(direction="stop", duration_sec=0.0)

    duration = _parse_duration(command_text)
    return VoiceMotionCommand(direction=direction, duration_sec=duration)


def _parse_duration(text: str) -> float:
    match = re.search(r"(\d+(?:\.\d+)?)\s*秒", text)
    if match:
        return _clamp_duration(float(match.group(1)))
    for char, value in _CHINESE_DIGITS.items():
        if f"{char}秒" in text:
            return _clamp_duration(float(value))
    return 1.0


def _clamp_duration(value: float) -> float:
    return max(0.2, min(value, 3.0))
