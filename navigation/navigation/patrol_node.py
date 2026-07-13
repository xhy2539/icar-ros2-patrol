import argparse
import sys
import time
from pathlib import Path

import rclpy
from geometry_msgs.msg import PoseStamped
from icar_interfaces.msg import NavStatus
from rclpy.node import Node

CURRENT_DIR = Path(__file__).resolve().parent
PARENT_DIR = CURRENT_DIR.parent
for path in (CURRENT_DIR, PARENT_DIR):
    if str(path) not in sys.path:
        sys.path.insert(0, str(path))

from navigation_utils import load_checkpoints, yaw_to_quaternion

NAV_TIMEOUT_SEC = 60.0


class PatrolNode(Node):
    def __init__(self, route_names, loop: bool):
        super().__init__("patrol_node")
        _, checkpoints = load_checkpoints()
        self.checkpoints = checkpoints
        self.route_names = route_names
        self.loop = loop
        self.current_index = 0
        self.waiting_result = False
        self.started_at = time.monotonic()
        self.goal_sent_at = None
        self.last_status = "IDLE"
        self.goal_publisher = self.create_publisher(PoseStamped, "/goal_pose", 10)
        self.create_subscription(NavStatus, "/nav_status", self.on_nav_status, 10)
        self.create_timer(1.0, self.on_timer)
        self.get_logger().info(f"Patrol node started in mock data mode: {self.route_names}")

    def publish_goal(self, name: str):
        checkpoint = self.checkpoints[name]
        message = PoseStamped()
        message.header.stamp = self.get_clock().now().to_msg()
        message.header.frame_id = "map"
        message.pose.position.x = float(checkpoint["x"])
        message.pose.position.y = float(checkpoint["y"])
        message.pose.position.z = 0.0
        orientation = yaw_to_quaternion(float(checkpoint.get("yaw", 0.0)))
        message.pose.orientation.x = orientation["x"]
        message.pose.orientation.y = orientation["y"]
        message.pose.orientation.z = orientation["z"]
        message.pose.orientation.w = orientation["w"]
        self.goal_publisher.publish(message)
        self.waiting_result = True
        self.goal_sent_at = time.monotonic()
        self.get_logger().info(f"Published patrol goal: {name}")

    def on_nav_status(self, message: NavStatus):
        self.last_status = message.status or "IDLE"
        if self.waiting_result and self.last_status == "ARRIVED":
            self.waiting_result = False
            self.goal_sent_at = None
            self.current_index += 1
        elif self.waiting_result and self.last_status == "FAILED":
            self.waiting_result = False
            self.goal_sent_at = None
            self.get_logger().warning("Patrol stopped after navigation failure")
            self.current_index = len(self.route_names)

    def on_timer(self):
        if time.monotonic() - self.started_at < 2.0:
            return
        if self.waiting_result:
            if self.goal_sent_at is not None and time.monotonic() - self.goal_sent_at > NAV_TIMEOUT_SEC:
                self.waiting_result = False
                self.get_logger().warning(
                    f"Patrol goal timed out after {NAV_TIMEOUT_SEC:.0f}s — skipping and advancing"
                )
                self.current_index += 1
            else:
                return
        if self.current_index >= len(self.route_names):
            if not self.loop:
                return
            self.current_index = 0
        target_name = self.route_names[self.current_index]
        if target_name not in self.checkpoints:
            self.get_logger().warning(f"Unknown checkpoint: {target_name}")
            self.current_index += 1
            return
        self.publish_goal(target_name)


def main():
    parser = argparse.ArgumentParser(description="Patrol node running with mock data mode")
    parser.add_argument("--route", default="", help="Comma-separated route names. Empty means use config route")
    parser.add_argument("--loop", action="store_true", help="Loop the route forever")
    args = parser.parse_args()

    default_route, _ = load_checkpoints()
    route_names = [item.strip() for item in args.route.split(",") if item.strip()] or default_route

    rclpy.init()
    node = PatrolNode(route_names, args.loop)
    try:
        rclpy.spin(node)
    except KeyboardInterrupt:
        pass
    finally:
        node.destroy_node()
        rclpy.shutdown()


if __name__ == "__main__":
    main()
