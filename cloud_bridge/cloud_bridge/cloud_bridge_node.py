#!/usr/bin/env python3
"""
cloud_bridge_node.py — MQTT ↔ ROS2 桥接节点

连接云服务器 MQTT Broker，把 ROS2 Topic 数据发到云端，
同时接收云端指令转成 ROS2 Topic。

Topic 映射:
  手机→MQTT→ROS2:
    /icar/cmd → /task/request (TaskRequest)
    /icar/llm/command → /llm/user_command (String)
    /icar/llm/generate_report → /llm/generate_report (Service)
  小车→ROS2→MQTT→手机:
    /task/status  → /icar/status
    /sensor/alert → /icar/alert
    /task/log     → /icar/log
    /llm/response → /icar/llm/response
"""

import json
import base64
import http.client
import os
import ssl
import threading
import time

import rclpy
from rclpy.node import Node
from rclpy.qos import QoSProfile, ReliabilityPolicy
from std_msgs.msg import String as ROSString
from geometry_msgs.msg import PoseStamped, Twist

from icar_interfaces.msg import (
    EnvData,
    NavStatus,
    ObstacleStatus,
    SensorAlert,
    TaskLog,
    TaskRequest,
    TaskStatus,
)
from icar_interfaces.srv import GenerateReport

from cloud_bridge.protocol import (
    CloudTopics,
    CommandValidationError,
    RecentCommandIds,
    command_ack,
    parse_motion_command,
    parse_snapshot_request,
    parse_task_command,
)

try:
    import paho.mqtt.client as mqtt
except ImportError:
    mqtt = None


class CloudBridgeNode(Node):
    def __init__(self):
        super().__init__("cloud_bridge_node")

        # ── 参数 ──
        self.declare_parameter("mqtt_host", os.getenv("ICAR_MQTT_HOST", "82.156.132.43"))
        self.declare_parameter("mqtt_port", int(os.getenv("ICAR_MQTT_PORT", "1883")))
        self.declare_parameter("mqtt_user", os.getenv("ICAR_MQTT_USER", "icar"))
        self.declare_parameter("mqtt_pass", os.getenv("ICAR_MQTT_PASS", "icar123456"))
        self.declare_parameter("mqtt_tls", os.getenv("ICAR_MQTT_TLS", "0") == "1")
        self.declare_parameter("mqtt_ca_cert", os.getenv("ICAR_MQTT_CA_CERT", ""))
        self.declare_parameter("mqtt_tls_insecure", False)
        self.declare_parameter("mqtt_keepalive", 60)
        self.declare_parameter("mqtt_qos", 1)
        self.declare_parameter("topic_prefix", os.getenv("ICAR_MQTT_TOPIC_PREFIX", "/icar"))
        self.declare_parameter("device_id", os.getenv("ICAR_DEVICE_ID", ""))
        self.declare_parameter("max_command_bytes", 16 * 1024)
        self.declare_parameter("cloud_cmd_vel_topic", "/cmd_vel_cloud")
        self.declare_parameter("max_linear", 0.35)
        self.declare_parameter("max_angular", 1.2)
        self.declare_parameter("telemetry_interval_sec", 0.5)
        self.declare_parameter(
            "snapshot_host", os.getenv("ICAR_ROS_VIDEO_HOST", "127.0.0.1")
        )
        self.declare_parameter(
            "snapshot_port", int(os.getenv("ICAR_ROS_VIDEO_PORT", "6502"))
        )
        self.declare_parameter("snapshot_timeout_sec", 2.0)
        self.declare_parameter("snapshot_max_bytes", 512 * 1024)
        self.declare_parameter("snapshot_min_interval_sec", 1.0)
        self.declare_parameter("enable", True)

        self.enable = self.get_parameter("enable").value
        if not self.enable:
            self.get_logger().info("cloud_bridge 已禁用")
            return

        if mqtt is None:
            self.get_logger().error("paho-mqtt 未安装，cloud_bridge 不可用")
            return

        host = self.get_parameter("mqtt_host").value
        port = self.get_parameter("mqtt_port").value
        user = self.get_parameter("mqtt_user").value
        pw = self.get_parameter("mqtt_pass").value
        self.mqtt_qos = int(self.get_parameter("mqtt_qos").value)
        self.max_command_bytes = int(self.get_parameter("max_command_bytes").value)
        self.topics = CloudTopics.build(
            self.get_parameter("topic_prefix").value,
            self.get_parameter("device_id").value,
        )
        self._recent_commands = RecentCommandIds()
        self._mqtt_connected = False
        self._report_future = None
        self._motion_lock = threading.Lock()
        self._motion = (0.0, 0.0, 0.0)
        self._motion_deadline = 0.0
        self._motion_active = False
        self._last_telemetry_publish = {}
        self._latest_pose = {"x": 0.0, "y": 0.0, "frame_id": "map"}
        self._recent_snapshot_requests = RecentCommandIds(capacity=64)
        self._snapshot_lock = threading.Lock()
        self._last_snapshot_started = 0.0

        # ── QoS ──
        qos = QoSProfile(depth=10, reliability=ReliabilityPolicy.RELIABLE)

        # ── ROS2 订阅：车 → 云 ──
        self.create_subscription(TaskStatus, "/task/status", self._on_status, qos)
        self.create_subscription(SensorAlert, "/sensor/alert", self._on_alert, qos)
        self.create_subscription(TaskLog, "/task/log", self._on_log, qos)
        self.create_subscription(
            ROSString, "/safety/alarm", self._on_safety_alarm, qos
        )
        self.create_subscription(ROSString, "/llm/response", self._on_llm_response, qos)
        self.create_subscription(NavStatus, "/nav_status", self._on_nav_status, qos)
        self.create_subscription(PoseStamped, "/pose", self._on_pose, qos)
        self.create_subscription(
            ObstacleStatus, "/obstacle_status", self._on_obstacle_status, qos
        )
        self.create_subscription(EnvData, "/sensor/env_data", self._on_env_data, qos)

        # ── ROS2 发布：云 → 车 ──
        self.task_pub = self.create_publisher(TaskRequest, "/task/request", qos)
        self.llm_command_pub = self.create_publisher(ROSString, "/llm/user_command", qos)
        self.cloud_cmd_vel_pub = self.create_publisher(
            Twist, self.get_parameter("cloud_cmd_vel_topic").value, qos
        )
        self.report_client = self.create_client(GenerateReport, "/llm/generate_report")
        self.create_timer(0.05, self._publish_cloud_motion)

        # ── MQTT ──
        self.mqtt = self._create_mqtt_client()
        if user:
            self.mqtt.username_pw_set(user, pw)
        self.mqtt.reconnect_delay_set(min_delay=1, max_delay=30)
        self.mqtt.on_connect = self._on_mqtt_connect
        self.mqtt.on_disconnect = self._on_mqtt_disconnect
        self.mqtt.on_message = self._on_mqtt_message

        if self.get_parameter("mqtt_tls").value:
            ca_cert = self.get_parameter("mqtt_ca_cert").value or None
            self.mqtt.tls_set(ca_certs=ca_cert, tls_version=ssl.PROTOCOL_TLS_CLIENT)
            if self.get_parameter("mqtt_tls_insecure").value:
                self.get_logger().warn("MQTT TLS 主机名校验已禁用，仅限临时调试")
                self.mqtt.tls_insecure_set(True)

        self.mqtt.will_set(
            self.topics.online,
            json.dumps({"online": False}, ensure_ascii=False),
            qos=self.mqtt_qos,
            retain=True,
        )

        # connect_async + loop_start 都是非阻塞调用，paho 自己管理网络线程。
        self._mqtt_connect()

        self.get_logger().info(
            f"cloud_bridge 启动: {host}:{port} (user={user}, cmd={self.topics.command})"
        )

    @staticmethod
    def _create_mqtt_client():
        """Support both paho-mqtt 1.x and 2.x during the migration period."""
        try:
            return mqtt.Client(mqtt.CallbackAPIVersion.VERSION2)
        except (AttributeError, TypeError):
            return mqtt.Client()

    # ── MQTT 连接 ──
    def _mqtt_connect(self):
        host = self.get_parameter("mqtt_host").value
        port = self.get_parameter("mqtt_port").value
        try:
            keepalive = int(self.get_parameter("mqtt_keepalive").value)
            self.mqtt.connect_async(host, port, keepalive)
            self.mqtt.loop_start()
        except Exception as e:
            self.get_logger().error(f"MQTT 连接失败: {e}")

    def _on_mqtt_connect(self, client, userdata, flags, rc, props=None):
        result_code = getattr(rc, "value", rc)
        if result_code == 0:
            self._mqtt_connected = True
            self.get_logger().info("MQTT 已连接")
            client.subscribe(self.topics.command, qos=self.mqtt_qos)
            client.subscribe(self.topics.control, qos=self.mqtt_qos)
            client.subscribe(self.topics.llm_command, qos=self.mqtt_qos)
            client.subscribe(self.topics.llm_generate_report, qos=self.mqtt_qos)
            client.subscribe(self.topics.snapshot_request, qos=self.mqtt_qos)
            client.publish(
                self.topics.online,
                json.dumps({"online": True}, ensure_ascii=False),
                qos=self.mqtt_qos,
                retain=True,
            )
        else:
            self.get_logger().error(f"MQTT 连接错误: rc={rc}")

    def _on_mqtt_disconnect(self, client, userdata, *args):
        self._mqtt_connected = False
        self._stop_cloud_motion("MQTT 断线")
        self.get_logger().warn("MQTT 连接已断开，客户端将自动重连")

    # ── 云 → 车：收到手机指令 ──
    def _on_mqtt_message(self, client, userdata, msg):
        payload = msg.payload
        if msg.topic != self.topics.control:
            self.get_logger().info(f"[云→车] {msg.topic}: {len(payload)} bytes")

        try:
            if len(payload) > self.max_command_bytes:
                raise CommandValidationError("指令超过大小限制")

            if msg.topic == self.topics.control:
                motion = parse_motion_command(
                    payload,
                    max_linear=float(self.get_parameter("max_linear").value),
                    max_angular=float(self.get_parameter("max_angular").value),
                )
                self._apply_cloud_motion(motion)

            elif msg.topic == self.topics.llm_command:
                data = json.loads(payload.decode("utf-8"))
                if not isinstance(data, dict):
                    raise CommandValidationError("LLM 指令 JSON 顶层必须是对象")
                text = data.get("text", "")
                if isinstance(text, str) and 0 < len(text) <= 4096:
                    cmd_msg = ROSString()
                    cmd_msg.data = text
                    self.llm_command_pub.publish(cmd_msg)
                    self.get_logger().info(f"已转发LLM指令: {text[:30]}...")
                else:
                    raise CommandValidationError("LLM 指令为空或超过 4096 字符")

            elif msg.topic == self.topics.llm_generate_report:
                self._generate_llm_report()

            elif msg.topic == self.topics.snapshot_request:
                snapshot_request = parse_snapshot_request(payload)
                self._request_snapshot(snapshot_request)

            elif msg.topic == self.topics.command:
                command = parse_task_command(
                    payload, max_payload_bytes=self.max_command_bytes
                )
                if self._recent_commands.seen_or_add(command.command_id):
                    self._publish_mqtt(
                        self.topics.ack,
                        command_ack(command.command_id, False, "重复指令，已忽略"),
                    )
                    self.get_logger().warn(
                        f"重复指令已忽略: command_id={command.command_id}"
                    )
                    return

                req = TaskRequest()
                req.task_type = "patrol"
                req.route = command.route
                req.params = command.params_json
                self.task_pub.publish(req)
                self._publish_mqtt(
                    self.topics.ack,
                    command_ack(command.command_id, True, "巡检任务已转发到 ROS2"),
                )
                self.get_logger().info(f"已转发巡检任务: route={command.route}")

        except (CommandValidationError, json.JSONDecodeError, UnicodeDecodeError) as e:
            self._publish_mqtt(self.topics.ack, command_ack("", False, str(e)))
            self.get_logger().warn(f"拒绝云端指令: {e}")
        except Exception as e:
            self._publish_mqtt(self.topics.ack, command_ack("", False, "内部处理错误"))
            self.get_logger().error(f"处理云端指令失败: {type(e).__name__}: {e}")

    def _request_snapshot(self, request):
        """Start one bounded snapshot fetch without blocking MQTT callbacks."""

        if self._recent_snapshot_requests.seen_or_add(request.request_id):
            self._publish_snapshot_error(request.request_id, "重复截图请求，已忽略")
            return

        now = time.monotonic()
        min_interval = float(
            self.get_parameter("snapshot_min_interval_sec").value
        )
        if now - self._last_snapshot_started < min_interval:
            self._publish_snapshot_error(request.request_id, "截图请求过于频繁")
            return
        if not self._snapshot_lock.acquire(blocking=False):
            self._publish_snapshot_error(request.request_id, "已有截图请求正在处理")
            return

        self._last_snapshot_started = now
        worker = threading.Thread(
            target=self._fetch_and_publish_snapshot,
            args=(request,),
            name="cloud-snapshot",
            daemon=True,
        )
        worker.start()

    def _fetch_and_publish_snapshot(self, request):
        connection = None
        try:
            host = str(self.get_parameter("snapshot_host").value)
            port = int(self.get_parameter("snapshot_port").value)
            timeout = float(self.get_parameter("snapshot_timeout_sec").value)
            max_bytes = int(self.get_parameter("snapshot_max_bytes").value)
            path = "/yolo_snapshot" if request.annotated else "/snapshot"
            connection = http.client.HTTPConnection(host, port, timeout=timeout)
            connection.request("GET", path, headers={"Connection": "close"})
            response = connection.getresponse()
            if response.status != 200:
                raise RuntimeError(f"视觉服务返回 HTTP {response.status}")
            content_type = response.getheader("Content-Type", "image/jpeg")
            if content_type.split(";", 1)[0].strip().lower() != "image/jpeg":
                raise RuntimeError("视觉服务未返回 JPEG")
            image = response.read(max_bytes + 1)
            if not image:
                raise RuntimeError("视觉服务返回空图片")
            if len(image) > max_bytes:
                raise RuntimeError(f"截图超过 {max_bytes} bytes 限制")

            self._publish_mqtt(
                self.topics.snapshot,
                {
                    "ok": True,
                    "request_id": request.request_id,
                    "annotated": request.annotated,
                    "content_type": "image/jpeg",
                    "size_bytes": len(image),
                    "captured_at_ms": int(time.time() * 1000),
                    "image_base64": base64.b64encode(image).decode("ascii"),
                },
            )
            self.get_logger().info(
                f"远程截图已发送: request_id={request.request_id}, "
                f"bytes={len(image)}, annotated={request.annotated}"
            )
        except (OSError, http.client.HTTPException, RuntimeError) as exc:
            self._publish_snapshot_error(request.request_id, str(exc))
            self.get_logger().warn(f"远程截图失败: {exc}")
        finally:
            if connection is not None:
                connection.close()
            self._snapshot_lock.release()

    def _publish_snapshot_error(self, request_id, message):
        self._publish_mqtt(
            self.topics.snapshot,
            {
                "ok": False,
                "request_id": request_id,
                "error": message,
                "captured_at_ms": int(time.time() * 1000),
            },
        )

    def _generate_llm_report(self):
        if self._report_future is not None and not self._report_future.done():
            self.get_logger().warn("已有巡检报告生成请求正在执行")
            return
        if not self.report_client.service_is_ready():
            self.get_logger().warn("/llm/generate_report service not available")
            return

        req = GenerateReport.Request()
        req.task_id = ""
        req.logs_json = ""
        self._report_future = self.report_client.call_async(req)
        self._report_future.add_done_callback(self._on_report_generated)

    def _on_report_generated(self, future):
        try:
            response = future.result()
            if response.success:
                self._publish_mqtt(self.topics.llm_report, {
                    "success": True,
                    "report_text": response.report_text,
                })
                self.get_logger().info("已生成并发送巡检报告")
            else:
                self._publish_mqtt(self.topics.llm_report, {
                    "success": False,
                    "error_msg": response.error_msg,
                })
                self.get_logger().warn(f"报告生成失败: {response.error_msg}")
        except Exception as e:
            self.get_logger().error(f"调用LLM报告生成服务失败: {e}")

    # ── 车 → 云：状态/告警/日志 ──
    def _on_status(self, msg: TaskStatus):
        self._publish_mqtt(self.topics.status, {
            "task_id": msg.task_id,
            "status": msg.status,
            "current_step": msg.current_step,
            "total_steps": msg.total_steps,
            "message": msg.message,
        }, retain=True)

    def _on_nav_status(self, msg: NavStatus):
        if not self._telemetry_due("nav"):
            return
        self._publish_mqtt(self.topics.nav, {
            "status": msg.status,
            "progress": msg.progress,
            "distance_remain": msg.distance_remain,
            "message": msg.message,
        }, retain=True)

    def _on_pose(self, msg: PoseStamped):
        if not self._telemetry_due("pose"):
            return
        self._latest_pose = {
            "x": round(float(msg.pose.position.x), 3),
            "y": round(float(msg.pose.position.y), 3),
            "z": round(float(msg.pose.position.z), 3),
            "orientation_z": round(float(msg.pose.orientation.z), 6),
            "orientation_w": round(float(msg.pose.orientation.w), 6),
            "frame_id": msg.header.frame_id or "map",
            "timestamp": {
                "sec": msg.header.stamp.sec,
                "nanosec": msg.header.stamp.nanosec,
            },
        }
        self._publish_mqtt(self.topics.pose, self._latest_pose, retain=True)

    def _on_obstacle_status(self, msg: ObstacleStatus):
        if not self._telemetry_due(
            "obstacle", force=msg.risk_level == "danger"
        ):
            return
        self._publish_mqtt(self.topics.obstacle, {
            "is_obstacle": msg.is_obstacle,
            "min_distance": msg.min_distance,
            "direction": msg.direction,
            "risk_level": msg.risk_level,
            "action": msg.action,
        }, retain=True)

    def _on_env_data(self, msg: EnvData):
        if not self._telemetry_due("environment"):
            return
        self._publish_mqtt(self.topics.environment, {
            "temperature": msg.temperature,
            "humidity": msg.humidity,
            "smoke": msg.smoke,
            "pm25": msg.pm25,
            "light": msg.light,
            "pressure": msg.pressure,
        }, retain=True)

    def _on_alert(self, msg: SensorAlert):
        self._publish_mqtt(self.topics.alert, {
            "sensor_type": msg.sensor_type,
            "current_value": msg.current_value,
            "threshold": msg.threshold,
            "severity": msg.severity,
            "message": msg.message,
        }, retain=True)

    def _on_log(self, msg: TaskLog):
        self._publish_mqtt(self.topics.log, {
            "task_id": msg.task_id,
            "timestamp": {
                "sec": msg.timestamp.sec,
                "nanosec": msg.timestamp.nanosec,
            },
            "event_type": msg.event_type,
            "data": msg.data_json,
            "data_json": msg.data_json,
            "severity": msg.severity,
        })

    def _on_safety_alarm(self, msg: ROSString):
        try:
            payload = json.loads(msg.data)
            if not isinstance(payload, dict):
                payload = {"data": payload}
        except json.JSONDecodeError:
            payload = {"raw": msg.data}
        payload.setdefault("source", "safety")
        payload.setdefault("pose", dict(self._latest_pose))
        payload.setdefault("timestamp", int(time.time()))
        hazard_type = str(payload.get("hazard_type", "safety"))
        payload.setdefault("sensor_type", hazard_type)
        payload.setdefault("current_value", payload.get("confidence", 1.0))
        payload.setdefault("threshold", 0.0)
        payload.setdefault(
            "severity", "ERROR" if hazard_type == "fallen_person" else "WARN"
        )
        default_messages = {
            "water": "检测到积水，已告警并请求重新规划",
            "visual_obstacle": "视觉检测到障碍物，已告警并请求重新规划",
            "fallen_person": "检测到人员摔倒，巡航已暂停，等待工作人员确认",
            "obstacle": "雷达检测到障碍物",
        }
        payload.setdefault("message", default_messages.get(hazard_type, "安全告警"))
        self._publish_mqtt(self.topics.alert, payload, retain=True)

    def _on_llm_response(self, msg: ROSString):
        try:
            data = json.loads(msg.data)
            self._publish_mqtt(self.topics.llm_response, {
                "success": data.get("success", False),
                "request_id": data.get("request_id", ""),
                "tool_name": data.get("tool_name", ""),
                "message": data.get("message", ""),
                "reply": data.get("reply", ""),
                "error_msg": data.get("error_msg", ""),
                "route": data.get("route", []),
                "result": data.get("result", {}),
                "command": data.get("command", {}),
            })
            self.get_logger().info(f"已转发LLM响应: tool_name={data.get('tool_name', '')}")
        except json.JSONDecodeError:
            self.get_logger().warn(f"LLM响应解析失败: {msg.data[:50]}...")

    def _apply_cloud_motion(self, motion):
        if motion.command == "stop":
            self._stop_cloud_motion("远程停止指令")
            return
        with self._motion_lock:
            self._motion = (motion.linear_x, motion.linear_y, motion.angular_z)
            self._motion_deadline = time.monotonic() + motion.lease_seconds
            self._motion_active = True

    def _publish_cloud_motion(self):
        expired = False
        with self._motion_lock:
            if not self._motion_active:
                return
            if time.monotonic() > self._motion_deadline:
                self._motion_active = False
                self._motion = (0.0, 0.0, 0.0)
                expired = True
            motion = self._motion
        self._publish_twist(motion)
        if expired:
            self.get_logger().warn("远程方向指令租约过期，已自动停车")

    def _stop_cloud_motion(self, reason):
        with self._motion_lock:
            was_active = self._motion_active
            self._motion_active = False
            self._motion = (0.0, 0.0, 0.0)
            self._motion_deadline = 0.0
        self._publish_twist((0.0, 0.0, 0.0))
        if was_active:
            self.get_logger().warn(f"远程方向控制停止: {reason}")

    def _publish_twist(self, motion):
        msg = Twist()
        msg.linear.x, msg.linear.y, msg.angular.z = motion
        self.cloud_cmd_vel_pub.publish(msg)

    def _telemetry_due(self, key, force=False):
        now = time.monotonic()
        interval = float(self.get_parameter("telemetry_interval_sec").value)
        if not force and now - self._last_telemetry_publish.get(key, 0.0) < interval:
            return False
        self._last_telemetry_publish[key] = now
        return True

    def _publish_mqtt(self, topic, data: dict, retain=False):
        try:
            info = self.mqtt.publish(
                topic,
                json.dumps(data, ensure_ascii=False),
                qos=self.mqtt_qos,
                retain=retain,
            )
            if getattr(info, "rc", 0) != 0:
                self.get_logger().warn(f"MQTT 发送排队失败: topic={topic}, rc={info.rc}")
        except Exception as e:
            self.get_logger().warn(f"MQTT 发送失败: {e}")

    def destroy_node(self):
        if hasattr(self, "cloud_cmd_vel_pub"):
            self._stop_cloud_motion("节点关闭")
        if hasattr(self, "mqtt"):
            try:
                if self._mqtt_connected:
                    self.mqtt.publish(
                        self.topics.online,
                        json.dumps({"online": False}, ensure_ascii=False),
                        qos=self.mqtt_qos,
                        retain=True,
                    )
                self.mqtt.disconnect()
                self.mqtt.loop_stop()
            except Exception as e:
                self.get_logger().warn(f"关闭 MQTT 客户端失败: {e}")
        return super().destroy_node()


def main(args=None):
    rclpy.init(args=args)
    node = CloudBridgeNode()
    try:
        rclpy.spin(node)
    except KeyboardInterrupt:
        node.get_logger().info("cloud_bridge_node 关闭")
    finally:
        node.destroy_node()
        rclpy.shutdown()


if __name__ == "__main__":
    main()
