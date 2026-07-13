import argparse
import math
import sys
import time
from pathlib import Path

from geometry_msgs.msg import Twist
from icar_interfaces.msg import ObstacleStatus
import rclpy
from rclpy.node import Node
from sensor_msgs.msg import LaserScan

CURRENT_DIR = Path(__file__).resolve().parent
PARENT_DIR = CURRENT_DIR.parent
for path in (CURRENT_DIR, PARENT_DIR):
    if str(path) not in sys.path:
        sys.path.insert(0, str(path))

from navigation_utils import load_obstacle_scenarios


DEFAULT_SAFE_DISTANCE = 2.5
FRONT_SECTOR_DEGREES = 30.0
WARNING_DISTANCE_M = 1.0
DANGER_DISTANCE_M = 0.5


def _safe_fallback_distance(range_max: float) -> float:
    if math.isfinite(range_max) and range_max > 0.0:
        return float(range_max)
    return DEFAULT_SAFE_DISTANCE


def _status_from_min_distance(min_distance: float):
    if min_distance <= DANGER_DISTANCE_M:
        return {
            "is_obstacle": True,
            "min_distance": float(min_distance),
            "direction": "front",
            "risk_level": "danger",
            "action": "stop",
        }
    if min_distance <= WARNING_DISTANCE_M:
        return {
            "is_obstacle": True,
            "min_distance": float(min_distance),
            "direction": "front",
            "risk_level": "warning",
            "action": "slow_down",
        }
    return {
        "is_obstacle": False,
        "min_distance": float(min_distance),
        "direction": "front",
        "risk_level": "safe",
        "action": "none",
    }


def classify_front_scan(
    ranges,
    angle_min: float,
    angle_increment: float,
    range_min: float,
    range_max: float,
    front_angle_deg: float = FRONT_SECTOR_DEGREES,
):
    front_angle_rad = math.radians(front_angle_deg)
    valid_distances = []

    for index, distance in enumerate(ranges):
        if not math.isfinite(distance):
            continue
        if distance < range_min or distance > range_max:
            continue

        angle = angle_min + index * angle_increment
        normalized_angle = math.atan2(math.sin(angle), math.cos(angle))
        if abs(normalized_angle) <= front_angle_rad:
            valid_distances.append(float(distance))

    if not valid_distances:
        return _status_from_min_distance(_safe_fallback_distance(range_max))

    return _status_from_min_distance(min(valid_distances))


class ObstacleAvoidNode(Node):
    def __init__(self, mode: str, scenario_name: str):
        super().__init__("obstacle_avoid_node")
        self.mode = mode
        config = load_obstacle_scenarios()
        self.scenarios = config.get("scenarios", {})
        default_scenario = config.get("default_scenario", "clear")
        self.scenario_name = scenario_name if scenario_name in self.scenarios else default_scenario
        self.scenario = self.scenarios[self.scenario_name]
        self.loop = bool(self.scenario.get("loop", True))
        self.events = self.scenario.get("events", [])
        self.started_at = time.monotonic()
        self.last_scan_at = None
        self.latest_scan_status = _status_from_min_distance(DEFAULT_SAFE_DISTANCE)

        self.publisher = self.create_publisher(ObstacleStatus, "/obstacle_status", 10)
        self.cmd_vel_publisher = self.create_publisher(Twist, "/cmd_vel_safety", 10)
        self.create_subscription(LaserScan, "/scan", self.on_scan, 10)
        self.create_timer(0.5, self.on_timer)
        if self.mode == "mock":
            self.get_logger().info(f"Obstacle avoid node started in mock data mode: {self.scenario_name}")
        else:
            self.get_logger().info("Obstacle avoid node started in real /scan mode")

    def on_scan(self, message: LaserScan):
        self.last_scan_at = time.monotonic()
        self.latest_scan_status = classify_front_scan(
            ranges=message.ranges,
            angle_min=float(message.angle_min),
            angle_increment=float(message.angle_increment),
            range_min=float(message.range_min),
            range_max=float(message.range_max),
        )

    def current_event(self):
        if not self.events:
            return {
                "is_obstacle": False,
                "min_distance": 2.5,
                "direction": "front",
                "risk_level": "safe",
                "action": "none",
            }

        total_duration = sum(float(event.get("duration_sec", 1.0)) for event in self.events)
        elapsed = time.monotonic() - self.started_at
        if self.loop and total_duration > 0:
            elapsed = elapsed % total_duration

        for event in self.events:
            duration = float(event.get("duration_sec", 1.0))
            if elapsed <= duration:
                return event
            elapsed -= duration

        return self.events[-1]

    def on_timer(self):
        event = self.current_event() if self.mode == "mock" else self.latest_scan_status
        message = ObstacleStatus()
        message.is_obstacle = bool(event.get("is_obstacle", False))
        message.min_distance = float(event.get("min_distance", 2.5))
        message.direction = event.get("direction", "front")
        message.risk_level = event.get("risk_level", "safe")
        message.action = event.get("action", "none")
        self.publisher.publish(message)

        if message.risk_level == "danger":
            stop = Twist()
            stop.linear.x = 0.0
            stop.angular.z = 0.0
            self.cmd_vel_publisher.publish(stop)


def main():
    parser = argparse.ArgumentParser(description="Obstacle avoid node for real /scan or mock scenarios")
    parser.add_argument("--mode", choices=["real", "mock"], default="real", help="Use real /scan data or mock scenario data")
    parser.add_argument("--scenario", default="warning_then_clear", help="Obstacle scenario defined in obstacle_scenarios.yaml")
    args = parser.parse_args()

    rclpy.init()
    node = ObstacleAvoidNode(args.mode, args.scenario)
    try:
        rclpy.spin(node)
    except KeyboardInterrupt:
        pass
    finally:
        node.destroy_node()
        rclpy.shutdown()


if __name__ == "__main__":
    main()
