#!/usr/bin/env python3
"""Mock vision node.

Publishes deterministic DetectionArray messages. Real vision only needs to
replace this publisher with camera/YOLO output using the same message schema.
"""

import rclpy
from rclpy.node import Node
from rclpy.qos import QoSProfile, ReliabilityPolicy

from icar_interfaces.msg import Detection, DetectionArray


class MockVisionNode(Node):
    def __init__(self):
        super().__init__("mock_vision_node")
        qos = QoSProfile(depth=10, reliability=ReliabilityPolicy.BEST_EFFORT)
        self.publisher = self.create_publisher(
            DetectionArray, "/vision/detections", qos
        )
        self.declare_parameter("period_sec", 1.5)
        self._frame_id = 0
        period = float(self.get_parameter("period_sec").value)
        self.timer = self.create_timer(period, self._publish_detection)
        self.get_logger().info("mock_vision_node ready")

    def _publish_detection(self):
        self._frame_id += 1
        msg = DetectionArray()
        msg.header.stamp = self.get_clock().now().to_msg()
        msg.header.frame_id = "mock_camera"

        det = Detection()
        det.class_name = "person" if self._frame_id % 2 else "sign"
        det.confidence = 0.86
        det.x_min = 120
        det.y_min = 80
        det.x_max = 300
        det.y_max = 420
        det.image_path = f"logs/images/mock_frame_{self._frame_id:04d}.jpg"
        msg.detections.append(det)
        self.publisher.publish(msg)


def main(args=None):
    rclpy.init(args=args)
    node = MockVisionNode()
    try:
        rclpy.spin(node)
    except KeyboardInterrupt:
        node.get_logger().info("mock_vision_node interrupted")
    finally:
        node.destroy_node()
        rclpy.shutdown()


if __name__ == "__main__":
    main()
