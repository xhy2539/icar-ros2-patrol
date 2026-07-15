from pathlib import Path


SOURCE = (
    Path(__file__).resolve().parents[1]
    / "voice_control"
    / "doubao_voice_node.py"
)


def test_browser_turn_end_feeds_silence_for_server_vad():
    source = SOURCE.read_text(encoding="utf-8")

    assert "WEB_TURN_END_SILENCE_FRAMES" in source
    assert "threading.Timer(0.15, self._queue_web_turn_silence).start()" in source
    assert "for _ in range(WEB_TURN_END_SILENCE_FRAMES):" in source
    assert "EVT_END_ASR" in source
    assert "event_id=EVT_END_ASR" in source
