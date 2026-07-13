import time

import rclpy
from geometry_msgs.msg import Twist
from rclpy.node import Node
from std_msgs.msg import Bool


class VelocityMuxNode(Node):
    """Small, explicit priority mux for the control sources used by this project."""

    SOURCES = (
        ("safety", "/cmd_vel_safety", 1.0),
        ("app", "/cmd_vel_app", 0.4),
        ("tracking", "/vision/target_cmd_vel", 0.3),
        ("joy", "/cmd_vel_joy", 0.4),
        ("nav", "/cmd_vel_nav", 0.6),
    )

    def __init__(self) -> None:
        super().__init__("velocity_mux")
        self._messages = {}
        self._timestamps = {}
        self._estop = False
        self._publisher = self.create_publisher(Twist, "/cmd_vel", 10)
        for name, topic, _timeout in self.SOURCES:
            self.create_subscription(
                Twist, topic, lambda msg, n=name: self._receive(n, msg), 10
            )
        self.create_subscription(Bool, "/safety_stop", self._set_estop, 10)
        self.create_timer(0.05, self._tick)

    def _receive(self, name: str, message: Twist) -> None:
        self._messages[name] = message
        self._timestamps[name] = time.monotonic()

    def _set_estop(self, message: Bool) -> None:
        self._estop = bool(message.data)
        self.get_logger().warning(f"safety stop {'ACTIVE' if self._estop else 'cleared'}")

    def _tick(self) -> None:
        if self._estop:
            self._publisher.publish(Twist())
            return
        now = time.monotonic()
        for name, _topic, timeout in self.SOURCES:
            if now - self._timestamps.get(name, 0.0) <= timeout:
                self._publisher.publish(self._messages[name])
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
