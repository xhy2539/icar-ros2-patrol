from __future__ import annotations

"""豆包端到端实时语音 API — 二进制帧编解码器。

WebSocket 端点: wss://openspeech.bytedance.com/api/v3/realtime/dialogue
协议: 自定义二进制帧，文档见 https://www.volcengine.com/docs/6561/1594356
"""

import json
import struct

# ── 消息类型 (4 bits) ──────────────────────────────────────────
MSG_FULL_CLIENT = 0b0001   # 客户端文本事件
MSG_FULL_SERVER = 0b1001   # 服务端文本事件
MSG_AUDIO_CLIENT = 0b0010  # 客户端音频事件
MSG_AUDIO_SERVER = 0b1011  # 服务端音频事件
MSG_ERROR = 0b1111         # 错误

# ── 序列化 / 压缩 (各 4 bits) ──────────────────────────────────
SER_RAW = 0b0000
SER_JSON = 0b0001
COMP_NONE = 0b0000
COMP_GZIP = 0b0001

# ── Message type specific flags ─────────────────────────────────
FLAG_HAS_EVENT = 0b0100

# ── 事件 ID ────────────────────────────────────────────────────
EVT_START_CONNECTION = 1
EVT_FINISH_CONNECTION = 2
EVT_START_SESSION = 100
EVT_FINISH_SESSION = 102
EVT_TASK_REQUEST = 200
EVT_END_ASR = 400
EVT_CHAT_TTS_TEXT = 500
EVT_CHAT_TEXT_QUERY = 501

EVT_CONN_STARTED = 50
EVT_CONN_FAILED = 51
EVT_CONN_FINISHED = 52
EVT_SESSION_STARTED = 150
EVT_SESSION_FINISHED = 152
EVT_SESSION_FAILED = 153
EVT_USAGE_RESPONSE = 154
EVT_TTS_SENTENCE_START = 350
EVT_TTS_SENTENCE_END = 351
EVT_TTS_RESPONSE = 352
EVT_TTS_ENDED = 359
EVT_ASR_INFO = 450
EVT_ASR_RESPONSE = 451
EVT_ASR_ENDED = 459
EVT_CHAT_RESPONSE = 550
EVT_CHAT_ENDED = 559
EVT_CHAT_TEXT_QUERY_CONF = 553
EVT_DIALOG_ERROR = 599

EVENT_NAMES = {
    1: "StartConnection", 2: "FinishConnection",
    50: "ConnectionStarted", 51: "ConnectionFailed", 52: "ConnectionFinished",
    100: "StartSession", 102: "FinishSession",
    150: "SessionStarted", 152: "SessionFinished", 153: "SessionFailed",
    154: "UsageResponse",
    200: "TaskRequest",
    400: "EndASR",
    350: "TTSSentenceStart", 351: "TTSSentenceEnd",
    352: "TTSResponse", 359: "TTSEnded",
    450: "ASRInfo", 451: "ASRResponse", 459: "ASREnded",
    500: "ChatTTSText", 501: "ChatTextQuery",
    550: "ChatResponse", 553: "ChatTextQueryConfirmed",
    559: "ChatEnded",
    599: "DialogCommonError",
}


def build_frame(
    event_id: int = 0,
    payload: bytes = b"",
    session_id: str = "",
    msg_type: int = MSG_FULL_CLIENT,
    ser: int = SER_JSON,
    comp: int = COMP_NONE,
) -> bytes:
    """构造豆包二进制帧。

    Connect 级事件 (1, 2):  [header 4B][event_id 4B][payload_size 4B][payload]
    Session 级事件 (100+): [header 4B][event_id 4B][sid_size 4B][sid][payload_size 4B][payload]
    """
    flags = FLAG_HAS_EVENT
    header = struct.pack(
        "4B",
        (0b0001 << 4) | 0b0001,  # version=1, header_size=1
        (msg_type << 4) | flags,
        (ser << 4) | comp,
        0x00,
    )

    body = struct.pack(">I", event_id)

    if session_id:
        sid_bytes = session_id.encode("utf-8")
        body += struct.pack(">I", len(sid_bytes)) + sid_bytes

    body += struct.pack(">I", len(payload)) + payload
    return header + body


def build_audio_frame(pcm: bytes, session_id: str) -> bytes:
    """构造音频数据帧 (TaskRequest, event 200)."""
    return build_frame(
        event_id=EVT_TASK_REQUEST,
        payload=pcm,
        session_id=session_id,
        msg_type=MSG_AUDIO_CLIENT,
        ser=SER_RAW,
    )


def build_text_frame(text: str, session_id: str) -> bytes:
    """构造文本查询帧 (ChatTextQuery, event 501)."""
    payload = json.dumps({"content": text}, ensure_ascii=False).encode("utf-8")
    return build_frame(
        event_id=EVT_CHAT_TEXT_QUERY,
        payload=payload,
        session_id=session_id,
    )


def parse_frame(data: bytes) -> dict | None:
    """解析服务端二进制帧。

    Returns:
        dict with keys: msg_type, event_id, payload, session_id, ser
        None if parse fails.
    """
    if len(data) < 8:
        return None

    byte0, byte1, byte2, byte3 = struct.unpack_from("4B", data, 0)
    msg_type = (byte1 >> 4) & 0x0F
    flags = byte1 & 0x0F
    ser = (byte2 >> 4) & 0x0F

    offset = 4

    # 错误帧: msg_type == 0b1111，有 4 字节 error_code
    error_code = 0
    if msg_type == MSG_ERROR:
        if len(data) >= offset + 4:
            error_code = struct.unpack_from(">i", data, offset)[0]
            offset += 4

    # Sequence 字段（可选）
    if flags & 0b0011:
        if len(data) >= offset + 4:
            offset += 4

    # Event ID
    event_id = 0
    if flags & FLAG_HAS_EVENT:
        if len(data) >= offset + 4:
            event_id = struct.unpack_from(">I", data, offset)[0]
            offset += 4

    # Session ID（仅 session 级事件，event >= 100）
    session_id = ""
    if event_id >= 100:
        if len(data) >= offset + 4:
            sid_size = struct.unpack_from(">I", data, offset)[0]
            offset += 4
            if sid_size > 0 and len(data) >= offset + sid_size:
                session_id = data[offset:offset + sid_size].decode(
                    "utf-8", errors="replace"
                )
                offset += sid_size

    # Payload
    payload = b""
    if len(data) >= offset + 4:
        payload_size = struct.unpack_from(">I", data, offset)[0]
        offset += 4
        if payload_size > 0 and len(data) >= offset + payload_size:
            payload = data[offset:offset + payload_size]

    return {
        "msg_type": msg_type,
        "event_id": event_id,
        "payload": payload,
        "session_id": session_id,
        "ser": ser,
    }


def parse_json(payload: bytes) -> dict:
    """尝试将 payload 解析为 JSON，失败返回空 dict。"""
    try:
        return json.loads(payload.decode("utf-8"))
    except (json.JSONDecodeError, UnicodeDecodeError):
        return {}
