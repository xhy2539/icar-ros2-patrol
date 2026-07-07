#!/usr/bin/env python3
"""Mock navigation node.

Listens to /task/status. Whenever task_manager enters NAVIGATING for a new
step, publishes NAVIGATING and then ARRIVED on /nav_status after a short delay.
Replace this node with the real navigation adapter once SLAM/nav is stable.
"""

import rclpy
from rclpy.node import Node
from rclpy.qos import QoSProfile, ReliabilityPolicy

from icar_interfaces.msg import NavStatus, TaskStatus


class MockNavigationNode(Node):
    def __init__(self):
        super().__init__("mock_navigation_node")
        qos = QoSProfile(depth=10, reliability=ReliabilityPolicy.RELIABLE)
        self.status_sub = self.create_subscription(
            TaskStatus, "/task/status", self._on_task_status, qos
        )
        self.nav_pub = self.create_publisher(NavStatus, "/nav_status", qos)
        self.declare_parameter("arrival_delay_sec", 2.0)
        self._active_key = None
        self._arrival_timer = None
        self.get_logger().info("mock_navigation_node ready")

    def _on_task_status(self, msg: TaskStatus):
        if msg.status != "NAVIGATING":
            return

        key = (msg.task_id, msg.current_step)
        if key == self._active_key:
            return

        self._active_key = key
        checkpoint = self._checkpoint_name(msg.current_step)
        self._publish_status(
            "NAVIGATING",
            progress=0.2,
            distance_remain=1.0,
            message=f"mock navigating to {checkpoint}",
        )
        delay_sec = float(self.get_parameter("arrival_delay_sec").value)
        if self._arrival_timer:
            self._arrival_timer.cancel()
        self._arrival_timer = self.create_timer(delay_sec, self._arrive)
        self.get_logger().info(f"mock navigation started: {checkpoint}")

    def _arrive(self):
        if self._arrival_timer:
            self._arrival_timer.cancel()
            self._arrival_timer = None
        self._publish_status(
            "ARRIVED",
            progress=1.0,
            distance_remain=0.0,
            message="mock arrival reached",
        )

    def _publish_status(self, status, progress, distance_remain, message):
        msg = NavStatus()
        msg.status = status
        msg.progress = float(progress)
        msg.distance_remain = float(distance_remain)
        msg.message = message
        self.nav_pub.publish(msg)

    @staticmethod
    def _checkpoint_name(step):
        names = ["A", "B", "C"]
        idx = max(0, int(step) - 1)
        return names[idx] if idx < len(names) else f"P{step}"


def main(args=None):
    rclpy.init(args=args)
    node = MockNavigationNode()
    try:
        rclpy.spin(node)
    except KeyboardInterrupt:
        node.get_logger().info("mock_navigation_node interrupted")
    finally:
        node.destroy_node()
        rclpy.shutdown()


if __name__ == "__main__":
    main()
