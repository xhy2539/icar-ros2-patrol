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
except ImportError:
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


class DatasetRecorderNode(Node):
    """Save camera frames on demand or at a bounded interval."""

    def __init__(self):
        super().__init__("dataset_recorder_node")
        self.declare_parameter("image_topic", "/camera/color/image_raw")
        self.declare_parameter("command_topic", "/vision/capture_command")
        self.declare_parameter("status_topic", "/vision/capture_status")
        self.declare_parameter("save_dir", "/tmp/icar_vision_dataset")
        self.declare_parameter("auto_interval_sec", 0.0)
        self.declare_parameter("max_images", 200)
        self.declare_parameter("jpeg_quality", 90)
        self.declare_parameter("prefix", "vision")

        self.image_topic = self.get_parameter("image_topic").value
        self.command_topic = self.get_parameter("command_topic").value
        self.status_topic = self.get_parameter("status_topic").value
        self.save_dir = Path(str(self.get_parameter("save_dir").value))
        self.auto_interval_sec = float(self.get_parameter("auto_interval_sec").value)
        self.max_images = int(self.get_parameter("max_images").value)
        self.jpeg_quality = int(self.get_parameter("jpeg_quality").value)
        self.prefix = self.get_parameter("prefix").value

        self.bridge = CvBridge() if CvBridge else None
        self.latest_msg = None
        self.saved_count = 0
        self.last_auto_save_at = 0.0
        self.enabled = self.auto_interval_sec > 0.0

        self.status_pub = self.create_publisher(String, self.status_topic, 10)
        self.image_sub = self.create_subscription(
            Image,
            self.image_topic,
            self.on_image,
            image_qos(),
        )
        self.command_sub = self.create_subscription(
            String,
            self.command_topic,
            self.on_command,
            10,
        )

        self.get_logger().info(
            f"Dataset recorder listening on {self.image_topic}; "
            f"commands={self.command_topic}; save_dir={self.save_dir}; "
            f"auto_interval_sec={self.auto_interval_sec}; max_images={self.max_images}"
        )
        if self.bridge is None or cv2 is None:
            self.get_logger().warning("cv_bridge/cv2 unavailable; image saving disabled")

    def on_image(self, msg):
        self.latest_msg = msg
        if not self.enabled or self.auto_interval_sec <= 0:
            return
        now = time.monotonic()
        if now - self.last_auto_save_at < self.auto_interval_sec:
            return
        self.last_auto_save_at = now
        self.save_latest(reason="auto_interval")

    def on_command(self, msg):
        try:
            command = json.loads(msg.data)
        except json.JSONDecodeError:
            command = {"action": msg.data.strip()}

        action = str(command.get("action", "")).lower()
        if action in ("capture_once", "capture", "save"):
            self.save_latest(reason=action, tag=command.get("tag"))
        elif action in ("start_interval", "set_interval"):
            interval = float(command.get("interval_sec", self.auto_interval_sec or 2.0))
            self.auto_interval_sec = max(0.1, interval)
            self.enabled = True
            self.publish_status("interval_started", {"interval_sec": self.auto_interval_sec})
        elif action in ("stop_interval", "stop"):
            self.enabled = False
            self.publish_status("interval_stopped", {})
        elif action == "set_max_images":
            self.max_images = max(1, int(command.get("max_images", self.max_images)))
            self.publish_status("max_images_updated", {"max_images": self.max_images})
        else:
            self.publish_status(
                "unknown_command",
                {"raw": msg.data, "supported": ["capture_once", "set_interval", "stop"]},
            )

    def save_latest(self, reason, tag=None):
        if self.latest_msg is None:
            self.publish_status("no_frame", {"reason": reason, "tag": tag})
            return
        if self.saved_count >= self.max_images:
            self.publish_status(
                "max_images_reached",
                {"max_images": self.max_images, "reason": reason, "tag": tag},
            )
            return
        if self.bridge is None or cv2 is None:
            self.publish_status("save_unavailable", {"reason": reason, "tag": tag})
            return

        try:
            self.save_dir.mkdir(parents=True, exist_ok=True)
            frame = self.bridge.imgmsg_to_cv2(self.latest_msg, desired_encoding="bgr8")
            stamp = self.latest_msg.header.stamp
            timestamp = f"{stamp.sec}_{stamp.nanosec:09d}"
            tag_part = f"_{self.safe_name(tag)}" if tag else ""
            filename = f"{self.prefix}_{timestamp}_{self.saved_count:04d}{tag_part}.jpg"
            path = self.save_dir / filename
            ok = cv2.imwrite(
                str(path),
                frame,
                [int(cv2.IMWRITE_JPEG_QUALITY), self.jpeg_quality],
            )
            if not ok:
                self.publish_status(
                    "save_failed", {"path": str(path), "reason": reason, "tag": tag}
                )
                return
            self.saved_count += 1
            self.publish_status(
                "image_saved",
                {
                    "path": str(path),
                    "count": self.saved_count,
                    "reason": reason,
                    "tag": tag,
                    "width": self.latest_msg.width,
                    "height": self.latest_msg.height,
                },
            )
        except Exception as exc:  # pylint: disable=broad-except
            self.publish_status(
                "save_exception", {"error": str(exc), "reason": reason, "tag": tag}
            )

    def publish_status(self, event, data):
        payload = {
            "module": "vision",
            "event": event,
            "image_topic": self.image_topic,
            "save_dir": str(self.save_dir),
            "saved_count": self.saved_count,
            "auto_interval_sec": self.auto_interval_sec,
            "enabled": self.enabled,
            "data": data,
        }
        self.status_pub.publish(String(data=json.dumps(payload, ensure_ascii=False)))
        if event in ("image_saved", "max_images_reached", "save_exception"):
            self.get_logger().info(json.dumps(payload, ensure_ascii=False))

    @staticmethod
    def safe_name(value):
        if value is None:
            return ""
        allowed = "abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789_-"
        return "".join(ch if ch in allowed else "_" for ch in str(value))[:40]


def main(args=None):
    rclpy.init(args=args)
    node = DatasetRecorderNode()
    try:
        rclpy.spin(node)
    finally:
        node.destroy_node()
        rclpy.shutdown()


if __name__ == "__main__":
    main()
