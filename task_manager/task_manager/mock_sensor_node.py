#!/usr/bin/env python3
"""Mock sensor node.

Publishes stable environment data to /sensor/env_data and can optionally
publish one warning alert. Real sensor work only needs to match EnvData and
SensorAlert message fields.
"""

import rclpy
from rclpy.node import Node
from rclpy.qos import QoSProfile, ReliabilityPolicy

from icar_interfaces.msg import EnvData, SensorAlert


class MockSensorNode(Node):
    def __init__(self):
        super().__init__("mock_sensor_node")
        qos = QoSProfile(depth=10, reliability=ReliabilityPolicy.RELIABLE)
        self.env_pub = self.create_publisher(EnvData, "/sensor/env_data", qos)
        self.alert_pub = self.create_publisher(SensorAlert, "/sensor/alert", qos)
        self.declare_parameter("sample_period_sec", 1.0)
        self.declare_parameter("publish_warning", False)
        self._tick = 0
        period = float(self.get_parameter("sample_period_sec").value)
        self.timer = self.create_timer(period, self._publish_env)
        self.get_logger().info("mock_sensor_node ready")

    def _publish_env(self):
        self._tick += 1
        msg = EnvData()
        msg.header.stamp = self.get_clock().now().to_msg()
        msg.header.frame_id = "mock_sensor"
        msg.temperature = 28.0 + (self._tick % 3) * 0.2
        msg.humidity = 61.0
        msg.smoke = 8.0
        msg.pm25 = 35.0 + (self._tick % 5)
        msg.light = 320.0
        msg.pressure = 1013.2
        self.env_pub.publish(msg)

        if self.get_parameter("publish_warning").value and self._tick == 5:
            alert = SensorAlert()
            alert.sensor_type = "pm25"
            alert.current_value = 155.0
            alert.threshold = 150.0
            alert.severity = "WARN"
            alert.message = "mock PM2.5 warning for integration test"
            self.alert_pub.publish(alert)


def main(args=None):
    rclpy.init(args=args)
    node = MockSensorNode()
    try:
        rclpy.spin(node)
    except KeyboardInterrupt:
        node.get_logger().info("mock_sensor_node interrupted")
    finally:
        node.destroy_node()
        rclpy.shutdown()


if __name__ == "__main__":
    main()
