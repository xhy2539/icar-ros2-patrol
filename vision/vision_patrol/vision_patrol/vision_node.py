import json
import time

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


class VisionNode(Node):
    """Camera-driven vision pipeline placeholder for detection and road work."""

    def __init__(self):
        super().__init__("vision_node")
        self.declare_parameter("image_topic", "/camera/color/image_raw")
        self.declare_parameter("detections_topic", "/vision/detections")
        self.declare_parameter("annotated_topic", "/vision/annotated_image")
        self.declare_parameter("mode", "detect")
        self.declare_parameter("publish_annotated", False)
        self.declare_parameter("enable_road_detection", False)
        self.declare_parameter("min_color_area", 600.0)

        self.image_topic = self.get_parameter("image_topic").value
        self.detections_topic = self.get_parameter("detections_topic").value
        self.annotated_topic = self.get_parameter("annotated_topic").value
        self.mode = self.get_parameter("mode").value
        self.publish_annotated = bool(self.get_parameter("publish_annotated").value)
        self.enable_road_detection = bool(
            self.get_parameter("enable_road_detection").value
        )
        self.min_color_area = float(self.get_parameter("min_color_area").value)

        self.bridge = CvBridge() if CvBridge else None
        self.frame_count = 0
        self.started_at = time.monotonic()

        self.detections_pub = self.create_publisher(String, self.detections_topic, 10)
        self.annotated_pub = None
        if self.publish_annotated:
            self.annotated_pub = self.create_publisher(Image, self.annotated_topic, 10)

        self.image_sub = self.create_subscription(
            Image,
            self.image_topic,
            self.on_image,
            image_qos(),
        )

        self.get_logger().info(
            f"Vision node mode={self.mode}, image_topic={self.image_topic}, "
            f"detections_topic={self.detections_topic}"
        )
        if self.bridge is None:
            self.get_logger().warning(
                "cv_bridge is unavailable; publishing metadata-only detections"
            )

    def on_image(self, msg):
        self.frame_count += 1
        frame = self.to_cv_frame(msg)

        detections = self.run_object_detection(frame)
        road = self.run_road_detection(frame)

        payload = {
            "module": "vision",
            "event": "frame_processed",
            "mode": self.mode,
            "image_topic": self.image_topic,
            "frame_count": self.frame_count,
            "stamp": {
                "sec": msg.header.stamp.sec,
                "nanosec": msg.header.stamp.nanosec,
            },
            "frame": {
                "width": msg.width,
                "height": msg.height,
                "encoding": msg.encoding,
            },
            "detections": detections,
            "road": road,
        }
        self.detections_pub.publish(String(data=json.dumps(payload, ensure_ascii=False)))

        if self.annotated_pub is not None and frame is not None:
            annotated = self.draw_annotations(frame.copy(), detections, road)
            try:
                self.annotated_pub.publish(
                    self.bridge.cv2_to_imgmsg(annotated, encoding="bgr8")
                )
            except Exception as exc:  # pylint: disable=broad-except
                self.get_logger().warning(f"failed to publish annotated image: {exc}")

    def to_cv_frame(self, msg):
        if self.bridge is None:
            return None
        try:
            return self.bridge.imgmsg_to_cv2(msg, desired_encoding="bgr8")
        except Exception as exc:  # pylint: disable=broad-except
            self.get_logger().warning(f"failed to convert image frame: {exc}")
            return None

    def run_object_detection(self, frame):
        if frame is None or cv2 is None or np is None:
            return []
        # Lightweight simulation detector. YOLO can replace this method later.
        color_specs = [
            ("obstacle", (0, 90, 90), (10, 255, 255), "red"),
            ("obstacle", (170, 90, 90), (180, 255, 255), "red"),
            ("sign", (35, 70, 60), (90, 255, 255), "green"),
            ("person", (20, 80, 80), (34, 255, 255), "yellow"),
        ]
        hsv = cv2.cvtColor(frame, cv2.COLOR_BGR2HSV)
        detections = []
        for class_name, lower, upper, color_name in color_specs:
            mask = cv2.inRange(hsv, np.array(lower), np.array(upper))
            mask = cv2.morphologyEx(mask, cv2.MORPH_OPEN, np.ones((5, 5), np.uint8))
            contours, _ = cv2.findContours(
                mask, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE
            )
            for contour in contours:
                area = cv2.contourArea(contour)
                if area < self.min_color_area:
                    continue
                x, y, w, h = cv2.boundingRect(contour)
                detections.append(
                    {
                        "class_name": class_name,
                        "confidence": round(min(0.99, 0.45 + area / 12000.0), 2),
                        "bbox": [int(x), int(y), int(x + w), int(y + h)],
                        "source": f"color_{color_name}",
                    }
                )
        return detections

    def run_road_detection(self, frame):
        if not self.enable_road_detection or frame is None or cv2 is None or np is None:
            return {"enabled": self.enable_road_detection, "lanes": []}
        height, width = frame.shape[:2]
        roi_y = int(height * 0.45)
        roi = frame[roi_y:, :]
        gray = cv2.cvtColor(roi, cv2.COLOR_BGR2GRAY)
        blur = cv2.GaussianBlur(gray, (5, 5), 0)
        edges = cv2.Canny(blur, 60, 150)
        lines = cv2.HoughLinesP(
            edges,
            rho=1,
            theta=np.pi / 180,
            threshold=45,
            minLineLength=45,
            maxLineGap=30,
        )
        lanes = []
        if lines is not None:
            for line in lines[:8]:
                x1, y1, x2, y2 = line[0]
                y1 += roi_y
                y2 += roi_y
                dx = x2 - x1
                dy = y2 - y1
                if abs(dx) < 4 and abs(dy) < 20:
                    continue
                slope = round(float(dy) / float(dx if dx else 1), 3)
                lanes.append(
                    {
                        "x1": int(x1),
                        "y1": int(y1),
                        "x2": int(x2),
                        "y2": int(y2),
                        "slope": slope,
                    }
                )
        return {
            "enabled": True,
            "lane_count": len(lanes),
            "lanes": lanes,
        }

    def draw_annotations(self, frame, detections, road):
        if cv2 is None:
            return frame
        for det in detections:
            bbox = det.get("bbox")
            if not bbox or len(bbox) != 4:
                continue
            x1, y1, x2, y2 = [int(v) for v in bbox]
            label = det.get("class_name", "object")
            conf = det.get("confidence", 0.0)
            cv2.rectangle(frame, (x1, y1), (x2, y2), (0, 255, 0), 2)
            cv2.putText(
                frame,
                f"{label} {conf:.2f}",
                (x1, max(0, y1 - 8)),
                cv2.FONT_HERSHEY_SIMPLEX,
                0.5,
                (0, 255, 0),
                1,
                cv2.LINE_AA,
            )
        if road.get("enabled"):
            for lane in road.get("lanes", []):
                cv2.line(
                    frame,
                    (lane["x1"], lane["y1"]),
                    (lane["x2"], lane["y2"]),
                    (255, 180, 0),
                    3,
                )
            cv2.putText(
                frame,
                f"road lanes: {road.get('lane_count', 0)}",
                (12, 24),
                cv2.FONT_HERSHEY_SIMPLEX,
                0.6,
                (255, 255, 0),
                2,
                cv2.LINE_AA,
            )
        return frame


def main(args=None):
    rclpy.init(args=args)
    node = VisionNode()
    try:
        rclpy.spin(node)
    finally:
        node.destroy_node()
        rclpy.shutdown()


if __name__ == "__main__":
    main()
