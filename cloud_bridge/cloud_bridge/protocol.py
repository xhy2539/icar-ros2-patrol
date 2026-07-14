"""Pure-Python helpers for the MQTT protocol used by ``cloud_bridge``.

This module deliberately has no ROS2 or paho-mqtt imports so command handling
can be validated in CI and on development machines without the robot runtime.
"""

from collections import OrderedDict
from dataclasses import dataclass
import json
import math
import threading
import time
from typing import Any, Dict, Optional, Union


class CommandValidationError(ValueError):
    """Raised when an MQTT command must not be forwarded to ROS2."""


@dataclass(frozen=True)
class CloudTopics:
    """MQTT topics for one robot, with legacy topic compatibility."""

    command: str
    control: str
    status: str
    nav: str
    pose: str
    obstacle: str
    environment: str
    alert: str
    log: str
    ack: str
    online: str
    llm_command: str
    llm_generate_report: str
    llm_response: str
    llm_report: str
    snapshot_request: str
    snapshot: str
    alarm: str
    video_frame: str
    detection: str
    capture: str
    tracking: str
    water_toggle: str
    obstacle_toggle: str

    @classmethod
    def build(cls, prefix: str = "/icar", device_id: str = "") -> "CloudTopics":
        normalized_prefix = "/" + prefix.strip().strip("/")
        normalized_device = device_id.strip().strip("/")
        if normalized_prefix == "/" or any(char in normalized_prefix for char in "+#"):
            raise ValueError("MQTT topic prefix 不能为空或包含通配符")
        if normalized_device and any(
            char in normalized_device for char in "/+#"
        ):
            raise ValueError("device_id 不能包含 /、+ 或 #")
        base = (
            f"{normalized_prefix}/{normalized_device}"
            if normalized_device
            else normalized_prefix
        )
        return cls(
            command=f"{base}/cmd",
            control=f"{base}/control",
            status=f"{base}/status",
            nav=f"{base}/nav",
            pose=f"{base}/pose",
            obstacle=f"{base}/obstacle",
            environment=f"{base}/env",
            alert=f"{base}/alert",
            log=f"{base}/log",
            ack=f"{base}/ack",
            online=f"{base}/online",
            llm_command=f"{base}/llm/command",
            llm_generate_report=f"{base}/llm/generate_report",
            llm_response=f"{base}/llm/response",
            llm_report=f"{base}/llm/report",
            snapshot_request=f"{base}/snapshot/request",
            snapshot=f"{base}/snapshot",
            alarm=f"{base}/alarm",
            video_frame=f"{base}/video_frame",
            detection=f"{base}/detection",
            capture=f"{base}/capture",
            tracking=f"{base}/tracking",
            water_toggle=f"{base}/water_toggle",
            obstacle_toggle=f"{base}/obstacle_toggle",
        )


@dataclass(frozen=True)
class TaskCommand:
    action: str
    route: list
    params_json: str
    command_id: str = ""


@dataclass(frozen=True)
class MotionCommand:
    command: str
    linear_x: float
    linear_y: float
    angular_z: float
    lease_seconds: float


@dataclass(frozen=True)
class SnapshotRequest:
    """One short-lived request for a JPEG frame from the robot."""

    request_id: str
    annotated: bool


class RecentCommandIds:
    """Bounded, thread-safe duplicate command detector."""

    def __init__(self, capacity: int = 256):
        if capacity < 1:
            raise ValueError("capacity must be positive")
        self._capacity = capacity
        self._items = OrderedDict()
        self._lock = threading.Lock()

    def seen_or_add(self, command_id: str) -> bool:
        if not command_id:
            return False
        with self._lock:
            if command_id in self._items:
                self._items.move_to_end(command_id)
                return True
            self._items[command_id] = None
            while len(self._items) > self._capacity:
                self._items.popitem(last=False)
            return False


def _finite_timestamp(value: Any, field_name: str) -> Optional[float]:
    if value is None:
        return None
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise CommandValidationError(f"{field_name} 必须是 Unix 时间戳")
    timestamp = float(value)
    if not math.isfinite(timestamp) or timestamp < 0:
        raise CommandValidationError(f"{field_name} 不是有效时间戳")
    return timestamp


def parse_task_command(
    payload: Union[str, bytes],
    *,
    now: Optional[float] = None,
    max_payload_bytes: int = 16 * 1024,
    max_route_points: int = 32,
) -> TaskCommand:
    """Validate an MQTT patrol command and normalize it for ``TaskRequest``."""

    if isinstance(payload, bytes):
        raw_bytes = payload
        try:
            payload_text = payload.decode("utf-8")
        except UnicodeDecodeError as exc:
            raise CommandValidationError("指令不是有效 UTF-8") from exc
    elif isinstance(payload, str):
        payload_text = payload
        raw_bytes = payload.encode("utf-8")
    else:
        raise CommandValidationError("指令必须是字符串或字节数据")

    if not raw_bytes:
        raise CommandValidationError("指令为空")
    if len(raw_bytes) > max_payload_bytes:
        raise CommandValidationError(
            f"指令超过大小限制 ({len(raw_bytes)} > {max_payload_bytes} bytes)"
        )

    try:
        data = json.loads(payload_text)
    except json.JSONDecodeError as exc:
        raise CommandValidationError("指令不是有效 JSON") from exc
    if not isinstance(data, dict):
        raise CommandValidationError("指令 JSON 顶层必须是对象")

    raw_action = data.get("action", "")
    if not isinstance(raw_action, str):
        raise CommandValidationError("action 必须是字符串")
    action = raw_action.strip().lower()
    if action not in ("start", "patrol", "巡检"):
        raise CommandValidationError(f"不支持的 action: {raw_action!r}")

    route = data.get("route", ["A", "B", "C"])
    if not isinstance(route, list) or not route:
        raise CommandValidationError("route 必须是非空数组")
    if len(route) > max_route_points:
        raise CommandValidationError(
            f"route 巡检点过多 ({len(route)} > {max_route_points})"
        )
    normalized_route = []
    for index, point in enumerate(route):
        if not isinstance(point, str):
            raise CommandValidationError(f"route[{index}] 必须是字符串")
        normalized_point = point.strip()
        if not normalized_point or len(normalized_point) > 64:
            raise CommandValidationError(f"route[{index}] 长度无效")
        if any(ord(char) < 32 for char in normalized_point):
            raise CommandValidationError(f"route[{index}] 包含控制字符")
        normalized_route.append(normalized_point)

    params = data.get("params", {})
    if isinstance(params, dict):
        params_json = json.dumps(params, ensure_ascii=False, separators=(",", ":"))
    elif isinstance(params, str):
        params_json = params
    else:
        raise CommandValidationError("params 必须是 JSON 对象或字符串")
    if len(params_json.encode("utf-8")) > 8 * 1024:
        raise CommandValidationError("params 超过 8 KiB 限制")

    command_id = data.get("command_id", "")
    if command_id is None:
        command_id = ""
    if not isinstance(command_id, str):
        raise CommandValidationError("command_id 必须是字符串")
    command_id = command_id.strip()
    if len(command_id) > 128:
        raise CommandValidationError("command_id 超过 128 字符限制")

    current_time = time.time() if now is None else float(now)
    issued_at = _finite_timestamp(data.get("issued_at"), "issued_at")
    expires_at = _finite_timestamp(data.get("expires_at"), "expires_at")
    if issued_at is not None and issued_at > current_time + 300:
        raise CommandValidationError("issued_at 超前超过 5 分钟")
    if expires_at is not None and expires_at < current_time:
        raise CommandValidationError("指令已过期")
    if issued_at is not None and expires_at is not None and expires_at < issued_at:
        raise CommandValidationError("expires_at 早于 issued_at")

    return TaskCommand(
        action="patrol",
        route=normalized_route,
        params_json=params_json,
        command_id=command_id,
    )


def parse_motion_command(
    payload: Union[str, bytes],
    *,
    now_ms: Optional[int] = None,
    max_linear: float = 0.35,
    max_angular: float = 1.2,
) -> MotionCommand:
    """Validate one short-lived remote motion lease."""

    if isinstance(payload, bytes):
        try:
            text = payload.decode("utf-8")
        except UnicodeDecodeError as exc:
            raise CommandValidationError("方向指令不是有效 UTF-8") from exc
    elif isinstance(payload, str):
        text = payload
    else:
        raise CommandValidationError("方向指令必须是字符串或字节数据")
    if len(text.encode("utf-8")) > 2048:
        raise CommandValidationError("方向指令超过 2 KiB 限制")

    try:
        data = json.loads(text)
    except json.JSONDecodeError as exc:
        raise CommandValidationError("方向指令不是有效 JSON") from exc
    if not isinstance(data, dict):
        raise CommandValidationError("方向指令 JSON 顶层必须是对象")

    command = data.get("command", "")
    if not isinstance(command, str):
        raise CommandValidationError("command 必须是字符串")
    command = command.strip().lower()
    allowed = {
        "forward",
        "backward",
        "left",
        "right",
        "turn_left",
        "turn_right",
        "stop",
    }
    if command not in allowed:
        raise CommandValidationError(f"不支持的方向指令: {command!r}")

    speed = data.get("speed", 0.5)
    if isinstance(speed, bool) or not isinstance(speed, (int, float)):
        raise CommandValidationError("speed 必须是 0.0~1.0 的数字")
    speed = float(speed)
    if not math.isfinite(speed) or not 0.0 <= speed <= 1.0:
        raise CommandValidationError("speed 必须在 0.0~1.0 范围内")

    lease_ms = data.get("lease_ms", 1000)
    if isinstance(lease_ms, bool) or not isinstance(lease_ms, (int, float)):
        raise CommandValidationError("lease_ms 必须是数字")
    lease_ms = int(lease_ms)
    if not 100 <= lease_ms <= 5000:
        raise CommandValidationError("lease_ms 必须在 100~5000ms 范围内")

    issued_at_ms = data.get("issued_at_ms")
    if isinstance(issued_at_ms, bool) or not isinstance(issued_at_ms, (int, float)):
        raise CommandValidationError("issued_at_ms 必须是 Unix 毫秒时间戳")
    current_ms = int(time.time() * 1000) if now_ms is None else int(now_ms)
    age_ms = current_ms - int(issued_at_ms)
    if age_ms > 10000:
        raise CommandValidationError("方向指令已过期")
    if age_ms < -5000:
        raise CommandValidationError("方向指令时间戳超前超过 5 秒")

    linear = max_linear * speed
    angular = max_angular * speed
    vectors = {
        "forward": (linear, 0.0, 0.0),
        "backward": (-linear, 0.0, 0.0),
        "left": (0.0, linear, 0.0),
        "right": (0.0, -linear, 0.0),
        "turn_left": (0.0, 0.0, angular),
        "turn_right": (0.0, 0.0, -angular),
        "stop": (0.0, 0.0, 0.0),
    }
    linear_x, linear_y, angular_z = vectors[command]
    return MotionCommand(
        command=command,
        linear_x=linear_x,
        linear_y=linear_y,
        angular_z=angular_z,
        lease_seconds=lease_ms / 1000.0,
    )


def parse_snapshot_request(
    payload: Union[str, bytes],
    *,
    now: Optional[float] = None,
    max_payload_bytes: int = 2048,
) -> SnapshotRequest:
    """Validate an on-demand cloud snapshot request.

    Snapshot requests are intentionally small and short-lived. The response is
    produced from the loopback-only ROS MJPEG service, so callers can select
    only the raw or annotated frame and cannot provide an arbitrary URL/path.
    """

    if isinstance(payload, bytes):
        raw_bytes = payload
        try:
            payload_text = payload.decode("utf-8")
        except UnicodeDecodeError as exc:
            raise CommandValidationError("截图请求不是有效 UTF-8") from exc
    elif isinstance(payload, str):
        payload_text = payload
        raw_bytes = payload.encode("utf-8")
    else:
        raise CommandValidationError("截图请求必须是字符串或字节数据")

    if not raw_bytes or len(raw_bytes) > max_payload_bytes:
        raise CommandValidationError("截图请求为空或超过大小限制")
    try:
        data = json.loads(payload_text)
    except json.JSONDecodeError as exc:
        raise CommandValidationError("截图请求不是有效 JSON") from exc
    if not isinstance(data, dict):
        raise CommandValidationError("截图请求 JSON 顶层必须是对象")

    request_id = data.get("request_id", "")
    if not isinstance(request_id, str):
        raise CommandValidationError("request_id 必须是字符串")
    request_id = request_id.strip()
    if not request_id or len(request_id) > 128:
        raise CommandValidationError("request_id 不能为空或超过 128 字符")
    if any(ord(char) < 32 for char in request_id):
        raise CommandValidationError("request_id 包含控制字符")

    annotated = data.get("annotated", False)
    if not isinstance(annotated, bool):
        raise CommandValidationError("annotated 必须是布尔值")

    current_time = time.time() if now is None else float(now)
    issued_at = _finite_timestamp(data.get("issued_at"), "issued_at")
    expires_at = _finite_timestamp(data.get("expires_at"), "expires_at")
    if issued_at is not None and issued_at > current_time + 300:
        raise CommandValidationError("issued_at 超前超过 5 分钟")
    if expires_at is not None and expires_at < current_time:
        raise CommandValidationError("截图请求已过期")
    if issued_at is not None and expires_at is not None and expires_at < issued_at:
        raise CommandValidationError("expires_at 早于 issued_at")

    return SnapshotRequest(request_id=request_id, annotated=annotated)


def command_ack(command_id: str, accepted: bool, message: str) -> Dict[str, Any]:
    """Build the small acknowledgement payload returned to the cloud."""

    return {
        "command_id": command_id,
        "accepted": accepted,
        "message": message,
        "timestamp": int(time.time()),
    }
