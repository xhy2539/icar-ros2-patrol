"""Obstacle classification node — reads /scan and publishes /obstacle_status.

Detection: ±30° front sector. <0.5m = DANGER/STOP, <1.0m = WARNING/SLOW_DOWN.
The velocity mux applies directional limits so Nav2 can still rotate or reverse
around a static obstacle. A legacy full-stop Twist can be enabled explicitly.
"""
import argparse
import math

from geometry_msgs.msg import Twist
from icar_interfaces.msg import ObstacleStatus
import rclpy
from rclpy.node import Node
from sensor_msgs.msg import LaserScan

FRONT_SECTOR_DEGREES = 30.0
WARNING_DISTANCE_M = 1.0
DANGER_DISTANCE_M = 0.5


def classify_front_scan(
    ranges,
    angle_min,
    angle_increment,
    range_min,
    range_max,
    front_angle_deg=FRONT_SECTOR_DEGREES,
    front_center_deg=0.0,
):
    front_rad = math.radians(front_angle_deg)
    front_center_rad = math.radians(front_center_deg)
    valid = []
    for i, d in enumerate(ranges):
        if not math.isfinite(d):
            continue
        if d < range_min or d > range_max:
            continue
        angle = angle_min + i * angle_increment - front_center_rad
        if abs(math.atan2(math.sin(angle), math.cos(angle))) <= front_rad:
            valid.append(d)
    if not valid:
        fallback = float(range_max) if math.isfinite(range_max) else 2.5
        return {"is_obstacle": False, "min_distance": fallback, "direction": "front", "risk_level": "safe", "action": "none"}
    d = min(valid)
    if d <= DANGER_DISTANCE_M:
        return {"is_obstacle": True, "min_distance": d, "direction": "front", "risk_level": "danger", "action": "stop"}
    if d <= WARNING_DISTANCE_M:
        return {"is_obstacle": True, "min_distance": d, "direction": "front", "risk_level": "warning", "action": "slow_down"}
    return {"is_obstacle": False, "min_distance": d, "direction": "front", "risk_level": "safe", "action": "none"}


def classify_scan(ranges, angle_min, angle_increment, range_min, range_max):
    """Backward-compatible entry point using the conventional zero-degree front."""
    return classify_front_scan(
        ranges,
        angle_min,
        angle_increment,
        range_min,
        range_max,
    )


class ObstacleAvoidNode(Node):
    def __init__(self, mode: str = "real"):
        super().__init__("obstacle_avoid_node")
        self.mode = mode
        self.declare_parameter("front_center_degrees", 180.0)
        self.declare_parameter("publish_hard_stop_cmd", False)
        self.front_center_degrees = float(
            self.get_parameter("front_center_degrees").value
        )
        self.publish_hard_stop_cmd = bool(
            self.get_parameter("publish_hard_stop_cmd").value
        )
        self.pub_status = self.create_publisher(ObstacleStatus, "/obstacle_status", 10)
        self.pub_cmd = self.create_publisher(Twist, "/cmd_vel_safety", 10)
        self.create_subscription(LaserScan, "/scan", self.on_scan, 10)
        self.get_logger().info(
            f"Obstacle avoid node started ({mode} mode, front=±{FRONT_SECTOR_DEGREES}°, danger={DANGER_DISTANCE_M}m, warning={WARNING_DISTANCE_M}m)")

    def on_scan(self, msg: LaserScan):
        result = classify_front_scan(
            msg.ranges, float(msg.angle_min), float(msg.angle_increment),
            float(msg.range_min), float(msg.range_max),
            front_center_deg=self.front_center_degrees)
        status = ObstacleStatus()
        status.is_obstacle = result["is_obstacle"]
        status.min_distance = result["min_distance"]
        status.direction = result["direction"]
        status.risk_level = result["risk_level"]
        status.action = result["action"]
        self.pub_status.publish(status)
        if result["risk_level"] == "danger":
            if self.publish_hard_stop_cmd:
                self.pub_cmd.publish(Twist())
            self.get_logger().warn(
                f"DANGER {result['min_distance']:.2f}m — block forward/replan",
                throttle_duration_sec=1.0,
            )
        elif result["risk_level"] == "safe":
            self.get_logger().info(f"SAFE {result['min_distance']:.2f}m", throttle_duration_sec=2.0)


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
