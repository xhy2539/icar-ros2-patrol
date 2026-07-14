#!/usr/bin/env python3
"""豆包端到端实时语音 ROS2 节点。

订阅 /voice/user_text (手机 APP 语音识别结果)，
通过豆包 API 生成 TTS 语音从音箱播放，
同时发布 /voice/assistant_result 供 voice_command_router_node 路由任务。

架构:
  手机 APP → /voice/user_text → doubao_voice_node → 豆包 API → TTS 音箱
                                                  → /voice/assistant_result
                                                  → /voice/status
"""

import asyncio
import json
import os
import queue
import threading
import time
import uuid

import numpy as np
import rclpy
from rclpy.node import Node
from rclpy.qos import QoSProfile, ReliabilityPolicy
from std_msgs.msg import String

from .doubao_protocol import (
    build_frame,
    build_audio_frame,
    build_text_frame,
    parse_frame,
    parse_json,
    COMP_NONE,
    EVT_CHAT_RESPONSE,
    EVT_CHAT_ENDED,
    EVT_CONN_FAILED,
    EVT_CONN_FINISHED,
    EVT_CONN_STARTED,
    EVT_DIALOG_ERROR,
    EVT_FINISH_CONNECTION,
    EVT_FINISH_SESSION,
    EVT_SESSION_FAILED,
    EVT_SESSION_FINISHED,
    EVT_SESSION_STARTED,
    EVT_START_CONNECTION,
    EVT_START_SESSION,
    EVT_TTS_ENDED,
    EVT_TTS_RESPONSE,
    EVT_TTS_SENTENCE_END,
    EVT_TTS_SENTENCE_START,
    EVT_USAGE_RESPONSE,
    MSG_FULL_CLIENT,
    MSG_AUDIO_CLIENT,
    SER_JSON,
    SER_RAW,
    EVENT_NAMES,
)

try:
    import sounddevice as sd
    import websockets
except ImportError as e:
    sd = None
    websockets = None
    _IMPORT_ERROR = str(e)

try:
    from dotenv import load_dotenv
except ImportError:

    def load_dotenv(path=None):
        pass


# ── 常量 ────────────────────────────────────────────────────────
WS_URL = "wss://openspeech.bytedance.com/api/v3/realtime/dialogue"
SAMPLE_RATE_OUT = 24000
SILENCE = b"\x00" * 640  # 20ms PCM silence, 用于保持音频管线活跃

DEFAULT_SYSTEM_ROLE = (
    "你是智能巡检小车的语音助手，你的名字叫小巡。"
    "用简短自然的中文与用户交流。"
    "当用户要求巡检或执行任务时，先复述内容并请用户确认。"
    "只有用户明确确认后，才用「执行任务：」开头输出最终指令。"
    "用户说「停下」「停止」「别动」「紧急停止」时，立即回复「紧急停止」。"
)


# ── 节点 ────────────────────────────────────────────────────────
class DoubaoVoiceNode(Node):
    """豆包端到端实时语音 ROS2 节点。"""

    def __init__(self):
        super().__init__("doubao_voice_node")

        # ── 参数 ──
        self.declare_parameter("app_id", "")
        self.declare_parameter("access_key", "")
        self.declare_parameter("model", "1.2.1.1")
        self.declare_parameter("speaker", "zh_female_vv_jupiter_bigtts")
        self.declare_parameter("system_role", DEFAULT_SYSTEM_ROLE)
        self.declare_parameter("output_device", "")  # 空 = 默认音箱

        self._app_id = self._resolve_cred("app_id", "DOUBAO_APP_ID")
        self._access_key = self._resolve_cred("access_key", "DOUBAO_ACCESS_KEY")
        self._model = str(self.get_parameter("model").value)
        self._speaker = str(self.get_parameter("speaker").value)
        self._system_role = str(self.get_parameter("system_role").value)
        self._output_device = str(self.get_parameter("output_device").value) or None

        if not self._app_id or not self._access_key:
            self.get_logger().error("缺少豆包凭据！请设置 app_id / access_key 参数或环境变量")
            raise RuntimeError("Missing doubao credentials")

        if sd is None or websockets is None:
            raise RuntimeError(f"缺少依赖: {_IMPORT_ERROR}")

        # ── 状态 ──
        self._ws = None
        self._session_id = ""
        self._dialog_id = ""
        self._connected = False
        self._output_stream = None

        # 跨线程队列: ROS2 回调 → asyncio
        self._text_queue = queue.Queue(maxsize=32)
        self._running = True

        # ── QoS ──
        qos = QoSProfile(depth=10, reliability=ReliabilityPolicy.RELIABLE)

        # ── 订阅 ──
        self._user_text_sub = self.create_subscription(
            String, "/voice/user_text", self._on_user_text, qos
        )

        # ── 发布 ──
        self._result_pub = self.create_publisher(
            String, "/voice/assistant_result", qos
        )
        self._status_pub = self.create_publisher(String, "/voice/status", qos)

        # ── 启动 asyncio 线程 ──
        self._loop = None
        self._thread = threading.Thread(target=self._run_asyncio, daemon=True)
        self._thread.start()

        self.get_logger().info(
            f"doubao_voice_node 已启动 (model={self._model}, speaker={self._speaker})"
        )

    # ── 凭据: 参数优先, 环境变量兜底 ─────────────────────────

    def _resolve_cred(self, param_name: str, env_name: str) -> str:
        val = str(self.get_parameter(param_name).value).strip()
        if val:
            return val
        # 尝试加载 .env
        for p in [
            os.path.join(os.path.expanduser("~"), ".env"),
            os.path.join(os.path.expanduser("~"), ".doubao_env"),
        ]:
            if os.path.exists(p):
                load_dotenv(p)
                break
        return os.environ.get(env_name, "")

    # ── ROS2 回调 ────────────────────────────────────────────

    def _on_user_text(self, msg: String):
        """手机 APP 语音识别结果。"""
        text = self._extract_text(msg.data)
        if not text:
            return

        self.get_logger().info(f"收到语音: {text[:60]}")
        try:
            self._text_queue.put_nowait(text)
        except queue.Full:
            self.get_logger().warn("文本队列满，丢弃消息")

    @staticmethod
    def _extract_text(raw: str) -> str:
        """从可能的 JSON 包装中提取纯文本。"""
        try:
            data = json.loads(raw)
            if isinstance(data, dict):
                return str(data.get("text", "")).strip()
        except (json.JSONDecodeError, TypeError):
            pass
        return str(raw).strip()

    # ── 发布 ─────────────────────────────────────────────────

    def _publish_result(self, text: str):
        msg = String()
        msg.data = json.dumps(
            {"text": text, "is_listen": False, "end_of_turn": True},
            ensure_ascii=False,
        )
        self._result_pub.publish(msg)

    def _publish_status(self, state: str, detail: str = ""):
        msg = String()
        msg.data = json.dumps(
            {"state": state, "detail": detail, "time": time.time()},
            ensure_ascii=False,
        )
        self._status_pub.publish(msg)

    # ── asyncio 主循环 ───────────────────────────────────────

    def _run_asyncio(self):
        """在后台线程中运行 asyncio 事件循环。"""
        asyncio.run(self._connection_supervisor())

    async def _connection_supervisor(self):
        """管理 WebSocket 连接生命周期，断线自动重连。"""
        self._loop = asyncio.get_running_loop()
        self._open_speaker()

        while self._running:
            try:
                await self._session()
            except Exception as exc:
                self.get_logger().error(f"豆包连接异常: {exc}")
                self._publish_status("disconnected", str(exc))
            self._connected = False
            self._ws = None
            if self._running:
                await asyncio.sleep(3.0)

    async def _session(self):
        """一次完整的 WebSocket 会话。"""
        ws_headers = {
            "X-Api-App-ID": self._app_id,
            "X-Api-Access-Key": self._access_key,
            "X-Api-Resource-Id": "volc.speech.dialog",
            "X-Api-App-Key": "PlgvMymc7f3tQnJ6",
        }

        self._publish_status("connecting")
        async with websockets.connect(
            WS_URL,
            extra_headers=ws_headers,
            max_size=2**24,
            ping_interval=30,
            ping_timeout=10,
            close_timeout=5,
        ) as ws:
            self._ws = ws
            self.get_logger().info("WebSocket 已连接")

            # 握手
            await self._handshake()
            self._connected = True
            self._publish_status("active")
            self.get_logger().info(
                f"豆包会话已建立 (dialog_id={self._dialog_id[:12]}...)"
            )

            # 并发: 处理用户文本 + 接收服务端事件
            await asyncio.gather(
                self._process_text_loop(),
                self._recv_loop(),
            )

    async def _handshake(self):
        """StartConnection → StartSession。"""
        # StartConnection
        await self._ws.send(
            build_frame(event_id=EVT_START_CONNECTION, payload=b"{}")
        )
        resp = await self._recv_one(timeout=10)
        if resp is None or resp["event_id"] != EVT_CONN_STARTED:
            raise RuntimeError(f"ConnectionStarted 失败: {resp}")

        # StartSession
        self._session_id = str(uuid.uuid4())
        session_config = json.dumps(
            {
                "asr": {
                    "audio_info": {
                        "format": "pcm",
                        "sample_rate": 16000,
                        "channel": 1,
                    }
                },
                "dialog": {
                    "bot_name": "小巡",
                    "system_role": self._system_role,
                    "extra": {
                        "strict_audit": False,
                        "model": self._model,
                    },
                },
                "tts": {
                    "speaker": self._speaker,
                    "audio_config": {
                        "channel": 1,
                        "format": "pcm_s16le",
                        "sample_rate": SAMPLE_RATE_OUT,
                    },
                },
            },
            ensure_ascii=False,
        ).encode("utf-8")

        await self._ws.send(
            build_frame(
                event_id=EVT_START_SESSION,
                payload=session_config,
                session_id=self._session_id,
            )
        )

        resp = await self._recv_one(timeout=15)
        if resp is None or resp["event_id"] != EVT_SESSION_STARTED:
            raise RuntimeError(f"SessionStarted 失败: {resp}")

        self._dialog_id = parse_json(resp["payload"]).get("dialog_id", "")

    async def _recv_one(self, timeout: float = 10):
        """接收并解析一帧。"""
        try:
            raw = await asyncio.wait_for(self._ws.recv(), timeout=timeout)
        except asyncio.TimeoutError:
            return None
        if isinstance(raw, str):
            raw = raw.encode("utf-8")
        return parse_frame(raw)

    # ── 文本处理 ─────────────────────────────────────────────

    async def _process_text_loop(self):
        """从队列取文本 → 发送到豆包。"""
        loop = asyncio.get_running_loop()
        while self._running and self._connected:
            try:
                text = await loop.run_in_executor(
                    None, lambda: self._text_queue.get(timeout=0.5)
                )
            except queue.Empty:
                continue

            try:
                # 保持音频管线活跃
                await self._ws.send(
                    build_audio_frame(SILENCE, self._session_id)
                )
                await asyncio.sleep(0.1)

                # 发送文本查询
                await self._ws.send(build_text_frame(text, self._session_id))
                self.get_logger().info(f"已发送到豆包: {text[:50]}...")
            except Exception as e:
                self.get_logger().error(f"发送文本失败: {e}")
                break

    # ── 接收服务端事件 ───────────────────────────────────────

    async def _recv_loop(self):
        """接收豆包服务端事件。"""
        full_text = ""  # 累积的文本回复
        tts_bytes = 0

        while self._running and self._connected:
            resp = await self._recv_one(timeout=2.0)
            if resp is None:
                continue

            evt = resp["event_id"]

            if evt == EVT_CHAT_RESPONSE:
                # 模型文本回复
                content = parse_json(resp["payload"]).get("content", "")
                if content:
                    full_text += content

            elif evt == EVT_CHAT_ENDED:
                if full_text.strip():
                    self.get_logger().info(f"豆包: {full_text[:80]}")
                    self._publish_result(full_text)
                full_text = ""

            elif evt == EVT_TTS_RESPONSE:
                # TTS 音频 → 音箱
                if resp["payload"] and self._output_stream is not None:
                    tts_bytes += len(resp["payload"])
                    try:
                        pcm = np.frombuffer(resp["payload"], dtype=np.int16)
                        self._output_stream.write(pcm)
                    except Exception as e:
                        self.get_logger().warn(f"音频播放失败: {e}")

            elif evt == EVT_TTS_ENDED:
                pass  # TTS 结束

            elif evt == EVT_TTS_SENTENCE_START:
                js = parse_json(resp["payload"])
                text = js.get("text", "")
                if text:
                    self.get_logger().info(f"TTS: {text[:60]}")

            elif evt == EVT_TTS_SENTENCE_END:
                pass

            elif evt == EVT_USAGE_RESPONSE:
                js = parse_json(resp["payload"])
                usage = js.get("usage", {})
                if usage:
                    total = (
                        usage.get("input_text_tokens", 0)
                        + usage.get("input_audio_tokens", 0)
                        + usage.get("output_text_tokens", 0)
                        + usage.get("output_audio_tokens", 0)
                    )
                    self.get_logger().debug(f"Token 用量: ~{total}")

            elif evt == EVT_SESSION_FAILED:
                js = parse_json(resp["payload"])
                self.get_logger().error(
                    f"Session 失败: {js.get('error', js)}"
                )
                self._connected = False

            elif evt == EVT_CONN_FAILED:
                js = parse_json(resp["payload"])
                self.get_logger().error(
                    f"连接失败: {js.get('error', js)}"
                )
                self._connected = False

            elif evt == EVT_DIALOG_ERROR:
                js = parse_json(resp["payload"])
                self.get_logger().warn(
                    f"对话错误: {js.get('message', js)}"
                )

            elif evt == EVT_CONN_FINISHED:
                self.get_logger().info("连接已结束")
                self._connected = False

            elif evt == EVT_SESSION_FINISHED:
                self.get_logger().info("会话已结束")

            else:
                # 未知事件，debug 级别打印
                name = EVENT_NAMES.get(evt, f"Unknown({evt})")
                if resp["ser"] == SER_JSON and resp["payload"]:
                    js = parse_json(resp["payload"])
                    self.get_logger().debug(
                        f"事件 {name}: {json.dumps(js, ensure_ascii=False)[:100]}"
                    )

    # ── 音箱 ─────────────────────────────────────────────────

    def _open_speaker(self):
        """打开音箱输出流。"""
        device = None
        if self._output_device:
            try:
                device = int(self._output_device)
            except ValueError:
                pass
        try:
            self._output_stream = sd.RawOutputStream(
                samplerate=SAMPLE_RATE_OUT,
                channels=1,
                dtype="int16",
                device=device,
            )
            self._output_stream.start()
            self.get_logger().info(f"音箱已打开 (device={device})")
        except Exception as e:
            self.get_logger().warn(f"音箱打开失败: {e}，语音回复将无声音")
            self._output_stream = None

    def _close_speaker(self):
        if self._output_stream is not None:
            try:
                self._output_stream.stop()
                self._output_stream.close()
            except Exception:
                pass
            self._output_stream = None

    # ── 关闭 ─────────────────────────────────────────────────

    async def _shutdown(self):
        """优雅关闭 WebSocket 连接。"""
        self._running = False
        if self._ws:
            try:
                await asyncio.wait_for(
                    self._ws.send(
                        build_frame(
                            event_id=EVT_FINISH_SESSION,
                            payload=b"{}",
                            session_id=self._session_id,
                        )
                    ),
                    timeout=3,
                )
                await asyncio.sleep(0.3)
                await asyncio.wait_for(
                    self._ws.send(
                        build_frame(event_id=EVT_FINISH_CONNECTION, payload=b"{}")
                    ),
                    timeout=3,
                )
            except Exception:
                pass

    def destroy_node(self):
        self._running = False
        self._close_speaker()
        # 触发 asyncio 关闭
        if self._loop and self._loop.is_running():
            asyncio.run_coroutine_threadsafe(self._shutdown(), self._loop)
        super().destroy_node()


# ── 入口 ────────────────────────────────────────────────────────
def main(args=None):
    rclpy.init(args=args)

    # 如果未传凭据参数，尝试加载 .env
    try:
        node = DoubaoVoiceNode()
    except (RuntimeError, ImportError) as e:
        print(f"启动失败: {e}", flush=True)
        return

    try:
        rclpy.spin(node)
    except KeyboardInterrupt:
        node.get_logger().info("用户中断")
    finally:
        node.destroy_node()
        rclpy.shutdown()


if __name__ == "__main__":
    main()
