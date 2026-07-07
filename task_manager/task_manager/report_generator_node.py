#!/usr/bin/env python3
"""Task log report generator.

Subscribes to /task/log and prints a simple patrol report when TASK_END is
received. This is the deterministic fallback before the real LLM service is
connected.
"""

import json
from collections import defaultdict

import rclpy
from rclpy.node import Node
from rclpy.qos import QoSProfile, ReliabilityPolicy

from icar_interfaces.msg import TaskLog


class ReportGeneratorNode(Node):
    def __init__(self):
        super().__init__("report_generator_node")
        qos = QoSProfile(depth=50, reliability=ReliabilityPolicy.RELIABLE)
        self.logs_by_task = defaultdict(list)
        self.sub = self.create_subscription(TaskLog, "/task/log", self._on_log, qos)
        self.get_logger().info("report_generator_node ready")

    def _on_log(self, msg: TaskLog):
        data = self._parse_json(msg.data_json)
        record = {
            "event_type": msg.event_type,
            "severity": msg.severity,
            "data": data,
        }
        self.logs_by_task[msg.task_id].append(record)
        if msg.event_type == "TASK_END":
            report = self._build_report(msg.task_id)
            self.get_logger().info("\n" + report)

    def _build_report(self, task_id):
        records = self.logs_by_task[task_id]
        checkpoints = []
        warnings = []
        detections = []

        for record in records:
            data = record["data"]
            if record["event_type"] == "CHECKPOINT_REACHED":
                checkpoints.append(data.get("checkpoint", "?"))
            elif record["event_type"] == "ANOMALY":
                warnings.append(data)
            elif record["event_type"] == "VISION_DETECT":
                for det in data.get("detections", []):
                    detections.append(det.get("class", "unknown"))

        route_text = " -> ".join(checkpoints) if checkpoints else "未记录到点"
        warning_text = (
            f"发现 {len(warnings)} 条异常/告警"
            if warnings
            else "未发现严重异常"
        )
        detection_text = (
            "、".join(sorted(set(detections))) if detections else "无目标记录"
        )

        return (
            f"巡检报告 task_id={task_id}\n"
            f"- 巡检路线: {route_text}\n"
            f"- 视觉结果: {detection_text}\n"
            f"- 异常概况: {warning_text}\n"
            f"- 日志事件数: {len(records)}"
        )

    @staticmethod
    def _parse_json(text):
        try:
            return json.loads(text) if text else {}
        except json.JSONDecodeError:
            return {"raw": text}


def main(args=None):
    rclpy.init(args=args)
    node = ReportGeneratorNode()
    try:
        rclpy.spin(node)
    except KeyboardInterrupt:
        node.get_logger().info("report_generator_node interrupted")
    finally:
        node.destroy_node()
        rclpy.shutdown()


if __name__ == "__main__":
    main()
