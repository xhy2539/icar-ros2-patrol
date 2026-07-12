#!/usr/bin/env python3
"""ROS2 LLM gateway.

The node keeps the LLM layer behind services. It never publishes /cmd_vel.
The first implementation is a deterministic fallback so integration tests can
run without network or model-server availability.
"""

import json
import re
from collections import defaultdict

import rclpy
from rclpy.node import Node
from rclpy.qos import QoSProfile, ReliabilityPolicy

from icar_interfaces.msg import TaskLog
from icar_interfaces.srv import GenerateReport, ParseTask


DEFAULT_ACTIONS = ["navigate", "avoid_obstacle", "detect_object", "collect_sensor"]
ALLOWED_ACTIONS = set(DEFAULT_ACTIONS)
KNOWN_POINTS = ("A", "B", "C", "D", "E", "F")


class LlmGatewayNode(Node):
    def __init__(self):
        super().__init__("llm_gateway_node")
        self.declare_parameter("provider", "rule")
        self.declare_parameter("default_route", ["A", "B", "C"])
        self.declare_parameter("max_logs_per_task", 200)

        self.provider = str(self.get_parameter("provider").value)
        self.default_route = list(self.get_parameter("default_route").value)
        self.max_logs_per_task = int(self.get_parameter("max_logs_per_task").value)

        qos = QoSProfile(depth=50, reliability=ReliabilityPolicy.RELIABLE)
        self.logs_by_task = defaultdict(list)
        self.task_log_sub = self.create_subscription(
            TaskLog, "/task/log", self._on_task_log, qos
        )
        self.parse_srv = self.create_service(
            ParseTask, "/llm/parse_task", self._on_parse_task
        )
        self.report_srv = self.create_service(
            GenerateReport, "/llm/generate_report", self._on_generate_report
        )

        self.get_logger().info(
            f"llm_gateway_node ready, provider={self.provider}, "
            "services=[/llm/parse_task,/llm/generate_report]"
        )

    def _on_task_log(self, msg: TaskLog):
        record = {
            "task_id": msg.task_id,
            "timestamp": {
                "sec": msg.timestamp.sec,
                "nanosec": msg.timestamp.nanosec,
            },
            "event_type": msg.event_type,
            "severity": msg.severity,
            "data": self._loads_json(msg.data_json),
        }
        bucket = self.logs_by_task[msg.task_id]
        bucket.append(record)
        if len(bucket) > self.max_logs_per_task:
            del bucket[: len(bucket) - self.max_logs_per_task]

    def _on_parse_task(self, request, response):
        text = request.input_text.strip()
        if not text:
            response.task_json = "{}"
            response.success = False
            response.error_msg = "input_text is empty"
            return response

        task = self._parse_task_by_rule(text)
        response.task_json = json.dumps(task, ensure_ascii=False)
        response.success = True
        response.error_msg = ""
        self.get_logger().info(f"parse_task: {text} -> {response.task_json}")
        return response

    def _on_generate_report(self, request, response):
        logs = []
        if request.logs_json.strip():
            parsed = self._loads_json(request.logs_json)
            if isinstance(parsed, list):
                logs = parsed
            elif isinstance(parsed, dict):
                logs = parsed.get("logs", [])
        elif request.task_id:
            logs = list(self.logs_by_task.get(request.task_id, []))

        if not logs:
            response.report_text = ""
            response.success = False
            response.error_msg = "no logs available"
            return response

        response.report_text = self._build_report(request.task_id, logs)
        response.success = True
        response.error_msg = ""
        return response

    def _parse_task_by_rule(self, text):
        route = self._extract_route(text) or self.default_route
        actions = self._extract_actions(text)
        safety_rule = self._extract_safety_rule(text)
        params = {
            "source": "llm_gateway",
            "provider": self.provider,
            "raw_text": text,
        }
        if "语音" in text or "说" in text:
            params["input_mode"] = "voice"

        return {
            "task_type": "patrol",
            "route": route,
            "actions": actions,
            "safety_rule": safety_rule,
            "params": params,
        }

    def _extract_route(self, text):
        route = []
        upper_text = text.upper()
        for point in KNOWN_POINTS:
            patterns = (
                rf"(?<![A-Z]){point}(?![A-Z])",
                rf"{point}\s*点",
                rf"点\s*{point}",
            )
            if any(re.search(pattern, upper_text) for pattern in patterns):
                route.append(point)
        if route:
            return route

        cn_points = {
            "一": "A",
            "二": "B",
            "三": "C",
            "四": "D",
            "五": "E",
            "六": "F",
        }
        for key, value in cn_points.items():
            if f"{key}号" in text or f"{key}点" in text:
                route.append(value)
        return route

    def _extract_actions(self, text):
        actions = ["navigate", "avoid_obstacle"]
        keyword_map = {
            "detect_object": ("检测", "识别", "目标", "视觉", "拍照"),
            "collect_sensor": ("采集", "传感器", "温度", "湿度", "烟雾", "环境"),
        }
        for action, keywords in keyword_map.items():
            if any(keyword in text for keyword in keywords):
                actions.append(action)
        if "巡检" in text or "一圈" in text:
            actions = DEFAULT_ACTIONS.copy()
        return [action for action in actions if action in ALLOWED_ACTIONS]

    @staticmethod
    def _extract_safety_rule(text):
        rules = []
        if "障碍" in text or "避障" in text:
            rules.append("遇到障碍物停止并等待处理")
        if "烟雾" in text or "报警" in text or "异常" in text:
            rules.append("检测到环境异常时停止并报警")
        if "停止" in text or "刹车" in text:
            rules.append("收到停止指令立即停止")
        return "；".join(rules) if rules else "遵循 task_manager 安全白名单"

    def _build_report(self, task_id, logs):
        checkpoints = []
        detections = []
        warnings = []
        errors = []
        event_count = 0

        for record in logs:
            event_count += 1
            event_type = str(record.get("event_type", ""))
            severity = str(record.get("severity", "INFO"))
            data = record.get("data", {})
            if isinstance(data, str):
                data = self._loads_json(data)

            if event_type in ("CHECKPOINT_REACHED", "NAV_END"):
                checkpoint = data.get("checkpoint") or data.get("target")
                if checkpoint:
                    checkpoints.append(str(checkpoint))
            if event_type == "VISION_DETECT":
                for det in data.get("detections", []):
                    name = det.get("class") or det.get("class_name") or "unknown"
                    detections.append(str(name))
            if event_type == "ANOMALY" or severity == "WARN":
                warnings.append(data)
            if severity == "ERROR":
                errors.append(data)

        route_text = " -> ".join(checkpoints) if checkpoints else "未记录到到点事件"
        detection_text = "、".join(sorted(set(detections))) if detections else "无目标记录"
        task_text = task_id or self._infer_task_id(logs)
        result = "异常结束" if errors else "完成/未发现致命错误"

        return (
            f"巡检报告 task_id={task_text}\n"
            f"- 巡检结果: {result}\n"
            f"- 巡检路线: {route_text}\n"
            f"- 视觉结果: {detection_text}\n"
            f"- 告警数量: {len(warnings)}\n"
            f"- 错误数量: {len(errors)}\n"
            f"- 日志事件数: {event_count}"
        )

    @staticmethod
    def _infer_task_id(logs):
        for record in logs:
            task_id = record.get("task_id")
            if task_id:
                return str(task_id)
        return "unknown"

    @staticmethod
    def _loads_json(text):
        if isinstance(text, (dict, list)):
            return text
        if not text:
            return {}
        try:
            return json.loads(text)
        except json.JSONDecodeError:
            return {"raw": text}


def main(args=None):
    rclpy.init(args=args)
    node = LlmGatewayNode()
    try:
        rclpy.spin(node)
    except KeyboardInterrupt:
        node.get_logger().info("llm_gateway_node interrupted")
    finally:
        node.destroy_node()
        rclpy.shutdown()


if __name__ == "__main__":
    main()
