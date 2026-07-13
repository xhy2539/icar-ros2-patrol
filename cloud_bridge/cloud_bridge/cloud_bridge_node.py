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
import threading

import rclpy
from rclpy.node import Node
from rclpy.qos import QoSProfile, ReliabilityPolicy
from std_msgs.msg import String as ROSString

from icar_interfaces.msg import TaskRequest, TaskStatus, TaskLog, SensorAlert

try:
    import paho.mqtt.client as mqtt
    from paho.mqtt.client import CallbackAPIVersion
except ImportError:
    mqtt = None


class CloudBridgeNode(Node):
    def __init__(self):
        super().__init__("cloud_bridge_node")

        # ── 参数 ──
        self.declare_parameter("mqtt_host", "82.156.132.43")
        self.declare_parameter("mqtt_port", 1883)
        self.declare_parameter("mqtt_user", "icar")
        self.declare_parameter("mqtt_pass", "icar123456")
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

        # ── QoS ──
        qos = QoSProfile(depth=10, reliability=ReliabilityPolicy.RELIABLE)

        # ── ROS2 订阅：车 → 云 ──
        self.create_subscription(TaskStatus, "/task/status", self._on_status, qos)
        self.create_subscription(SensorAlert, "/sensor/alert", self._on_alert, qos)
        self.create_subscription(TaskLog, "/task/log", self._on_log, qos)
        self.create_subscription(ROSString, "/llm/response", self._on_llm_response, qos)

        # ── ROS2 发布：云 → 车 ──
        self.task_pub = self.create_publisher(TaskRequest, "/task/request", qos)
        self.llm_command_pub = self.create_publisher(ROSString, "/llm/user_command", qos)

        # ── MQTT ──
        self.mqtt = mqtt.Client(CallbackAPIVersion.VERSION2)
        self.mqtt.username_pw_set(user, pw)
        self.mqtt.on_connect = self._on_mqtt_connect
        self.mqtt.on_message = self._on_mqtt_message

        # 后台线程连 MQTT
        self._mqtt_thread = threading.Thread(target=self._mqtt_connect, daemon=True)
        self._mqtt_thread.start()

        self.get_logger().info(
            f"cloud_bridge 启动: {host}:{port} (user={user})"
        )

    # ── MQTT 连接 ──
    def _mqtt_connect(self):
        host = self.get_parameter("mqtt_host").value
        port = self.get_parameter("mqtt_port").value
        try:
            self.mqtt.connect(host, port, 60)
            self.mqtt.loop_forever()
        except Exception as e:
            self.get_logger().error(f"MQTT 连接失败: {e}")

    def _on_mqtt_connect(self, client, userdata, flags, rc, props=None):
        if rc == 0:
            self.get_logger().info("MQTT 已连接")
            client.subscribe("/icar/cmd")
            client.subscribe("/icar/llm/command")
            client.subscribe("/icar/llm/generate_report")
        else:
            self.get_logger().error(f"MQTT 连接错误: rc={rc}")

    # ── 云 → 车：收到手机指令 ──
    def _on_mqtt_message(self, client, userdata, msg):
        payload = msg.payload.decode("utf-8", errors="replace")
        self.get_logger().info(f"[云→车] {msg.topic}: {payload}")

        try:
            if msg.topic == "/icar/llm/command":
                data = json.loads(payload)
                text = data.get("text", "")
                if text:
                    cmd_msg = ROSString()
                    cmd_msg.data = text
                    self.llm_command_pub.publish(cmd_msg)
                    self.get_logger().info(f"已转发LLM指令: {text[:30]}...")
                else:
                    self.get_logger().warn("LLM指令为空")

            elif msg.topic == "/icar/llm/generate_report":
                self._generate_llm_report()

            else:
                data = json.loads(payload)
                action = data.get("action", "").lower()
                route = data.get("route", ["A", "B", "C"])
                params = data.get("params", "")

                if action in ("start", "patrol", "巡检"):
                    req = TaskRequest()
                    req.task_type = "patrol"
                    req.route = route
                    req.params = json.dumps(params, ensure_ascii=False) if isinstance(params, dict) else str(params)
                    self.task_pub.publish(req)
                    self.get_logger().info(f"已转发巡检任务: route={route}")

        except (json.JSONDecodeError, KeyError) as e:
            self.get_logger().warn(f"无法解析指令: {payload}, error={e}")

    def _generate_llm_report(self):
        try:
            from icar_interfaces.srv import GenerateReport
            import rclpy

            client = self.create_client(GenerateReport, '/llm/generate_report')
            if not client.wait_for_service(timeout_sec=2.0):
                self.get_logger().warn("/llm/generate_report service not available")
                return

            req = GenerateReport.Request()
            req.task_id = ""
            req.logs_json = ""

            future = client.call_async(req)
            rclpy.spin_until_future_complete(self, future)

            response = future.result()
            if response.success:
                self._publish_mqtt("/icar/llm/report", {
                    "success": True,
                    "report_text": response.report_text
                })
                self.get_logger().info("已生成并发送巡检报告")
            else:
                self._publish_mqtt("/icar/llm/report", {
                    "success": False,
                    "error_msg": response.error_msg
                })
                self.get_logger().warn(f"报告生成失败: {response.error_msg}")

        except Exception as e:
            self.get_logger().error(f"调用LLM报告生成服务失败: {e}")

    # ── 车 → 云：状态/告警/日志 ──
    def _on_status(self, msg: TaskStatus):
        self._publish_mqtt("/icar/status", {
            "task_id": msg.task_id,
            "status": msg.status,
            "current_step": msg.current_step,
            "total_steps": msg.total_steps,
            "message": msg.message,
        })

    def _on_alert(self, msg: SensorAlert):
        self._publish_mqtt("/icar/alert", {
            "sensor_type": msg.sensor_type,
            "current_value": msg.current_value,
            "threshold": msg.threshold,
            "severity": msg.severity,
            "message": msg.message,
        })

    def _on_log(self, msg: TaskLog):
        self._publish_mqtt("/icar/log", {
            "task_id": msg.task_id,
            "event_type": msg.event_type,
            "data": msg.data_json,
            "severity": msg.severity,
        })

    def _publish_mqtt(self, topic, data: dict):
        try:
            self.mqtt.publish(topic, json.dumps(data, ensure_ascii=False))
        except Exception as e:
            self.get_logger().warn(f"MQTT 发送失败: {e}")


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
