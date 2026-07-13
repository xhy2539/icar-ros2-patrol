"""Obstacle avoidance node — reads /scan, publishes /obstacle_status and /cmd_vel_safety."""
import argparse
import math
import time

from geometry_msgs.msg import Twist
from icar_interfaces.msg import ObstacleStatus
import rclpy
from rclpy.node import Node
from sensor_msgs.msg import LaserScan

FRONT_SECTOR_DEGREES = 90.0  # half-angle
WARNING_DISTANCE_M = 1.0
DANGER_DISTANCE_M = 0.5


def classify_scan(ranges, angle_min, angle_increment, range_min, range_max):
    front_rad = math.radians(FRONT_SECTOR_DEGREES)
    valid = []
    for i, d in enumerate(ranges):
        if not math.isfinite(d):
            continue
        if d < range_min or d > range_max:
            continue
        angle = angle_min + i * angle_increment
        if abs(math.atan2(math.sin(angle), math.cos(angle))) <= front_rad:
            valid.append(d)
    if not valid:
        return {
            "is_obstacle": False,
            "min_distance": float(range_max) if math.isfinite(range_max) else 2.5,
            "direction": "front",
            "risk_level": "safe",
            "action": "none",
        }
    d = min(valid)
    if d <= DANGER_DISTANCE_M:
        return {"is_obstacle": True, "min_distance": d, "direction": "front", "risk_level": "danger", "action": "stop"}
    if d <= WARNING_DISTANCE_M:
        return {"is_obstacle": True, "min_distance": d, "direction": "front", "risk_level": "warning", "action": "slow_down"}
    return {"is_obstacle": False, "min_distance": d, "direction": "front", "risk_level": "safe", "action": "none"}


class ObstacleAvoidNode(Node):
    def __init__(self, mode: str = "real"):
        super().__init__("obstacle_avoid_node")
        self.mode = mode
        self.latest = None
        self.pub_status = self.create_publisher(ObstacleStatus, "/obstacle_status", 10)
        self.pub_cmd = self.create_publisher(Twist, "/cmd_vel_safety", 10)
        self.create_subscription(LaserScan, "/scan", self.on_scan, 10)
        self.create_timer(0.1, self.on_timer)
        self.get_logger().info(f"Obstacle avoid node started in {mode} mode (front={FRONT_SECTOR_DEGREES}deg, danger={DANGER_DISTANCE_M}m)")

    def on_scan(self, msg: LaserScan):
        self.latest = classify_scan(msg.ranges, float(msg.angle_min), float(msg.angle_increment), float(msg.range_min), float(msg.range_max))

    def on_timer(self):
        event = self.latest
        if event is None:
            return  # no scan yet
        status = ObstacleStatus()
        status.is_obstacle = event["is_obstacle"]
        status.min_distance = event["min_distance"]
        status.direction = event["direction"]
        status.risk_level = event["risk_level"]
        status.action = event["action"]
        self.pub_status.publish(status)
        if event["risk_level"] == "danger":
            stop = Twist()
            stop.linear.x = 0.0
            stop.angular.z = 0.0
            self.pub_cmd.publish(stop)
            self.get_logger().warn(f"DANGER at {event['min_distance']:.2f}m — STOP", throttle_duration_sec=1.0)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--mode", choices=["real", "mock"], default="real")
    args = parser.parse_args()
    rclpy.init()
    node = ObstacleAvoidNode(args.mode)
    try:
        rclpy.spin(node)
    except KeyboardInterrupt:
        pass
    finally:
        node.destroy_node()
        rclpy.shutdown()


if __name__ == "__main__":
    main()
