#!/usr/bin/env python3
"""Audible alarm for obstacle stops.

The chassis driver already subscribes to ``/Buzzer``.  This node converts
danger/stop transitions on ``/obstacle_status`` into a short three-pulse alarm,
repeats it at a bounded interval while danger persists, and publishes a JSON
status event for the App and LLM layers.
"""

import json
import time

import rclpy
from rclpy.node import Node
from std_msgs.msg import Bool, String

from icar_interfaces.msg import ObstacleStatus

from .obstacle_alarm_logic import ObstacleAlarmController


class ObstacleAlarmNode(Node):
    def __init__(self) -> None:
        super().__init__("obstacle_alarm_node")
        self.declare_parameter("repeat_sec", 5.0)
        self.declare_parameter("pulse_sec", 0.18)
        self.declare_parameter("pulse_count", 3)

        self._pulse_sec = max(0.05, float(self.get_parameter("pulse_sec").value))
        self._pulse_count = max(1, int(self.get_parameter("pulse_count").value))
        self._controller = ObstacleAlarmController(
            repeat_sec=float(self.get_parameter("repeat_sec").value)
        )
        self._external_active = set()
        self._sound_enabled = True
        self._pattern = []
        self._next_transition_at = 0.0

        self._buzzer_pub = self.create_publisher(Bool, "/Buzzer", 10)
        self._status_pub = self.create_publisher(String, "/safety/alarm", 10)
        self.create_subscription(
            ObstacleStatus, "/obstacle_status", self._on_obstacle, 10
        )
        self.create_subscription(
            String, "/safety/hazard_event", self._on_hazard_event, 10
        )
        self.create_subscription(
            Bool, "/safety/alarm_sound_enabled", self._on_sound_enabled, 10
        )
        self.create_timer(0.05, self._tick)
        self.get_logger().info("obstacle alarm ready: /obstacle_status -> /Buzzer")

    def _on_sound_enabled(self, message: Bool) -> None:
        """Mute only the buzzer; safety events and obstacle blocking continue."""
        self._sound_enabled = bool(message.data)
        if not self._sound_enabled:
            self._pattern.clear()
            self._buzzer_pub.publish(Bool(data=False))
        self.get_logger().info(
            f"obstacle alarm sound {'enabled' if self._sound_enabled else 'muted'}"
        )

    def _on_obstacle(self, message: ObstacleStatus) -> None:
        decision = self._controller.update(
            message.risk_level,
            message.action,
            time.monotonic(),
        )
        if decision.event == "none":
            return

        payload = {
            "event": decision.event,
            "active": decision.active,
            "risk_level": message.risk_level,
            "action": message.action,
            "distance": round(float(message.min_distance), 3),
            "direction": message.direction,
        }
        status = String()
        status.data = json.dumps(payload, ensure_ascii=False)
        self._status_pub.publish(status)

        if decision.should_beep:
            self._start_pattern()
            self.get_logger().warning(
                f"obstacle alarm {decision.event}: "
                f"{message.min_distance:.2f}m {message.direction}"
            )
        elif decision.event == "cleared":
            if not self._external_active:
                self._pattern.clear()
                self._buzzer_pub.publish(Bool(data=False))
            self.get_logger().info("obstacle alarm cleared")

    def _start_pattern(self) -> None:
        if not self._sound_enabled:
            return
        self._pattern = [value for _ in range(self._pulse_count) for value in (True, False)]
        self._next_transition_at = 0.0

    def _on_hazard_event(self, message: String) -> None:
        """Forward task-manager hazards and add an audible alarm pattern."""
        try:
            payload = json.loads(message.data)
            if not isinstance(payload, dict):
                raise ValueError("hazard event must be an object")
        except (json.JSONDecodeError, ValueError) as exc:
            self.get_logger().warning(f"ignored invalid hazard event: {exc}")
            return

        status = String()
        status.data = json.dumps(payload, ensure_ascii=False)
        self._status_pub.publish(status)

        hazard_type = str(payload.get("hazard_type", "external"))
        if payload.get("active"):
            self._external_active.add(hazard_type)
        else:
            self._external_active.discard(hazard_type)

        if payload.get("active") and payload.get("event") in ("started", "repeated"):
            self._start_pattern()
            self.get_logger().warning(
                f"{hazard_type} alarm "
                f"{payload.get('event')}"
            )
        elif not payload.get("active") and not self._external_active \
                and not self._controller.active:
            self._pattern.clear()
            self._buzzer_pub.publish(Bool(data=False))

    def _tick(self) -> None:
        if not self._pattern:
            return
        now = time.monotonic()
        if now < self._next_transition_at:
            return
        self._buzzer_pub.publish(Bool(data=self._pattern.pop(0)))
        self._next_transition_at = now + self._pulse_sec

    def destroy_node(self):
        self._buzzer_pub.publish(Bool(data=False))
        return super().destroy_node()


def main(args=None) -> None:
    rclpy.init(args=args)
    node = ObstacleAlarmNode()
    try:
        rclpy.spin(node)
    except KeyboardInterrupt:
        pass
    finally:
        node.destroy_node()
        rclpy.shutdown()
