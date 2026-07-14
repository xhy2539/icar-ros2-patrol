#!/usr/bin/env python3
"""Receive browser PCM over WebSocket and publish it into the ROS2 voice graph."""

from __future__ import annotations

import asyncio
import json
import threading

import rclpy
from rclpy.node import Node
from std_msgs.msg import String, UInt8MultiArray

from .web_voice_protocol import VoiceSession, decode_control_frame

try:
    from websockets.asyncio.server import serve
except ImportError:  # pragma: no cover - reported at runtime on the car
    serve = None


class WebVoiceGatewayNode(Node):
    """Loopback-safe browser audio ingress for ``doubao_voice_node``."""

    def __init__(self) -> None:
        super().__init__("web_voice_gateway_node")
        self.declare_parameter("host", "0.0.0.0")
        self.declare_parameter("port", 8767)
        self._audio_pub = self.create_publisher(UInt8MultiArray, "/voice/web_audio", 20)
        self._control_pub = self.create_publisher(String, "/voice/web_audio_control", 10)
        self._thread = threading.Thread(target=self._run, daemon=True)
        self._thread.start()

    def _publish_control(self, frame: dict, detail: str = "") -> None:
        message = String()
        message.data = json.dumps({**frame, "source": "web", "detail": detail}, ensure_ascii=False)
        self._control_pub.publish(message)

    async def _client(self, websocket) -> None:
        session = VoiceSession()
        try:
            async for message in websocket:
                if isinstance(message, bytes):
                    if not session.accept_audio(message):
                        await websocket.send(json.dumps({"type": "error", "code": "audio_without_start"}))
                        continue
                    audio = UInt8MultiArray()
                    audio.data = list(message)
                    self._audio_pub.publish(audio)
                    continue

                frame = decode_control_frame(message)
                if frame is None or not session.apply_control(frame):
                    await websocket.send(json.dumps({"type": "error", "code": "invalid_frame"}))
                    continue
                self._publish_control(frame)
                await websocket.send(json.dumps({"type": "ack", "event": frame["type"]}))
        finally:
            if session.active:
                session.apply_control({"type": "end"})
                self._publish_control({"type": "end"}, "browser disconnected")

    async def _serve(self) -> None:
        if serve is None:
            raise RuntimeError("websockets package is required for web voice gateway")
        host = str(self.get_parameter("host").value)
        port = int(self.get_parameter("port").value)
        async with serve(self._client, host, port, max_size=2**20):
            self.get_logger().info(f"web voice gateway listening on {host}:{port}")
            await asyncio.get_running_loop().create_future()

    def _run(self) -> None:
        try:
            asyncio.run(self._serve())
        except Exception as exc:
            self.get_logger().error(f"web voice gateway stopped: {exc}")


def main() -> None:
    rclpy.init()
    node = WebVoiceGatewayNode()
    try:
        rclpy.spin(node)
    finally:
        node.destroy_node()
        rclpy.shutdown()
