#!/usr/bin/env python3
"""Local WebSocket-to-MQTT bridge for browser-based iCar cloud control.

Browsers can't speak raw TCP MQTT. This bridge accepts WebSocket connections
from the control_simulator.html page and forwards them to the MQTT broker.
"""

import asyncio
import base64
import json
import os
import signal
import sys

import paho.mqtt.client as mqtt
import websockets
from websockets.server import WebSocketServerProtocol

WS_HOST = os.getenv("ICAR_WS_MQTT_HOST", "0.0.0.0")
WS_PORT = int(os.getenv("ICAR_WS_MQTT_PORT", "9010"))
MQTT_HOST = os.getenv("ICAR_MQTT_HOST", "82.156.132.43")
MQTT_PORT = int(os.getenv("ICAR_MQTT_PORT", "1883"))
MQTT_USER = os.getenv("ICAR_MQTT_USER", "icar")
MQTT_PASS = os.getenv("ICAR_MQTT_PASS", "icar123456")
TOPIC_PREFIX = os.getenv("ICAR_MQTT_TOPIC_PREFIX", "/icar")
DEVICE_ID = os.getenv("ICAR_DEVICE_ID", "")


def _car_topic(suffix: str) -> str:
    """Build a cloud MQTT topic matching the cloud_bridge convention."""
    base = f"{TOPIC_PREFIX}/{DEVICE_ID}" if DEVICE_ID else TOPIC_PREFIX
    return f"{base.rstrip('/')}/{suffix}"


# Topic routing: the bridge subscribes to these car→app MQTT topics and
# forwards payloads to the browser under the browser-side topic name.
CAR_TOPICS = {
    "status": "task_status",
    "nav": "nav_status",
    "pose": "robot_pose",
    "obstacle": "obstacle_status",
    "env": "sensor_env_data",
    "alert": "sensor_alert",
    "alarm": "safety_alarm",
    "log": "task_log",
    "llm/response": "llm_response",
    "llm/report": "generate_report_result",
    "ack": "cloud_ack",
    "online": "robot_online",
    "video_frame": "video_frame",
    "detection": "detections",
    "capture": "capture_status",
    "tracking": "tracking_status",
}
# Browser publishes → the bridge forwards to these car-side MQTT topics.
CMD_TOPICS = {
    "control": "control",
    "cmd": "cmd",
    "llm/command": "llm/command",
    "llm/generate_report": "llm/generate_report",
    "snapshot/request": "snapshot/request",
    "alarm": "alarm",
    "water_toggle": "water_toggle",
    "obstacle_toggle": "obstacle_toggle",
}


class MqttBridge:
    def __init__(self):
        self.client = mqtt.Client(
            client_id=f"ws_bridge_{os.getpid()}",
            callback_api_version=mqtt.CallbackAPIVersion.VERSION2,
        )
        self.client.username_pw_set(MQTT_USER, MQTT_PASS)
        self.client.on_connect = self._on_connect
        self.client.on_message = self._on_message
        self.client.on_disconnect = self._on_disconnect
        self.ws: WebSocketServerProtocol | None = None
        self._loop: asyncio.AbstractEventLoop | None = None
        self._connected = False
        self._subscribed: set[str] = set()

    # ── MQTT lifecycle (called once per process) ──

    def start(self):
        """Start the persistent MQTT connection. Call once at startup."""
        self.client.reconnect_delay_set(min_delay=1, max_delay=10)
        self.client.connect_async(MQTT_HOST, MQTT_PORT, keepalive=15)
        self.client.loop_start()

    def stop(self):
        """Tear down MQTT. Call once at shutdown."""
        self.client.loop_stop()
        self.client.disconnect()

    # ── MQTT callbacks ──

    def _on_connect(self, client, userdata, flags, reason_code, properties=None):
        rc = getattr(reason_code, "value", reason_code)
        if rc == 0:
            self._connected = True
            for topic in self._subscribed:
                client.subscribe(topic, qos=1)
            # Notify the browser that MQTT is now ready
            if self._loop is not None and self.ws is not None:
                asyncio.run_coroutine_threadsafe(
                    self._safe_send({"type": "mqtt_ready"}),
                    self._loop,
                )

    def _on_disconnect(self, client, userdata, flags, reason_code, properties=None):
        self._connected = False

    def _on_message(self, client, userdata, msg):
        if self.ws is None:
            return
        suffix = msg.topic
        prefix = f"{TOPIC_PREFIX}/" if not DEVICE_ID else f"{TOPIC_PREFIX}/{DEVICE_ID}/"
        if suffix.startswith(prefix):
            suffix = suffix[len(prefix):]
        browser_topic = CAR_TOPICS.get(suffix, suffix)

        # Binary payload → base64 encode (video frames)
        if browser_topic == "video_frame":
            data = {"data": base64.b64encode(msg.payload).decode("ascii")}
        else:
            payload_str = msg.payload.decode("utf-8", errors="replace")
            try:
                data = json.loads(payload_str)
            except json.JSONDecodeError:
                data = {"raw": payload_str}

        # paho-mqtt callbacks run in a background thread — use threadsafe API
        if self._loop is not None:
            asyncio.run_coroutine_threadsafe(
                self._safe_send({
                    "type": "message",
                    "topic": browser_topic,
                    "payload": data,
                }),
                self._loop,
            )

    async def _safe_send(self, data: dict):
        if self.ws is None:
            return
        try:
            await self.ws.send(json.dumps(data, ensure_ascii=False))
        except websockets.ConnectionClosed:
            self.ws = None

    # ── Browser API ──

    def subscribe(self, suffix: str):
        topic = _car_topic(suffix)
        # Always subscribe (even if already tracked) so retained messages
        # are delivered to each new browser connection.
        self._subscribed.add(topic)
        if self._connected:
            self.client.subscribe(topic, qos=1)

    def publish(self, suffix: str, payload: dict):
        topic = _car_topic(CMD_TOPICS.get(suffix, f"cmd/{suffix}"))
        data = json.dumps(payload, ensure_ascii=False)
        self.client.publish(topic, data, qos=1)

    async def handle(self, ws: WebSocketServerProtocol):
        self.ws = ws
        self._loop = asyncio.get_running_loop()
        try:
            await ws.send(json.dumps({
                "type": "connected",
                "mqtt": self._connected,
            }))
            async for raw in ws:
                try:
                    msg = json.loads(raw)
                except json.JSONDecodeError:
                    continue
                msg_type = msg.get("type", "")
                if msg_type == "subscribe":
                    for suffix in msg.get("topics", []):
                        self.subscribe(str(suffix))
                elif msg_type == "publish":
                    self.publish(
                        str(msg.get("suffix", "")),
                        msg.get("payload", {}),
                    )
        finally:
            self.ws = None
            # MQTT stays connected — do NOT tear it down here


async def main():
    bridge = MqttBridge()
    bridge.start()  # persistent MQTT connection
    stop = asyncio.Event()

    def _shutdown():
        stop.set()

    loop = asyncio.get_running_loop()
    for sig in (signal.SIGINT, signal.SIGTERM):
        try:
            loop.add_signal_handler(sig, _shutdown)
        except NotImplementedError:
            pass

    async with websockets.serve(
        lambda ws: bridge.handle(ws), WS_HOST, WS_PORT
    ):
        print(
            f"MQTT WebSocket bridge: ws://{WS_HOST}:{WS_PORT}"
            f" → mqtt://{MQTT_HOST}:{MQTT_PORT}"
        )
        await stop.wait()

    bridge.stop()


if __name__ == "__main__":
    asyncio.run(main())
