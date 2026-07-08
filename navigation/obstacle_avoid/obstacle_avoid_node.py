import argparse
import sys
import time
from pathlib import Path

import rclpy
from rclpy.node import Node
from std_msgs.msg import String

CURRENT_DIR = Path(__file__).resolve().parent
PARENT_DIR = CURRENT_DIR.parent
for path in (CURRENT_DIR, PARENT_DIR):
    if str(path) not in sys.path:
        sys.path.insert(0, str(path))

from navigation_utils import dump_json_message, load_obstacle_scenarios


class ObstacleAvoidNode(Node):
    def __init__(self, scenario_name: str):
        super().__init__("obstacle_avoid_node")
        config = load_obstacle_scenarios()
        self.scenarios = config.get("scenarios", {})
        default_scenario = config.get("default_scenario", "clear")
        self.scenario_name = scenario_name if scenario_name in self.scenarios else default_scenario
        self.scenario = self.scenarios[self.scenario_name]
        self.loop = bool(self.scenario.get("loop", True))
        self.events = self.scenario.get("events", [])
        self.started_at = time.monotonic()

        self.publisher = self.create_publisher(String, "/obstacle_status", 10)
        self.create_timer(0.5, self.on_timer)
        self.get_logger().info(f"Obstacle avoid node started in mock data mode: {self.scenario_name}")

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
        event = self.current_event()
        payload = {
            "source": "obstacle_avoid_node",
            "mode": "mock",
            "scenario": self.scenario_name,
            "is_obstacle": bool(event.get("is_obstacle", False)),
            "min_distance": float(event.get("min_distance", 2.5)),
            "direction": event.get("direction", "front"),
            "risk_level": event.get("risk_level", "safe"),
            "action": event.get("action", "none"),
        }
        message = String()
        message.data = dump_json_message(payload)
        self.publisher.publish(message)


def main():
    parser = argparse.ArgumentParser(description="Obstacle avoid node running with mock data mode")
    parser.add_argument("--scenario", default="warning_then_clear", help="Obstacle scenario defined in obstacle_scenarios.yaml")
    args = parser.parse_args()

    rclpy.init()
    node = ObstacleAvoidNode(args.scenario)
    try:
        rclpy.spin(node)
    except KeyboardInterrupt:
        pass
    finally:
        node.destroy_node()
        rclpy.shutdown()


if __name__ == "__main__":
    main()
