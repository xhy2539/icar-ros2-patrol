import json
import time
from pathlib import Path

import rclpy
from rclpy.node import Node
from rclpy.qos import DurabilityPolicy, HistoryPolicy, QoSProfile, ReliabilityPolicy
from sensor_msgs.msg import Image
from std_msgs.msg import String

try:
    from cv_bridge import CvBridge
except ImportError:  # Allows syntax checks outside a ROS image.
    CvBridge = None

try:
    import cv2
except ImportError:
    cv2 = None


def image_qos(depth=5):
    return QoSProfile(
        history=HistoryPolicy.KEEP_LAST,
        depth=depth,
        reliability=ReliabilityPolicy.BEST_EFFORT,
        durability=DurabilityPolicy.VOLATILE,
    )


class CameraProbeNode(Node):
    """Subscribe to the car camera topic and publish lightweight status JSON."""

    def __init__(self):
        super().__init__("camera_probe_node")
        self.declare_parameter("image_topic", "/camera/color/image_raw")
        self.declare_parameter("status_topic", "/vision/camera_status")
        self.declare_parameter("save_first_frame", False)
        self.declare_parameter("save_dir", "/tmp/icar_vision_samples")
        self.declare_parameter("log_every_sec", 5.0)

        self.image_topic = self.get_parameter("image_topic").value
        self.status_topic = self.get_parameter("status_topic").value
        self.save_first_frame = bool(self.get_parameter("save_first_frame").value)
        self.save_dir = Path(str(self.get_parameter("save_dir").value))
        self.log_every_sec = float(self.get_parameter("log_every_sec").value)

        self.bridge = CvBridge() if CvBridge else None
        self.frame_count = 0
        self.saved_first_frame = False
        self.started_at = time.monotonic()
        self.last_log_at = self.started_at
        self.last_log_count = 0

        self.status_pub = self.create_publisher(String, self.status_topic, 10)
        self.image_sub = self.create_subscription(
            Image,
            self.image_topic,
            self.on_image,
            image_qos(),
        )

        self.get_logger().info(
            f"Camera probe listening on {self.image_topic}, publishing {self.status_topic}"
        )
        if self.save_first_frame and (self.bridge is None or cv2 is None):
            self.get_logger().warning(
                "save_first_frame requested, but cv_bridge/cv2 is unavailable"
            )

    def on_image(self, msg):
        self.frame_count += 1
        now = time.monotonic()
        elapsed = max(now - self.started_at, 1e-6)
        fps_avg = self.frame_count / elapsed

        if self.save_first_frame and not self.saved_first_frame:
            self.save_sample(msg)

        payload = {
            "module": "vision",
            "event": "camera_frame",
            "image_topic": self.image_topic,
            "frame_count": self.frame_count,
            "width": msg.width,
            "height": msg.height,
            "encoding": msg.encoding,
            "fps_avg": round(fps_avg, 2),
            "stamp": {
                "sec": msg.header.stamp.sec,
                "nanosec": msg.header.stamp.nanosec,
            },
        }
        self.status_pub.publish(String(data=json.dumps(payload, ensure_ascii=False)))

        if now - self.last_log_at >= self.log_every_sec:
            delta_count = self.frame_count - self.last_log_count
            delta_time = max(now - self.last_log_at, 1e-6)
            fps_recent = delta_count / delta_time
            self.get_logger().info(
                f"camera ok: {msg.width}x{msg.height} {msg.encoding}, "
                f"recent fps={fps_recent:.2f}, total={self.frame_count}"
            )
            self.last_log_at = now
            self.last_log_count = self.frame_count

    def save_sample(self, msg):
        if self.bridge is None or cv2 is None:
            return
        try:
            self.save_dir.mkdir(parents=True, exist_ok=True)
            frame = self.bridge.imgmsg_to_cv2(msg, desired_encoding="bgr8")
            path = self.save_dir / "camera_first_frame.jpg"
            cv2.imwrite(str(path), frame)
            self.saved_first_frame = True
            self.get_logger().info(f"saved first camera frame to {path}")
        except Exception as exc:  # pylint: disable=broad-except
            self.saved_first_frame = True
            self.get_logger().warning(f"failed to save first frame: {exc}")


def main(args=None):
    rclpy.init(args=args)
    node = CameraProbeNode()
    try:
        rclpy.spin(node)
    finally:
        node.destroy_node()
        rclpy.shutdown()


if __name__ == "__main__":
    main()
