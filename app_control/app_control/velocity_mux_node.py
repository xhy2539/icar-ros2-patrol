import time

import rclpy
from geometry_msgs.msg import Twist
from icar_interfaces.msg import ObstacleStatus
from rclpy.node import Node
from std_msgs.msg import Bool

from .velocity_safety_logic import constrain_for_obstacle


class VelocityMuxNode(Node):
    """Small, explicit priority mux for the control sources used by this project."""

    SOURCES = (
        ("app", "/cmd_vel_app", 0.4),
        ("cloud", "/cmd_vel_cloud", 0.4),
        ("tracking", "/vision/target_cmd_vel", 0.3),
        ("joy", "/cmd_vel_joy", 0.4),
        ("nav", "/cmd_vel_nav", 0.6),
    )

    def __init__(self) -> None:
        super().__init__("velocity_mux")
        self._messages = {}
        self._timestamps = {}
        self._estop = False
        self._obstacle_avoidance_enabled = True
        self._obstacle_risk = "safe"
        self._obstacle_action = "none"
        self._obstacle_direction = "front"
        self.declare_parameter("warning_max_linear", 0.12)
        self._warning_max_linear = float(
            self.get_parameter("warning_max_linear").value
        )
        self._publisher = self.create_publisher(Twist, "/cmd_vel", 10)
        for name, topic, _timeout in self.SOURCES:
            self.create_subscription(
                Twist, topic, lambda msg, n=name: self._receive(n, msg), 10
            )
        self.create_subscription(Bool, "/safety_stop", self._set_estop, 10)
        self.create_subscription(
            Bool,
            "/safety/obstacle_avoidance_enabled",
            self._set_obstacle_avoidance_enabled,
            10,
        )
        self.create_subscription(
            ObstacleStatus, "/obstacle_status", self._set_obstacle, 10
        )
        self.create_timer(0.05, self._tick)

    def _receive(self, name: str, message: Twist) -> None:
        self._messages[name] = message
        self._timestamps[name] = time.monotonic()

    def _set_estop(self, message: Bool) -> None:
        self._estop = bool(message.data)
        self.get_logger().warning(f"safety stop {'ACTIVE' if self._estop else 'cleared'}")

    def _set_obstacle_avoidance_enabled(self, message: Bool) -> None:
        self._obstacle_avoidance_enabled = bool(message.data)
        state = "enabled" if self._obstacle_avoidance_enabled else "DISABLED"
        self.get_logger().warning(f"obstacle velocity limiting {state}")

    def _set_obstacle(self, message: ObstacleStatus) -> None:
        self._obstacle_risk = message.risk_level
        self._obstacle_action = message.action
        self._obstacle_direction = message.direction

    def _safe_command(self, message: Twist) -> Twist:
        if not self._obstacle_avoidance_enabled:
            return message
        safe = constrain_for_obstacle(
            message.linear.x,
            message.linear.y,
            message.angular.z,
            self._obstacle_risk,
            self._obstacle_action,
            self._obstacle_direction,
            self._warning_max_linear,
        )
        output = Twist()
        output.linear.x = safe.linear_x
        output.linear.y = safe.linear_y
        output.linear.z = message.linear.z
        output.angular.x = message.angular.x
        output.angular.y = message.angular.y
        output.angular.z = safe.angular_z
        return output

    def _tick(self) -> None:
        if self._estop:
            self._publisher.publish(Twist())
            return
        now = time.monotonic()
        for name, _topic, timeout in self.SOURCES:
            if now - self._timestamps.get(name, 0.0) <= timeout:
                self._publisher.publish(self._safe_command(self._messages[name]))
                return
        self._publisher.publish(Twist())


def main(args=None) -> None:
    rclpy.init(args=args)
    node = VelocityMuxNode()
    try:
        rclpy.spin(node)
    except KeyboardInterrupt:
        pass
    finally:
        node.destroy_node()
        rclpy.shutdown()
