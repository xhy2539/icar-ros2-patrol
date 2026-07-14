import json

from voice_control.web_voice_protocol import VoiceSession, decode_control_frame


def test_start_frame_requires_16khz_mono_pcm():
    frame = json.dumps(
        {"type": "start", "sample_rate": 16000, "channels": 1, "format": "pcm_s16le"}
    )

    assert decode_control_frame(frame) == {
        "type": "start",
        "sample_rate": 16000,
        "channels": 1,
        "format": "pcm_s16le",
    }


def test_invalid_start_frame_is_rejected():
    assert decode_control_frame('{"type":"start","sample_rate":48000}') is None


def test_audio_requires_an_active_session():
    session = VoiceSession()

    assert not session.accept_audio(b"pcm")
    assert session.apply_control(
        {"type": "start", "sample_rate": 16000, "channels": 1, "format": "pcm_s16le"}
    )
    assert session.accept_audio(b"pcm")
    assert session.apply_control({"type": "end"})
    assert not session.accept_audio(b"pcm")
