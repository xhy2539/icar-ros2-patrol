#!/usr/bin/env python3
"""Microphone/speaker bridge for the MiniCPM-o duplex WebSocket API."""

import asyncio
import base64
import inspect
import json
import queue
import ssl
import threading
import time
import uuid

import numpy as np
import rclpy
from rclpy.node import Node
from std_msgs.msg import String

try:
    import sounddevice as sd
    import websockets
except ImportError:
    sd = None
    websockets = None


DEFAULT_PROMPT = (
    "你是智能巡检小车的语音助手。用简短自然的中文交流。"
    "你不能直接生成轮速或cmd_vel。用户要求移动、巡检、识别或采集时，"
    "先复述并询问确认；只有用户明确确认后，才用‘执行任务：’开头完整复述任务。"
    "用户说停止、别动、急停或刹车时，立即只说‘紧急停止’。"
)


class DuplexAudioNode(Node):
    def __init__(self):
        super().__init__("duplex_audio_node")
        self.declare_parameter("server_url", "wss://127.0.0.1:8040")
        self.declare_parameter("verify_tls", False)
        self.declare_parameter("input_device", "")
        self.declare_parameter("output_device", "")
        self.declare_parameter("vad_rms_threshold", 0.025)
        self.declare_parameter("system_prompt", DEFAULT_PROMPT)

        self.result_pub = self.create_publisher(
            String, "/voice/assistant_result", 20
        )
        self.status_pub = self.create_publisher(String, "/voice/status", 10)

        self._loop = None
        self._audio_queue = None
        self._input_buffer = bytearray()
        self._playback_queue = queue.Queue(maxsize=16)
        self._input_stream = None
        self._output_stream = None
        self._model_speaking = False
        self._stopping = threading.Event()

        if sd is None or websockets is None:
            raise RuntimeError(
                "voice_control requires numpy, sounddevice and websockets"
            )

        self._thread = threading.Thread(target=self._run_asyncio, daemon=True)
        self._thread.start()
        self.get_logger().info("duplex_audio_node started")

    def _publish_status(self, state, detail=""):
        msg = String()
        msg.data = json.dumps(
            {"state": state, "detail": detail, "time": time.time()},
            ensure_ascii=False,
        )
        self.status_pub.publish(msg)

    def _run_asyncio(self):
        asyncio.run(self._connection_supervisor())

    async def _connection_supervisor(self):
        self._loop = asyncio.get_running_loop()
        while not self._stopping.is_set():
            try:
                await self._run_session()
            except Exception as exc:
                self.get_logger().error(f"duplex connection failed: {exc}")
                self._publish_status("disconnected", str(exc))
            self._stop_audio()
            if not self._stopping.is_set():
                await asyncio.sleep(3.0)

    async def _run_session(self):
        base_url = str(self.get_parameter("server_url").value).rstrip("/")
        session_id = f"adx_robot_{uuid.uuid4().hex[:10]}"
        uri = f"{base_url}/ws/duplex/{session_id}"
        ssl_context = self._ssl_context(uri)
        connect_kwargs = {
            "ssl": ssl_context,
            "max_size": 32 * 1024 * 1024,
            "open_timeout": 20,
        }
        if "proxy" in inspect.signature(websockets.connect).parameters:
            connect_kwargs["proxy"] = None

        self._publish_status("connecting", uri)
        async with websockets.connect(uri, **connect_kwargs) as ws:
            await self._prepare(ws)
            self._audio_queue = asyncio.Queue(maxsize=3)
            self._start_audio()
            self._publish_status("active")
            await asyncio.gather(self._send_audio(ws), self._receive(ws))

    def _ssl_context(self, uri):
        if not uri.startswith("wss://"):
            return None
        context = ssl.create_default_context()
        if not bool(self.get_parameter("verify_tls").value):
            context.check_hostname = False
            context.verify_mode = ssl.CERT_NONE
        return context

    async def _prepare(self, ws):
        while True:
            event = json.loads(await asyncio.wait_for(ws.recv(), timeout=60))
            event_type = event.get("type")
            if event_type == "queue_done":
                break
            if event_type == "error":
                raise RuntimeError(event.get("error", "queue failed"))

        await ws.send(
            json.dumps(
                {
                    "type": "prepare",
                    "system_prompt": str(
                        self.get_parameter("system_prompt").value
                    ),
                    "config": {
                        "generate_audio": True,
                        "chunk_ms": 1000,
                        "sample_rate": 16000,
                        "force_listen_count": 2,
                        "max_new_speak_tokens_per_chunk": 12,
                        "listen_prob_scale": 1.0,
                        "temperature": 0.7,
                        "top_p": 0.8,
                        "top_k": 20,
                    },
                },
                ensure_ascii=False,
            )
        )
        while True:
            event = json.loads(await asyncio.wait_for(ws.recv(), timeout=120))
            if event.get("type") == "prepared":
                return
            if event.get("type") == "error":
                raise RuntimeError(event.get("error", "prepare failed"))

    def _start_audio(self):
        input_device = str(self.get_parameter("input_device").value) or None
        output_device = str(self.get_parameter("output_device").value) or None
        self._input_buffer.clear()
        self._input_stream = sd.RawInputStream(
            samplerate=16000,
            channels=1,
            dtype="float32",
            blocksize=1600,
            device=input_device,
            callback=self._on_input,
        )
        self._output_stream = sd.RawOutputStream(
            samplerate=24000,
            channels=1,
            dtype="float32",
            device=output_device,
        )
        self._input_stream.start()
        self._output_stream.start()
        threading.Thread(target=self._playback_worker, daemon=True).start()

    def _stop_audio(self):
        for stream in (self._input_stream, self._output_stream):
            if stream is not None:
                try:
                    stream.stop()
                    stream.close()
                except Exception:
                    pass
        self._input_stream = None
        self._output_stream = None
        self._clear_playback()

    def _on_input(self, indata, frames, time_info, status):
        del frames, time_info
        if status:
            self.get_logger().warning(f"audio input status: {status}")
        raw = bytes(indata)
        samples = np.frombuffer(raw, dtype=np.float32)
        rms = float(np.sqrt(np.mean(samples * samples))) if samples.size else 0.0
        interrupt = self._model_speaking and rms >= float(
            self.get_parameter("vad_rms_threshold").value
        )
        if interrupt:
            self._clear_playback()
        self._input_buffer.extend(raw)
        chunk_bytes = 16000 * 4
        while len(self._input_buffer) >= chunk_bytes:
            chunk = bytes(self._input_buffer[:chunk_bytes])
            del self._input_buffer[:chunk_bytes]
            if self._loop and self._audio_queue:
                self._loop.call_soon_threadsafe(
                    self._enqueue_audio, chunk, interrupt
                )

    def _enqueue_audio(self, chunk, interrupt):
        if self._audio_queue.full():
            try:
                self._audio_queue.get_nowait()
                self._audio_queue.task_done()
            except asyncio.QueueEmpty:
                pass
        self._audio_queue.put_nowait((chunk, interrupt))

    async def _send_audio(self, ws):
        while True:
            chunk, interrupt = await self._audio_queue.get()
            try:
                await ws.send(
                    json.dumps(
                        {
                            "type": "audio_chunk",
                            "audio_base64": base64.b64encode(chunk).decode(),
                            "force_listen": interrupt,
                        }
                    )
                )
            finally:
                self._audio_queue.task_done()

    async def _receive(self, ws):
        async for raw in ws:
            event = json.loads(raw)
            event_type = event.get("type")
            if event_type == "result":
                self._model_speaking = not bool(event.get("is_listen", True))
                msg = String()
                msg.data = json.dumps(event, ensure_ascii=False)
                self.result_pub.publish(msg)
                if event.get("audio_data"):
                    self._queue_playback(event["audio_data"])
            elif event_type == "audio_only" and event.get("audio_data"):
                self._queue_playback(event["audio_data"])
            elif event_type in ("stopped", "timeout", "error"):
                raise RuntimeError(event.get("error", event_type))

    def _queue_playback(self, audio_b64):
        data = base64.b64decode(audio_b64)
        try:
            self._playback_queue.put_nowait(data)
        except queue.Full:
            try:
                self._playback_queue.get_nowait()
            except queue.Empty:
                pass
            self._playback_queue.put_nowait(data)

    def _playback_worker(self):
        while self._output_stream is not None and not self._stopping.is_set():
            try:
                data = self._playback_queue.get(timeout=0.5)
            except queue.Empty:
                continue
            try:
                self._output_stream.write(data)
            except Exception as exc:
                self.get_logger().warning(f"audio playback failed: {exc}")

    def _clear_playback(self):
        while True:
            try:
                self._playback_queue.get_nowait()
            except queue.Empty:
                return

    def destroy_node(self):
        self._stopping.set()
        self._stop_audio()
        super().destroy_node()


def main(args=None):
    rclpy.init(args=args)
    node = DuplexAudioNode()
    try:
        rclpy.spin(node)
    except KeyboardInterrupt:
        pass
    finally:
        node.destroy_node()
        rclpy.shutdown()


if __name__ == "__main__":
    main()
