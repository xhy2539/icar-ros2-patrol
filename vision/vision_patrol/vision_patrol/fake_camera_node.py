import math

import rclpy
from rclpy.node import Node
from rclpy.qos import DurabilityPolicy, HistoryPolicy, QoSProfile, ReliabilityPolicy
from sensor_msgs.msg import Image

try:
    from cv_bridge import CvBridge
except ImportError:
    CvBridge = None

try:
    import cv2
    import numpy as np
except ImportError:
    cv2 = None
    np = None


def image_qos(depth=5):
    return QoSProfile(
        history=HistoryPolicy.KEEP_LAST,
        depth=depth,
        reliability=ReliabilityPolicy.BEST_EFFORT,
        durability=DurabilityPolicy.VOLATILE,
    )


class FakeCameraNode(Node):
    """Publish a synthetic camera feed for off-car vision development."""

    def __init__(self):
        super().__init__("fake_camera_node")
        self.declare_parameter("image_topic", "/camera/color/image_raw")
        self.declare_parameter("width", 640)
        self.declare_parameter("height", 480)
        self.declare_parameter("fps", 15.0)
        self.declare_parameter("scenario", "patrol")

        self.image_topic = self.get_parameter("image_topic").value
        self.width = int(self.get_parameter("width").value)
        self.height = int(self.get_parameter("height").value)
        self.fps = float(self.get_parameter("fps").value)
        self.scenario = self.get_parameter("scenario").value

        self.bridge = CvBridge() if CvBridge else None
        self.publisher = self.create_publisher(Image, self.image_topic, image_qos())
        self.frame_index = 0
        timer_period = 1.0 / max(self.fps, 1.0)
        self.timer = self.create_timer(timer_period, self.publish_frame)

        self.get_logger().info(
            f"Fake camera publishing {self.width}x{self.height} {self.fps:.1f}Hz "
            f"on {self.image_topic}, scenario={self.scenario}"
        )
        if self.bridge is None or cv2 is None or np is None:
            self.get_logger().error(
                "fake_camera requires cv_bridge, cv2 and numpy in the ROS2 environment"
            )

    def publish_frame(self):
        if self.bridge is None or cv2 is None or np is None:
            return
        frame = self.render_frame()
        msg = self.bridge.cv2_to_imgmsg(frame, encoding="bgr8")
        msg.header.stamp = self.get_clock().now().to_msg()
        msg.header.frame_id = "fake_camera"
        self.publisher.publish(msg)
        self.frame_index += 1

    def render_frame(self):
        frame = np.full((self.height, self.width, 3), (42, 48, 52), dtype=np.uint8)
        self.draw_floor(frame)
        self.draw_lanes(frame)
        self.draw_targets(frame)
        self.draw_hud(frame)
        return frame

    def draw_floor(self, frame):
        horizon = int(self.height * 0.42)
        frame[:horizon, :] = (58, 64, 70)
        frame[horizon:, :] = (55, 55, 55)
        for y in range(horizon, self.height, 28):
            shade = 50 + ((y // 28) % 2) * 10
            cv2.line(frame, (0, y), (self.width, y), (shade, shade, shade), 1)

    def draw_lanes(self, frame):
        t = self.frame_index / 18.0
        offset = int(math.sin(t) * 32)
        bottom_y = self.height - 1
        horizon_y = int(self.height * 0.46)
        left_bottom = (int(self.width * 0.28) + offset, bottom_y)
        left_top = (int(self.width * 0.43) + offset // 2, horizon_y)
        right_bottom = (int(self.width * 0.72) + offset, bottom_y)
        right_top = (int(self.width * 0.57) + offset // 2, horizon_y)
        cv2.line(frame, left_bottom, left_top, (245, 245, 245), 8)
        cv2.line(frame, right_bottom, right_top, (245, 245, 245), 8)
        center_bottom = (self.width // 2 + offset, bottom_y)
        center_top = (self.width // 2 + offset // 2, horizon_y)
        cv2.line(frame, center_bottom, center_top, (60, 210, 255), 4)

    def draw_targets(self, frame):
        t = self.frame_index / 12.0
        obstacle_x = int(self.width * 0.50 + math.sin(t) * 80)
        obstacle_y = int(self.height * 0.67)
        cv2.rectangle(
            frame,
            (obstacle_x - 36, obstacle_y - 42),
            (obstacle_x + 36, obstacle_y + 42),
            (0, 0, 230),
            -1,
        )
        cv2.putText(
            frame,
            "obstacle",
            (obstacle_x - 48, obstacle_y - 52),
            cv2.FONT_HERSHEY_SIMPLEX,
            0.55,
            (255, 255, 255),
            2,
            cv2.LINE_AA,
        )

        sign_x = int(self.width * 0.76)
        sign_y = int(self.height * 0.48 + math.cos(t * 0.7) * 18)
        cv2.rectangle(
            frame,
            (sign_x - 28, sign_y - 28),
            (sign_x + 28, sign_y + 28),
            (0, 190, 0),
            -1,
        )
        cv2.putText(
            frame,
            "A",
            (sign_x - 12, sign_y + 14),
            cv2.FONT_HERSHEY_SIMPLEX,
            1.2,
            (255, 255, 255),
            3,
            cv2.LINE_AA,
        )

        person_x = int(self.width * 0.21)
        person_y = int(self.height * 0.58)
        cv2.circle(frame, (person_x, person_y - 34), 18, (0, 220, 220), -1)
        cv2.rectangle(
            frame,
            (person_x - 18, person_y - 14),
            (person_x + 18, person_y + 54),
            (0, 220, 220),
            -1,
        )

    def draw_hud(self, frame):
        cv2.putText(
            frame,
            f"fake camera frame {self.frame_index}",
            (12, 28),
            cv2.FONT_HERSHEY_SIMPLEX,
            0.7,
            (230, 230, 230),
            2,
            cv2.LINE_AA,
        )


def main(args=None):
    rclpy.init(args=args)
    node = FakeCameraNode()
    try:
        rclpy.spin(node)
    finally:
        node.destroy_node()
        rclpy.shutdown()


if __name__ == "__main__":
    main()
