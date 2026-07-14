#!/usr/bin/env python3
"""Route confirmed assistant commands through llm_gateway and task_manager."""

import json
import re

import rclpy
from rclpy.node import Node
from rclpy.qos import QoSProfile, ReliabilityPolicy
from std_msgs.msg import String

from icar_interfaces.msg import TaskRequest, TaskStatus
from icar_interfaces.srv import ParseTask

from .intent_classifier import classify_intent


CONTROL_PREFIX = "执行任务："
EMERGENCY_PHRASES = ("紧急停止", "立即停止")
VALID_POINTS = {"A", "B", "C", "D", "E", "F"}


class VoiceCommandRouterNode(Node):
    def __init__(self):
        super().__init__("voice_command_router_node")
        qos = QoSProfile(depth=20, reliability=ReliabilityPolicy.RELIABLE)
        self.result_sub = self.create_subscription(
            String, "/voice/assistant_result", self._on_result, qos
        )
        self.user_text_sub = self.create_subscription(
            String, "/voice/user_text", self._on_user_text, qos
        )
        self.task_status_sub = self.create_subscription(
            TaskStatus, "/task/status", self._on_task_status, qos
        )
        self.task_pub = self.create_publisher(TaskRequest, "/task/request", qos)
        self.llm_command_pub = self.create_publisher(String, "/llm/user_command", qos)
        self.control_pub = self.create_publisher(String, "/voice/control", qos)
        self.intent_pub = self.create_publisher(String, "/voice/intent", qos)
        self.robot_status_pub = self.create_publisher(
            String, "/voice/robot_status", qos
        )
        self.parse_client = self.create_client(ParseTask, "/llm/parse_task")
        self._turn_text = ""
        self._was_speaking = False
        self._last_command = ""
        self.get_logger().info("voice_command_router_node ready")

    def _on_user_text(self, msg):
        text = self._extract_text(msg.data)
        decision = classify_intent(text)
        decision["text"] = text
        decision["source"] = "voice"

        intent_msg = String()
        intent_msg.data = json.dumps(decision, ensure_ascii=False)
        self.intent_pub.publish(intent_msg)

        if decision["intent"] == "emergency":
            self._publish_control("stop", text)
        elif decision["intent"] == "care_alert":
            self._publish_control("notify_staff", text)

        self.get_logger().info(
            f"voice intent={decision['intent']} text={text}"
        )

    @staticmethod
    def _extract_text(raw):
        try:
            value = json.loads(raw)
            if isinstance(value, dict):
                return str(value.get("text", "")).strip()
        except json.JSONDecodeError:
            pass
        return str(raw).strip()

    def _on_result(self, msg):
        try:
            event = json.loads(msg.data)
        except json.JSONDecodeError:
            event = {"text": msg.data, "is_listen": False}

        text = str(event.get("text", ""))
        if text:
            self._turn_text += text

        if any(phrase in self._turn_text for phrase in EMERGENCY_PHRASES):
            self._publish_control("stop", self._turn_text)
            self._turn_text = ""
            self._was_speaking = False
            return

        is_speaking = not bool(event.get("is_listen", True))
        turn_finished = bool(event.get("end_of_turn", False)) or (
            self._was_speaking and not is_speaking
        )
        self._was_speaking = is_speaking
        if turn_finished:
            self._route_completed_turn(self._turn_text.strip())
            self._turn_text = ""

    def _route_completed_turn(self, text):
        if CONTROL_PREFIX not in text:
            return
        command = text.split(CONTROL_PREFIX, 1)[1].strip()
        command = re.split(r"[。！？\n]", command, maxsplit=1)[0].strip()
        if not command or command == self._last_command:
            return
        # The executable LLM gateway owns the complete safe-tool whitelist:
        # patrol, tracking, bounded movement, status and compound plans.
        # Do not reduce a voice command back to patrol-only ParseTask here.
        message = String()
        message.data = json.dumps(
            {"input_text": command, "source": "voice", "request_id": "voice"},
            ensure_ascii=False,
        )
        self.llm_command_pub.publish(message)
        self._last_command = command
        self.get_logger().info(f"published confirmed voice tool command: {command}")

    def _on_parsed(self, future, source):
        try:
            response = future.result()
            if not response.success:
                raise RuntimeError(response.error_msg)
            parsed = json.loads(response.task_json)
            route = [
                str(point).upper()
                for point in parsed.get("route", [])
                if str(point).upper() in VALID_POINTS
            ]
            if not route:
                raise ValueError("parsed task has no valid route")

            task = TaskRequest()
            task.task_type = str(parsed.get("task_type", "patrol"))
            task.route = route
            task.params = json.dumps(
                {
                    "source": "voice_control",
                    "confirmed_text": source,
                    "parsed": parsed,
                },
                ensure_ascii=False,
            )
            self.task_pub.publish(task)
            self._last_command = source
            self.get_logger().info(
                f"published confirmed voice task: route={route}, text={source}"
            )
        except Exception as exc:
            self.get_logger().error(f"voice task rejected: {exc}")

    def _publish_control(self, command, reason):
        msg = String()
        msg.data = json.dumps(
            {"command": command, "reason": reason, "source": "voice_control"},
            ensure_ascii=False,
        )
        self.control_pub.publish(msg)
        self.get_logger().warning(f"published voice control: {command}")

    def _on_task_status(self, msg):
        status = String()
        status.data = json.dumps(
            {
                "task_id": msg.task_id,
                "status": msg.status,
                "current_step": msg.current_step,
                "total_steps": msg.total_steps,
                "message": msg.message,
            },
            ensure_ascii=False,
        )
        self.robot_status_pub.publish(status)


def main(args=None):
    rclpy.init(args=args)
    node = VoiceCommandRouterNode()
    try:
        rclpy.spin(node)
    except KeyboardInterrupt:
        pass
    finally:
        node.destroy_node()
        rclpy.shutdown()


if __name__ == "__main__":
    main()
