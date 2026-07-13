import json
import math
import socket
import threading
import time
import uuid
from datetime import datetime

import rclpy
from geometry_msgs.msg import PoseStamped, Twist
from icar_interfaces.msg import (
    DetectionArray,
    EnvData,
    NavStatus,
    ObstacleStatus,
    SensorAlert,
    TaskLog,
    TaskRequest,
    TaskStatus,
)
from icar_interfaces.srv import GenerateReport, ParseTask
from rclpy.node import Node
from std_msgs.msg import Bool, String

from .command_parser import Motion, is_emergency_stop_text, parse_command


class AppBridgeNode(Node):
    """Bidirectional TCP bridge between the web gateway and ROS 2.

    Motion is published only to /cmd_vel_app. Other accepted APP messages are
    explicitly routed to their ROS topics. ROS status is serialized as one JSON
    object per line and sent back through every subscribed gateway connection.
    """

    def __init__(self) -> None:
        super().__init__("app_bridge")
        self.declare_parameter("listen_host", "0.0.0.0")
        self.declare_parameter("listen_port", 6501)
        self.declare_parameter("output_topic", "/cmd_vel_app")
        self.declare_parameter("command_timeout_sec", 0.35)
        self.declare_parameter("max_linear", 0.35)
        self.declare_parameter("max_angular", 1.2)

        self._timeout = float(self.get_parameter("command_timeout_sec").value)
        self._max_linear = float(self.get_parameter("max_linear").value)
        self._max_angular = float(self.get_parameter("max_angular").value)
        self._motion_publisher = self.create_publisher(
            Twist, str(self.get_parameter("output_topic").value), 10
        )
        self._goal_publisher = self.create_publisher(PoseStamped, "/goal_pose", 10)
        self._tracking_publisher = self.create_publisher(
            String, "/vision/target_tracking/command", 10
        )
        self._task_publisher = self.create_publisher(
            TaskRequest, "/task/request", 10
        )
        self._capture_publisher = self.create_publisher(
            String, "/vision/capture_command", 10
        )
        self._llm_command_publisher = self.create_publisher(
            String, "/llm/user_command", 10
        )
        self._safety_stop_publisher = self.create_publisher(
            Bool, "/safety_stop", 10
        )
        self._parse_task_client = self.create_client(ParseTask, "/llm/parse_task")
        self._report_client = self.create_client(
            GenerateReport, "/llm/generate_report"
        )

        self.create_subscription(
            ObstacleStatus, "/obstacle_status", self._on_obstacle, 10
        )
        self.create_subscription(NavStatus, "/nav_status", self._on_nav, 10)
        self.create_subscription(
            TaskStatus, "/task/status", self._on_task_status, 10
        )
        self.create_subscription(TaskLog, "/task/log", self._on_task_log, 10)
        self.create_subscription(EnvData, "/sensor/env_data", self._on_env, 10)
        self.create_subscription(
            SensorAlert, "/sensor/alert", self._on_alert, 10
        )
        self.create_subscription(
            DetectionArray, "/vision/detections", self._on_detections, 10
        )
        self.create_subscription(
            String,
            "/vision/capture_status",
            lambda msg: self._on_json_string("capture_status", msg),
            10,
        )
        self.create_subscription(
            String,
            "/vision/target_tracking/status",
            lambda msg: self._on_json_string("tracking_status", msg),
            10,
        )
        self.create_subscription(
            String, "/llm/response", self._on_llm_response, 10
        )

        self._motion = Motion(0.0, 0.0, 0.0)
        self._last_command = 0.0
        self._active = False
        self._control_owner = None
        self._motion_lock = threading.Lock()

        # socket -> {"lock": Lock, "subscriptions": set[str]}
        self._clients = {}
        self._clients_lock = threading.Lock()
        self._shutdown = threading.Event()
        self.create_timer(0.05, self._publish_tick)
        threading.Thread(target=self._serve, daemon=True).start()

    def _serve(self) -> None:
        host = str(self.get_parameter("listen_host").value)
        port = int(self.get_parameter("listen_port").value)
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as server:
            server.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            server.bind((host, port))
            server.listen(8)
            server.settimeout(0.5)
            self.get_logger().info(f"bidirectional app TCP listening on {host}:{port}")
            while rclpy.ok() and not self._shutdown.is_set():
                try:
                    client, address = server.accept()
                except socket.timeout:
                    continue
                threading.Thread(
                    target=self._handle_client, args=(client, address), daemon=True
                ).start()

    def _handle_client(self, client: socket.socket, address) -> None:
        self.get_logger().info(f"app client connected: {address}")
        state = {"lock": threading.Lock(), "subscriptions": set()}
        with self._clients_lock:
            self._clients[client] = state
        buffer = b""
        client.settimeout(0.5)
        try:
            while rclpy.ok() and not self._shutdown.is_set():
                try:
                    chunk = client.recv(4096)
                except socket.timeout:
                    continue
                if not chunk:
                    break
                buffer += chunk
                while b"\n" in buffer:
                    line, buffer = buffer.split(b"\n", 1)
                    self._handle_line(
                        client, line.decode("utf-8", errors="replace").strip()
                    )
        except OSError as exc:
            self.get_logger().warning(f"app client error {address}: {exc}")
        finally:
            with self._clients_lock:
                self._clients.pop(client, None)
            with self._motion_lock:
                owns_control = self._control_owner is client
            if owns_control:
                self._stop_now()
            try:
                client.close()
            except OSError:
                pass
            self.get_logger().info(
                f"app client disconnected: {address}; "
                f"control_stopped={owns_control}"
            )

    def _handle_line(self, client: socket.socket, raw: str) -> None:
        if not raw:
            return
        data = None
        if raw.startswith("{"):
            try:
                data = json.loads(raw)
            except json.JSONDecodeError as exc:
                self._send(client, {"topic": "error", "error": f"invalid JSON: {exc}"})
                return
            if not isinstance(data, dict):
                self._send(client, {"topic": "error", "error": "JSON must be an object"})
                return

            subscription = data.get("subscribe")
            if subscription:
                with self._clients_lock:
                    state = self._clients.get(client)
                    if state is not None:
                        state["subscriptions"].add(str(subscription))
                self._send(
                    client,
                    {"topic": "subscription", "subscribed": str(subscription)},
                )
                return

            action = str(data.get("action", ""))
            if action == "goal_pose":
                self._publish_goal(client, data)
                return
            if action == "tracking":
                self._publish_tracking(client, data)
                return
            if action == "task_request":
                self._publish_task(client, data)
                return
            if action in ("capture_once", "set_interval", "set_max_images", "stop"):
                self._publish_capture(client, data)
                return
            if action == "parse_task":
                self._call_parse_task(client, data)
                return
            if action == "generate_report":
                self._call_generate_report(client, data)
                return
            if action == "llm_command":
                self._publish_llm_command(client, data)
                return
            if action and "command" not in data and "direction" not in data:
                self._send(
                    client,
                    {"topic": "error", "error": f"unsupported action: {action}"},
                )
                return

        self._apply_motion(client, raw)

    def _apply_motion(self, client: socket.socket, raw: str) -> None:
        try:
            motion = parse_command(raw, self._max_linear, self._max_angular)
        except (ValueError, TypeError, json.JSONDecodeError) as exc:
            self.get_logger().warning(f"rejected control command: {exc}")
            self._send(client, {"topic": "error", "error": str(exc)})
            return
        with self._motion_lock:
            self._motion = motion
            self._last_command = time.monotonic()
            self._active = True
            self._control_owner = client

    def _publish_goal(self, client: socket.socket, data: dict) -> None:
        try:
            x = float(data["x"])
            y = float(data["y"])
            yaw = float(data.get("yaw", 0.0))
        except (KeyError, TypeError, ValueError):
            self._send(client, {"topic": "error", "error": "goal_pose requires numeric x/y/yaw"})
            return
        pose = PoseStamped()
        pose.header.stamp = self.get_clock().now().to_msg()
        pose.header.frame_id = str(data.get("frame_id", "map"))
        pose.pose.position.x = x
        pose.pose.position.y = y
        pose.pose.orientation.z = math.sin(yaw / 2.0)
        pose.pose.orientation.w = math.cos(yaw / 2.0)
        self._goal_publisher.publish(pose)
        self._send(client, {"topic": "command_ack", "action": "goal_pose", "ok": True})

    def _publish_tracking(self, client: socket.socket, data: dict) -> None:
        command = str(data.get("command", ""))
        if command not in ("start", "stop"):
            self._send(client, {"topic": "error", "error": "tracking command must be start/stop"})
            return
        payload = {"action": command}
        if command == "start":
            classes = data.get("target_classes", ["person"])
            if not isinstance(classes, list):
                self._send(client, {"topic": "error", "error": "target_classes must be a list"})
                return
            payload["target_classes"] = [str(item) for item in classes]
        message = String()
        message.data = json.dumps(payload, ensure_ascii=False)
        self._tracking_publisher.publish(message)
        self._send(client, {"topic": "command_ack", "action": "tracking", "ok": True})

    def _publish_task(self, client: socket.socket, data: dict) -> None:
        task = data.get("task", data)
        if not isinstance(task, dict):
            self._send(client, {"topic": "error", "error": "task must be an object"})
            return
        task_type = str(task.get("task_type", ""))
        route = task.get("route", [])
        if not task_type or not isinstance(route, list):
            self._send(client, {"topic": "error", "error": "task_type and route[] are required"})
            return
        message = TaskRequest()
        message.task_type = task_type
        message.route = [str(point) for point in route]
        params = task.get("params", {})
        message.params = params if isinstance(params, str) else json.dumps(params, ensure_ascii=False)
        self._task_publisher.publish(message)
        self._send(client, {"topic": "command_ack", "action": "task_request", "ok": True})

    def _publish_capture(self, client: socket.socket, data: dict) -> None:
        message = String()
        message.data = json.dumps(data, ensure_ascii=False)
        self._capture_publisher.publish(message)
        self._send(client, {"topic": "command_ack", "action": data["action"], "ok": True})

    def _publish_llm_command(self, client: socket.socket, data: dict) -> None:
        """Forward one natural-language command to the executable LLM gateway."""
        input_text = str(data.get("input_text", "")).strip()
        if not input_text:
            self._send(
                client,
                {
                    "topic": "llm_response",
                    "success": False,
                    "error_msg": "input_text is required",
                },
            )
            return
        if len(input_text) > 1000:
            self._send(
                client,
                {
                    "topic": "llm_response",
                    "success": False,
                    "error_msg": "input_text is too long (max 1000 characters)",
                },
            )
            return

        request_id = str(data.get("request_id", "")).strip() or uuid.uuid4().hex
        if is_emergency_stop_text(input_text):
            # Do not wait for a model or even for llm_gateway availability.
            self._stop_now()
            self._safety_stop_publisher.publish(Bool(data=True))
            self._send(
                client,
                {
                    "topic": "command_ack",
                    "action": "emergency_stop",
                    "request_id": request_id,
                    "ok": True,
                },
            )
        message = String()
        message.data = json.dumps(
            {
                "request_id": request_id,
                "input_text": input_text,
                "source": "app",
            },
            ensure_ascii=False,
        )
        self._llm_command_publisher.publish(message)
        self._send(
            client,
            {
                "topic": "command_ack",
                "action": "llm_command",
                "request_id": request_id,
                "ok": True,
            },
        )

    def _call_parse_task(self, client: socket.socket, data: dict) -> None:
        text = str(data.get("input_text", "")).strip()
        if not text:
            self._send(client, {"topic": "parse_task_result", "success": False, "error_msg": "input_text is required"})
            return
        if not self._parse_task_client.service_is_ready():
            self._send(client, {"topic": "parse_task_result", "success": False, "error_msg": "/llm/parse_task unavailable"})
            return
        request = ParseTask.Request()
        request.input_text = text
        future = self._parse_task_client.call_async(request)
        future.add_done_callback(lambda result: self._finish_parse_task(client, result))

    def _finish_parse_task(self, client: socket.socket, future) -> None:
        try:
            response = future.result()
            payload = {
                "topic": "parse_task_result",
                "task_json": response.task_json,
                "success": bool(response.success),
                "error_msg": response.error_msg,
            }
        except Exception as exc:
            payload = {"topic": "parse_task_result", "success": False, "error_msg": str(exc)}
        self._send(client, payload)

    def _call_generate_report(self, client: socket.socket, data: dict) -> None:
        if not self._report_client.service_is_ready():
            self._send(client, {"topic": "generate_report_result", "success": False, "error_msg": "/llm/generate_report unavailable"})
            return
        request = GenerateReport.Request()
        request.task_id = str(data.get("task_id", ""))
        logs = data.get("logs", data.get("logs_json", ""))
        request.logs_json = logs if isinstance(logs, str) else json.dumps(logs, ensure_ascii=False)
        future = self._report_client.call_async(request)
        future.add_done_callback(lambda result: self._finish_generate_report(client, result))

    def _finish_generate_report(self, client: socket.socket, future) -> None:
        try:
            response = future.result()
            payload = {
                "topic": "generate_report_result",
                "report_text": response.report_text,
                "success": bool(response.success),
                "error_msg": response.error_msg,
            }
        except Exception as exc:
            payload = {"topic": "generate_report_result", "success": False, "error_msg": str(exc)}
        self._send(client, payload)

    def _send(self, client: socket.socket, payload: dict) -> None:
        with self._clients_lock:
            state = self._clients.get(client)
        if state is None:
            return
        line = json.dumps(payload, ensure_ascii=False, separators=(",", ":")) + "\n"
        try:
            with state["lock"]:
                client.sendall(line.encode("utf-8"))
        except OSError:
            pass

    def _broadcast(self, topic: str, payload: dict) -> None:
        payload["topic"] = topic
        with self._clients_lock:
            clients = list(self._clients.items())
        for client, state in clients:
            subscriptions = state["subscriptions"]
            if subscriptions and topic not in subscriptions:
                continue
            self._send(client, payload)

    def _on_obstacle(self, msg: ObstacleStatus) -> None:
        self._broadcast("obstacle_status", {
            "is_obstacle": bool(msg.is_obstacle),
            "min_distance": float(msg.min_distance),
            "direction": msg.direction,
            "risk_level": msg.risk_level,
            "action": msg.action,
        })

    def _on_nav(self, msg: NavStatus) -> None:
        self._broadcast("nav_status", {
            "status": msg.status,
            "progress": float(msg.progress),
            "distance_remain": float(msg.distance_remain),
            "message": msg.message,
        })

    def _on_task_status(self, msg: TaskStatus) -> None:
        self._broadcast("task_status", {
            "task_id": msg.task_id,
            "status": msg.status,
            "current_step": int(msg.current_step),
            "total_steps": int(msg.total_steps),
            "message": msg.message,
        })

    def _on_task_log(self, msg: TaskLog) -> None:
        timestamp = datetime.fromtimestamp(msg.timestamp.sec).strftime("%Y-%m-%d %H:%M:%S")
        self._broadcast("task_log", {
            "task_id": msg.task_id,
            "timestamp": timestamp,
            "event_type": msg.event_type,
            "data_json": msg.data_json,
            "severity": msg.severity,
        })

    def _on_env(self, msg: EnvData) -> None:
        self._broadcast("sensor_env_data", {
            "temperature": float(msg.temperature),
            "humidity": float(msg.humidity),
            "smoke": float(msg.smoke),
            "pm25": float(msg.pm25),
            "light": float(msg.light),
            "pressure": float(msg.pressure),
        })

    def _on_alert(self, msg: SensorAlert) -> None:
        self._broadcast("sensor_alert", {
            "sensor_type": msg.sensor_type,
            "current_value": float(msg.current_value),
            "threshold": float(msg.threshold),
            "severity": msg.severity,
            "message": msg.message,
        })

    def _on_detections(self, msg: DetectionArray) -> None:
        self._broadcast("detections", {
            "detections": [
                {
                    "class_name": item.class_name,
                    "confidence": float(item.confidence),
                    "x_min": int(item.x_min),
                    "y_min": int(item.y_min),
                    "x_max": int(item.x_max),
                    "y_max": int(item.y_max),
                    "image_path": item.image_path,
                }
                for item in msg.detections
            ]
        })

    def _on_json_string(self, topic: str, msg: String) -> None:
        try:
            payload = json.loads(msg.data)
            if not isinstance(payload, dict):
                payload = {"data": payload}
        except json.JSONDecodeError:
            payload = {"raw": msg.data}
        self._broadcast(topic, payload)

    def _on_llm_response(self, msg: String) -> None:
        try:
            payload = json.loads(msg.data)
            if not isinstance(payload, dict):
                payload = {"success": True, "data": payload}
        except json.JSONDecodeError:
            payload = {"success": True, "message": msg.data}
        self._broadcast("llm_response", payload)

    def _stop_now(self) -> None:
        with self._motion_lock:
            self._motion = Motion(0.0, 0.0, 0.0)
            self._last_command = 0.0
            self._active = False
            self._control_owner = None
        self._motion_publisher.publish(Twist())

    def _publish_tick(self) -> None:
        with self._motion_lock:
            if not self._active:
                return
            motion = self._motion
            if time.monotonic() - self._last_command > self._timeout:
                motion = Motion(0.0, 0.0, 0.0)
                self._motion = motion
                self._active = False
                self._control_owner = None
        message = Twist()
        message.linear.x = motion.x
        message.linear.y = motion.y
        message.angular.z = motion.z
        self._motion_publisher.publish(message)

    def destroy_node(self):
        self._shutdown.set()
        self._stop_now()
        with self._clients_lock:
            clients = list(self._clients)
        for client in clients:
            try:
                client.shutdown(socket.SHUT_RDWR)
            except OSError:
                pass
        return super().destroy_node()


def main(args=None) -> None:
    rclpy.init(args=args)
    node = AppBridgeNode()
    try:
        rclpy.spin(node)
    except KeyboardInterrupt:
        pass
    finally:
        node.destroy_node()
        rclpy.shutdown()
