import argparse
import sys
import time
from pathlib import Path

import rclpy
from geometry_msgs.msg import PoseStamped
from icar_interfaces.msg import NavStatus, ObstacleStatus
from nav_msgs.msg import OccupancyGrid
from rclpy.node import Node
from rclpy.qos import DurabilityPolicy, QoSProfile, ReliabilityPolicy
from sensor_msgs.msg import LaserScan

CURRENT_DIR = Path(__file__).resolve().parent
PARENT_DIR = CURRENT_DIR.parent
for path in (CURRENT_DIR, PARENT_DIR):
    if str(path) not in sys.path:
        sys.path.insert(0, str(path))

from navigation_utils import clamp, distance_between, load_checkpoints, load_nav_scenarios, quaternion_to_yaw


class NavigationNode(Node):
    def __init__(self, scenario_name: str):
        super().__init__("navigation_node")
        _, checkpoints = load_checkpoints()
        scenario_config = load_nav_scenarios()

        available_scenarios = scenario_config.get("scenarios", {})
        default_scenario = scenario_config.get("default_scenario", "success")
        self.scenario_name = scenario_name if scenario_name in available_scenarios else default_scenario
        self.scenario = available_scenarios[self.scenario_name]

        self.current_pose = dict(checkpoints.get("HOME", {"x": 0.0, "y": 0.0, "yaw": 0.0}))
        self.goal_start_pose = dict(self.current_pose)
        self.active_goal = None
        self.goal_start_time = None
        self.result_time = None
        self.result_status = None
        self.result_message = ""
        self.last_status_signature = None
        self.current_obstacle = None
        self.danger_since = None
        self.map_received = False
        self.scan_received = False

        map_qos = QoSProfile(depth=1)
        map_qos.reliability = ReliabilityPolicy.RELIABLE
        map_qos.durability = DurabilityPolicy.TRANSIENT_LOCAL

        self.status_publisher = self.create_publisher(NavStatus, "/nav_status", 10)
        self.create_subscription(PoseStamped, "/goal_pose", self.on_goal_pose, 10)
        self.create_subscription(ObstacleStatus, "/obstacle_status", self.on_obstacle_status, 10)
        self.create_subscription(PoseStamped, "/pose", self.on_pose, 10)
        self.create_subscription(OccupancyGrid, "/map", self.on_map, map_qos)
        self.create_subscription(LaserScan, "/scan", self.on_scan, 10)
        self.timer = self.create_timer(0.5, self.on_timer)

        self.get_logger().info(f"Navigation node started in mock data mode: {self.scenario_name}")

    def on_goal_pose(self, message: PoseStamped):
        self.active_goal = {
            "x": float(message.pose.position.x),
            "y": float(message.pose.position.y),
            "yaw": quaternion_to_yaw(
                float(message.pose.orientation.z),
                float(message.pose.orientation.w),
            ),
        }
        self.goal_start_pose = dict(self.current_pose)
        self.goal_start_time = time.monotonic()
        self.result_time = None
        self.result_status = None
        self.result_message = ""
        self.danger_since = None
        self.get_logger().info(
            f"Received goal ({self.active_goal['x']:.2f}, {self.active_goal['y']:.2f})"
        )

    def on_obstacle_status(self, message: ObstacleStatus):
        self.current_obstacle = message

    def on_pose(self, message: PoseStamped):
        self.current_pose = {
            "x": float(message.pose.position.x),
            "y": float(message.pose.position.y),
            "yaw": quaternion_to_yaw(
                float(message.pose.orientation.z),
                float(message.pose.orientation.w),
            ),
        }

    def on_map(self, _: OccupancyGrid):
        self.map_received = True

    def on_scan(self, _: LaserScan):
        self.scan_received = True

    def publish_status(self, status: str, progress: float, distance_remain: float, message_text: str):
        signature = (
            status,
            round(progress, 3),
            round(distance_remain, 3),
            message_text,
        )
        if signature != self.last_status_signature:
            ros_message = NavStatus()
            ros_message.status = status
            ros_message.progress = round(progress, 3)
            ros_message.distance_remain = round(distance_remain, 3)
            ros_message.message = message_text
            self.status_publisher.publish(ros_message)
            self.last_status_signature = signature

    def finish_goal(self, status: str, message_text: str, progress: float):
        self.result_status = status
        self.result_message = message_text
        self.result_time = time.monotonic()
        if self.active_goal:
            if status == "ARRIVED":
                self.current_pose = dict(self.active_goal)
            else:
                self.current_pose = {
                    "x": self.goal_start_pose["x"] + (self.active_goal["x"] - self.goal_start_pose["x"]) * progress,
                    "y": self.goal_start_pose["y"] + (self.active_goal["y"] - self.goal_start_pose["y"]) * progress,
                    "yaw": self.goal_start_pose["yaw"] + (self.active_goal["yaw"] - self.goal_start_pose["yaw"]) * progress,
                }

    def on_timer(self):
        if not self.active_goal and not self.result_status:
            self.publish_status("IDLE", 0.0, 0.0, "waiting for /goal_pose")
            return

        if self.result_status:
            hold_result_sec = float(self.scenario.get("hold_result_sec", 2.0))
            if time.monotonic() - self.result_time <= hold_result_sec:
                self.publish_status(self.result_status, 1.0 if self.result_status == "ARRIVED" else 0.99, 0.0, self.result_message)
                return

            self.active_goal = None
            self.result_status = None
            self.result_message = ""
            self.goal_start_time = None
            self.publish_status("IDLE", 0.0, 0.0, "ready for next goal")
            return

        now = time.monotonic()
        elapsed = now - self.goal_start_time
        duration_sec = float(self.scenario.get("duration_sec", 8.0))
        fail_after_sec = self.scenario.get("fail_after_sec")
        obstacle_fail_after_sec = float(self.scenario.get("obstacle_fail_after_sec", 999.0))

        progress = clamp(elapsed / duration_sec, 0.0, 1.0)
        total_distance = distance_between(self.goal_start_pose, self.active_goal)
        distance_remain = total_distance * (1.0 - progress)

        risk_level = self.current_obstacle.risk_level if self.current_obstacle else "safe"
        if risk_level == "danger":
            if self.danger_since is None:
                self.danger_since = now
            if now - self.danger_since >= obstacle_fail_after_sec:
                self.finish_goal("FAILED", "navigation failed because obstacle remained danger too long", progress)
                self.publish_status("FAILED", progress, max(distance_remain, 0.0), self.result_message)
                return
            self.publish_status("NAVIGATING", progress, distance_remain, "obstacle detected, holding navigation state")
            return

        self.danger_since = None

        if fail_after_sec is not None and elapsed >= float(fail_after_sec):
            self.finish_goal("FAILED", "navigation timeout in mock scenario", progress)
            self.publish_status("FAILED", progress, max(distance_remain, 0.0), self.result_message)
            return

        if elapsed >= duration_sec:
            self.finish_goal("ARRIVED", "mock goal reached", 1.0)
            self.publish_status("ARRIVED", 1.0, 0.0, self.result_message)
            return

        self.publish_status("NAVIGATING", progress, distance_remain, "mock navigation in progress")


def main():
    parser = argparse.ArgumentParser(description="Navigation node running with mock data mode")
    parser.add_argument("--scenario", default="success", help="Navigation scenario defined in nav_scenarios.yaml")
    args = parser.parse_args()

    rclpy.init()
    node = NavigationNode(args.scenario)
    try:
        rclpy.spin(node)
    except KeyboardInterrupt:
        pass
    finally:
        node.destroy_node()
        rclpy.shutdown()


if __name__ == "__main__":
    main()
