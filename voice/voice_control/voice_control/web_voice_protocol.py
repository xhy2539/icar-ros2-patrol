"""Validation for browser microphone frames sent to the car voice gateway."""

from __future__ import annotations

import json
from typing import Any


PCM_CONFIG = {"sample_rate": 16000, "channels": 1, "format": "pcm_s16le"}


def decode_control_frame(raw: str | bytes) -> dict[str, Any] | None:
    """Return a supported voice lifecycle frame, or ``None`` when invalid."""
    try:
        if isinstance(raw, bytes):
            raw = raw.decode("utf-8")
        frame = json.loads(raw)
    except (TypeError, UnicodeDecodeError, json.JSONDecodeError):
        return None

    if not isinstance(frame, dict):
        return None
    if frame.get("type") == "end":
        return {"type": "end"}
    if frame.get("type") != "start":
        return None
    if any(frame.get(key) != value for key, value in PCM_CONFIG.items()):
        return None
    return {"type": "start", **PCM_CONFIG}


class VoiceSession:
    """Small state holder shared by a WebSocket connection and ROS publisher."""

    def __init__(self) -> None:
        self.active = False

    def apply_control(self, frame: dict[str, Any]) -> bool:
        if frame.get("type") == "start":
            if any(frame.get(key) != value for key, value in PCM_CONFIG.items()):
                return False
            self.active = True
            return True
        if frame == {"type": "end"} and self.active:
            self.active = False
            return True
        return False

    def accept_audio(self, payload: bytes) -> bool:
        return self.active and bool(payload)
