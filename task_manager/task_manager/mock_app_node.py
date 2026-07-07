#!/usr/bin/env python3
"""Mock APP node for patrol integration tests.

Publishes one patrol task to /task/request. This lets the team test the
task_manager and downstream mock modules before the real APP is ready.
"""

import json

import rclpy
from rclpy.node import Node
from rclpy.qos import QoSProfile, ReliabilityPolicy

from icar_interfaces.msg import TaskRequest


class MockAppNode(Node):
    def __init__(self):
        super().__init__("mock_app_node")
        qos = QoSProfile(depth=10, reliability=ReliabilityPolicy.RELIABLE)
        self.publisher = self.create_publisher(TaskRequest, "/task/request", qos)
        self.declare_parameter("route", ["A", "B", "C"])
        self.declare_parameter("delay_sec", 1.0)
        self._published = False
        delay_sec = float(self.get_parameter("delay_sec").value)
        self.timer = self.create_timer(delay_sec, self._publish_task)
        self.get_logger().info("mock_app_node ready; will publish patrol task once")

    def _publish_task(self):
        if self._published:
            return

        route = list(self.get_parameter("route").value)
        msg = TaskRequest()
        msg.task_type = "patrol"
        msg.route = route
        msg.params = json.dumps(
            {
                "source": "mock_app_node",
                "stop_on_obstacle": True,
                "collect_sensor": True,
                "run_vision": True,
            },
            ensure_ascii=False,
        )
        self.publisher.publish(msg)
        self._published = True
        self.get_logger().info(f"published mock patrol task: route={route}")


def main(args=None):
    rclpy.init(args=args)
    node = MockAppNode()
    try:
        rclpy.spin(node)
    except KeyboardInterrupt:
        node.get_logger().info("mock_app_node interrupted")
    finally:
        node.destroy_node()
        rclpy.shutdown()


if __name__ == "__main__":
    main()
