import argparse
import math
import sys
import time
from pathlib import Path

from geometry_msgs.msg import Twist
import rclpy
from rclpy.node import Node
from sensor_msgs.msg import LaserScan
from std_msgs.msg import String

# icar_interfaces is required for formal deployment; fall back to String for
# real-car debugging where the package is not yet built.
try:
    from icar_interfaces.msg import ObstacleStatus

    HAVE_ICAR_INTERFACES = True
except ImportError:
    ObstacleStatus = None
    HAVE_ICAR_INTERFACES = False

CURRENT_DIR = Path(__file__).resolve().parent
PARENT_DIR = CURRENT_DIR.parent
for path in (CURRENT_DIR, PARENT_DIR):
    if str(path) not in sys.path:
        sys.path.insert(0, str(path))

from navigation_utils import load_obstacle_scenarios


DEFAULT_SAFE_DISTANCE = 2.5
DEFAULT_FRONT_SECTOR_DEGREES = 90.0
WARNING_DISTANCE_M = 1.0
DANGER_DISTANCE_M = 0.5

# When the target front sector returns no valid readings, the fallback
# progressively widens the search window by these steps until a valid
# reading is found or the full 360 deg is exhausted.
FALLBACK_SECTOR_STEPS = [45.0, 90.0, 180.0]


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


def _collect_sector_distances(ranges, angle_min, angle_increment,
                               range_min, range_max, center_angle_rad,
                               half_sector_rad):
    """Return valid distances within the specified sector (radians)."""
    valid = []
    for index, distance in enumerate(ranges):
        if not math.isfinite(distance):
            continue
        if distance < range_min or distance > range_max:
            continue
        angle = angle_min + index * angle_increment
        # angular distance from sector center, wrapped to [-pi, pi]
        diff = math.atan2(math.sin(angle - center_angle_rad),
                          math.cos(angle - center_angle_rad))
        if abs(diff) <= half_sector_rad:
            valid.append(float(distance))
    return valid


def classify_front_scan(
    ranges,
    angle_min: float,
    angle_increment: float,
    range_min: float,
    range_max: float,
    front_angle_deg: float = DEFAULT_FRONT_SECTOR_DEGREES,
    front_angle_offset_deg: float = 0.0,
):
    """Classify obstacle risk based on the closest object in the front sector.

    When the requested front sector contains no valid readings (e.g. due to
    lidar blind spots or chassis occlusion), the function progressively
    widens the search window up to the full 360 deg rather than silently
    reporting SAFE.
    """
    front_angle_rad = math.radians(front_angle_deg)
    center_angle_rad = math.radians(front_angle_offset_deg)

    valid_distances = _collect_sector_distances(
        ranges, angle_min, angle_increment, range_min, range_max,
        center_angle_rad, front_angle_rad,
    )

    if valid_distances:
        return _status_from_min_distance(min(valid_distances))

    # Primary front sector is empty — try progressively wider sectors.
    for step_deg in FALLBACK_SECTOR_STEPS:
        wider_half = math.radians(step_deg)
        valid_distances = _collect_sector_distances(
            ranges, angle_min, angle_increment, range_min, range_max,
            center_angle_rad, wider_half,
        )
        if valid_distances:
            return _status_from_min_distance(min(valid_distances))

    # Nothing valid anywhere — assume safe with range_max.
    return _status_from_min_distance(_safe_fallback_distance(range_max))


class ObstacleAvoidNode(Node):
    def __init__(self, mode: str, scenario_name: str):
        super().__init__("obstacle_avoid_node")

        # -- ROS2 parameters --------------------------------------------------
        self.declare_parameter("front_sector_deg", DEFAULT_FRONT_SECTOR_DEGREES)
        self.declare_parameter("front_angle_offset_deg", 0.0)
        self.declare_parameter("warning_distance_m", WARNING_DISTANCE_M)
        self.declare_parameter("danger_distance_m", DANGER_DISTANCE_M)

        self.front_sector_deg = float(
            self.get_parameter("front_sector_deg").value
        )
        self.front_angle_offset_deg = float(
            self.get_parameter("front_angle_offset_deg").value
        )
        # Expose thresholds so node-level classify_front_scan calls use them.
        self.warning_distance_m = float(
            self.get_parameter("warning_distance_m").value
        )
        self.danger_distance_m = float(
            self.get_parameter("danger_distance_m").value
        )

        # -- mode & scenarios -------------------------------------------------
        self.mode = mode
        config = load_obstacle_scenarios()
        self.scenarios = config.get("scenarios", {})
        default_scenario = config.get("default_scenario", "clear")
        self.scenario_name = (
            scenario_name if scenario_name in self.scenarios else default_scenario
        )
        self.scenario = self.scenarios[self.scenario_name]
        self.loop = bool(self.scenario.get("loop", True))
        self.events = self.scenario.get("events", [])
        self.started_at = time.monotonic()
        self.last_scan_at = None
        self.latest_scan_status = _status_from_min_distance(DEFAULT_SAFE_DISTANCE)
        self.empty_front_logged = False

        # -- publishers & subscribers -----------------------------------------
        if HAVE_ICAR_INTERFACES:
            self.obstacle_pub = self.create_publisher(ObstacleStatus, "/obstacle_status", 10)
        else:
            self.obstacle_pub = self.create_publisher(String, "/obstacle_status", 10)
        self.cmd_vel_publisher = self.create_publisher(Twist, "/cmd_vel", 10)
        self.create_subscription(LaserScan, "/scan", self.on_scan, 10)
        self.create_timer(0.5, self.on_timer)

        if self.mode == "mock":
            self.get_logger().info(
                f"Obstacle avoid node started in mock mode: {self.scenario_name}"
            )
        else:
            self.get_logger().info(
                "Obstacle avoid node started in real /scan mode "
                f"(front_sector={self.front_sector_deg}deg, "
                f"offset={self.front_angle_offset_deg}deg, "
                f"warning={self.warning_distance_m}m, "
                f"danger={self.danger_distance_m}m)"
            )
            if not HAVE_ICAR_INTERFACES:
                self.get_logger().warning(
                    "icar_interfaces not available; publishing String on /obstacle_status"
                )

    def on_scan(self, message: LaserScan):
        self.last_scan_at = time.monotonic()
        status = classify_front_scan(
            ranges=message.ranges,
            angle_min=float(message.angle_min),
            angle_increment=float(message.angle_increment),
            range_min=float(message.range_min),
            range_max=float(message.range_max),
            front_angle_deg=self.front_sector_deg,
            front_angle_offset_deg=self.front_angle_offset_deg,
        )
        # Override threshold constants in the returned status so they match
        # the node-level parameterised values.
        min_d = status["min_distance"]
        if min_d <= self.danger_distance_m:
            status.update(risk_level="danger", action="stop", is_obstacle=True)
        elif min_d <= self.warning_distance_m:
            status.update(risk_level="warning", action="slow_down", is_obstacle=True)
        else:
            status.update(risk_level="safe", action="none", is_obstacle=False)

        if status["risk_level"] == "danger" and not self.empty_front_logged:
            sector_info = (
                f"{self.front_sector_deg}deg sector had no valid points; "
                "using widened fallback"
            )
            self.get_logger().warning(
                f"Obstacle DANGER at {min_d:.2f}m — {sector_info}",
                throttle_duration_sec=5.0,
            )

        self.latest_scan_status = status

    def _publish_obstacle_status(self, event):
        if HAVE_ICAR_INTERFACES:
            msg = ObstacleStatus()
            msg.is_obstacle = bool(event.get("is_obstacle", False))
            msg.min_distance = float(event.get("min_distance", 2.5))
            msg.direction = event.get("direction", "front")
            msg.risk_level = event.get("risk_level", "safe")
            msg.action = event.get("action", "none")
            self.obstacle_pub.publish(msg)
        else:
            import json
            payload = json.dumps(
                {
                    "is_obstacle": bool(event.get("is_obstacle", False)),
                    "min_distance": float(event.get("min_distance", 2.5)),
                    "direction": event.get("direction", "front"),
                    "risk_level": event.get("risk_level", "safe"),
                    "action": event.get("action", "none"),
                },
                ensure_ascii=False,
            )
            self.obstacle_pub.publish(String(data=payload))

    def current_event(self):
        if not self.events:
            return {
                "is_obstacle": False,
                "min_distance": 2.5,
                "direction": "front",
                "risk_level": "safe",
                "action": "none",
            }

        total_duration = sum(
            float(event.get("duration_sec", 1.0)) for event in self.events
        )
        elapsed = time.monotonic() - self.started_at
        if self.loop and total_duration > 0:
            elapsed = elapsed % total_duration

        cursor = 0.0
        for event in self.events:
            duration = float(event.get("duration_sec", 1.0))
            if elapsed <= cursor + duration:
                return event
            cursor += duration

        return self.events[-1]

    def on_timer(self):
        event = self.current_event() if self.mode == "mock" else self.latest_scan_status
        self._publish_obstacle_status(event)

        risk = event.get("risk_level", "safe")
        if risk == "danger":
            stop = Twist()
            stop.linear.x = 0.0
            stop.angular.z = 0.0
            self.cmd_vel_publisher.publish(stop)
        elif risk == "warning":
            slow = Twist()
            slow.linear.x = 0.05
            slow.angular.z = 0.0
            self.cmd_vel_publisher.publish(slow)


def main():
    parser = argparse.ArgumentParser(
        description="Obstacle avoid node for real /scan or mock scenarios"
    )
    parser.add_argument(
        "--mode",
        choices=["real", "mock"],
        default="real",
        help="Use real /scan data or mock scenario data",
    )
    parser.add_argument(
        "--scenario",
        default="warning_then_clear",
        help="Obstacle scenario defined in obstacle_scenarios.yaml",
    )
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
