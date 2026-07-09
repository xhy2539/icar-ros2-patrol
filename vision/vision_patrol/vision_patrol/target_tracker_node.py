import json
import time

import rclpy
from geometry_msgs.msg import Twist
from rclpy.node import Node
from std_msgs.msg import String

try:
    from icar_interfaces.msg import DetectionArray
except ImportError:
    DetectionArray = None


class TargetTrackerNode(Node):
    """Select a visual target and publish safe follow-control velocity hints."""

    def __init__(self):
        super().__init__("target_tracker_node")
        self.declare_parameter("detections_topic", "/vision/detections")
        self.declare_parameter("json_detections_topic", "")
        self.declare_parameter("command_topic", "/vision/target_tracking/command")
        self.declare_parameter("cmd_vel_topic", "/vision/target_cmd_vel")
        self.declare_parameter("status_topic", "/vision/target_tracking/status")
        self.declare_parameter("target_classes", ["person"])
        self.declare_parameter("fallback_classes", ["sign", "obstacle"])
        self.declare_parameter("enabled_on_start", False)
        self.declare_parameter("min_confidence", 0.45)
        self.declare_parameter("desired_bbox_area_ratio", 0.12)
        self.declare_parameter("deadband_x", 0.08)
        self.declare_parameter("deadband_area", 0.035)
        self.declare_parameter("linear_gain", 0.45)
        self.declare_parameter("angular_gain", 0.9)
        self.declare_parameter("max_linear_speed", 0.18)
        self.declare_parameter("max_angular_speed", 0.6)
        self.declare_parameter("lost_timeout_sec", 0.8)
        self.declare_parameter("publish_stop_on_lost", True)
        self.declare_parameter("allow_fallback", True)
        self.declare_parameter("frame_width", 640)
        self.declare_parameter("frame_height", 480)

        self.detections_topic = self.get_parameter("detections_topic").value
        self.json_detections_topic = self.get_parameter("json_detections_topic").value
        self.command_topic = self.get_parameter("command_topic").value
        self.cmd_vel_topic = self.get_parameter("cmd_vel_topic").value
        self.status_topic = self.get_parameter("status_topic").value
        self.target_classes = list(self.get_parameter("target_classes").value)
        self.fallback_classes = list(self.get_parameter("fallback_classes").value)
        self.enabled = bool(self.get_parameter("enabled_on_start").value)
        self.min_confidence = float(self.get_parameter("min_confidence").value)
        self.desired_bbox_area_ratio = float(
            self.get_parameter("desired_bbox_area_ratio").value
        )
        self.deadband_x = float(self.get_parameter("deadband_x").value)
        self.deadband_area = float(self.get_parameter("deadband_area").value)
        self.linear_gain = float(self.get_parameter("linear_gain").value)
        self.angular_gain = float(self.get_parameter("angular_gain").value)
        self.max_linear_speed = float(self.get_parameter("max_linear_speed").value)
        self.max_angular_speed = float(self.get_parameter("max_angular_speed").value)
        self.lost_timeout_sec = float(self.get_parameter("lost_timeout_sec").value)
        self.publish_stop_on_lost = bool(self.get_parameter("publish_stop_on_lost").value)
        self.allow_fallback = bool(self.get_parameter("allow_fallback").value)
        self.frame_width = int(self.get_parameter("frame_width").value)
        self.frame_height = int(self.get_parameter("frame_height").value)

        self.last_seen_at = 0.0
        self.last_frame_size = None
        self.last_target = None

        self.cmd_pub = self.create_publisher(Twist, self.cmd_vel_topic, 10)
        self.status_pub = self.create_publisher(String, self.status_topic, 10)
        if DetectionArray is not None:
            self.detections_sub = self.create_subscription(
                DetectionArray,
                self.detections_topic,
                self.on_detection_array,
                10,
            )
        else:
            self.detections_sub = self.create_subscription(
                String,
                self.detections_topic,
                self.on_detections_json,
                10,
            )
        self.json_detections_sub = None
        if self.json_detections_topic:
            self.json_detections_sub = self.create_subscription(
                String,
                self.json_detections_topic,
                self.on_detections_json,
                10,
            )
        self.command_sub = self.create_subscription(
            String,
            self.command_topic,
            self.on_command,
            10,
        )
        self.timer = self.create_timer(0.2, self.check_lost_target)

        self.get_logger().info(
            f"Target tracker listening on {self.detections_topic}; "
            f"publishing cmd hints to {self.cmd_vel_topic}; "
            f"commands={self.command_topic}; enabled={self.enabled}; "
            f"target_classes={self.target_classes}"
        )
        self.publish_status("ready", {"message": "waiting for tracking command"})

    def on_command(self, msg):
        try:
            command = json.loads(msg.data)
        except json.JSONDecodeError:
            command = {"action": msg.data.strip()}

        action = str(command.get("action", "")).lower()
        if action in ("start", "select_target", "set_target"):
            classes = self.parse_classes(command)
            if classes:
                self.target_classes = classes
            self.allow_fallback = bool(command.get("allow_fallback", self.allow_fallback))
            fallback = command.get("fallback_classes")
            if fallback is not None:
                self.fallback_classes = self.normalize_class_list(fallback)
            self.enabled = True
            self.last_seen_at = 0.0
            self.publish_status(
                "tracking_started",
                {
                    "target_classes": self.target_classes,
                    "allow_fallback": self.allow_fallback,
                    "fallback_classes": self.fallback_classes,
                },
            )
        elif action in ("stop", "pause", "cancel"):
            self.enabled = False
            self.last_seen_at = 0.0
            self.cmd_pub.publish(Twist())
            self.publish_status("tracking_stopped", {})
        elif action == "set_params":
            self.update_params_from_command(command)
            self.publish_status("params_updated", self.current_params())
        elif action == "status":
            self.publish_status("status", self.current_params())
        else:
            self.publish_status(
                "unknown_command",
                {
                    "raw": msg.data,
                    "supported": ["start", "select_target", "stop", "set_params", "status"],
                },
            )

    def on_detection_array(self, msg):
        detections = []
        for det in msg.detections:
            detections.append(
                {
                    "class_name": det.class_name,
                    "confidence": det.confidence,
                    "bbox": [det.x_min, det.y_min, det.x_max, det.y_max],
                    "image_path": det.image_path,
                }
            )
        payload = {
            "frame": {"width": self.frame_width, "height": self.frame_height},
            "detections": detections,
        }
        self.handle_detection_payload(payload)

    def on_detections_json(self, msg):
        if not self.enabled:
            return
        try:
            payload = json.loads(msg.data)
        except json.JSONDecodeError as exc:
            self.publish_status("bad_json", {"error": str(exc)})
            return
        self.handle_detection_payload(payload)

    def handle_detection_payload(self, payload):
        if not self.enabled:
            return
        frame = payload.get("frame", {})
        width = int(frame.get("width", 0) or 0)
        height = int(frame.get("height", 0) or 0)
        detections = payload.get("detections", [])
        if width <= 0 or height <= 0:
            self.publish_status("missing_frame_size", {})
            return

        target = self.select_target(detections, width, height)
        if target is None:
            self.publish_status("no_target", {"detections": len(detections)})
            return

        cmd, control = self.compute_command(target, width, height)
        self.cmd_pub.publish(cmd)
        self.last_seen_at = time.monotonic()
        self.last_frame_size = (width, height)
        self.last_target = target
        self.publish_status(
            "tracking",
            {
                "target": target,
                "control": control,
                "cmd_vel_topic": self.cmd_vel_topic,
            },
        )

    def select_target(self, detections, width, height):
        candidates = []
        fallback = []
        for det in detections:
            class_name = str(det.get("class_name", ""))
            confidence = float(det.get("confidence", 0.0) or 0.0)
            bbox = det.get("bbox", [])
            if confidence < self.min_confidence or len(bbox) != 4:
                continue
            score = self.score_detection(det, width, height)
            item = dict(det)
            item["score"] = score
            if class_name in self.target_classes:
                candidates.append(item)
            elif self.allow_fallback and class_name in self.fallback_classes:
                fallback.append(item)
        pool = candidates if candidates else fallback
        if not pool:
            return None
        return max(pool, key=lambda det: det["score"])

    def score_detection(self, det, width, height):
        x1, y1, x2, y2 = [float(v) for v in det["bbox"]]
        bbox_area = max(0.0, x2 - x1) * max(0.0, y2 - y1)
        frame_area = float(width * height)
        area_ratio = bbox_area / frame_area if frame_area else 0.0
        center_x = (x1 + x2) / 2.0 / float(width)
        center_error = abs(center_x - 0.5)
        confidence = float(det.get("confidence", 0.0) or 0.0)
        return confidence + min(area_ratio, 0.35) - center_error * 0.4

    def compute_command(self, target, width, height):
        x1, y1, x2, y2 = [float(v) for v in target["bbox"]]
        bbox_area = max(0.0, x2 - x1) * max(0.0, y2 - y1)
        frame_area = float(width * height)
        area_ratio = bbox_area / frame_area if frame_area else 0.0
        center_x = (x1 + x2) / 2.0 / float(width)
        x_error = center_x - 0.5

        angular_z = 0.0
        if abs(x_error) > self.deadband_x:
            angular_z = -self.angular_gain * x_error

        area_error = self.desired_bbox_area_ratio - area_ratio
        linear_x = 0.0
        if abs(area_error) > self.deadband_area:
            linear_x = self.linear_gain * area_error

        cmd = Twist()
        cmd.linear.x = self.clamp(linear_x, -self.max_linear_speed, self.max_linear_speed)
        cmd.angular.z = self.clamp(
            angular_z, -self.max_angular_speed, self.max_angular_speed
        )
        control = {
            "center_x": round(center_x, 3),
            "x_error": round(x_error, 3),
            "area_ratio": round(area_ratio, 4),
            "desired_area_ratio": self.desired_bbox_area_ratio,
            "linear_x": round(cmd.linear.x, 3),
            "angular_z": round(cmd.angular.z, 3),
        }
        return cmd, control

    def check_lost_target(self):
        if not self.enabled:
            return
        if self.last_seen_at <= 0:
            return
        elapsed = time.monotonic() - self.last_seen_at
        if elapsed <= self.lost_timeout_sec:
            return
        self.last_seen_at = 0.0
        if self.publish_stop_on_lost:
            self.cmd_pub.publish(Twist())
        self.publish_status("target_lost", {"lost_timeout_sec": self.lost_timeout_sec})

    def publish_status(self, event, data):
        payload = {
            "module": "vision",
            "event": event,
            "enabled": self.enabled,
            "target_classes": self.target_classes,
            "fallback_classes": self.fallback_classes if self.allow_fallback else [],
            "data": data,
        }
        self.status_pub.publish(String(data=json.dumps(payload, ensure_ascii=False)))

    def parse_classes(self, command):
        if "target_classes" in command:
            return self.normalize_class_list(command["target_classes"])
        if "class_name" in command:
            return self.normalize_class_list(command["class_name"])
        if "target_class" in command:
            return self.normalize_class_list(command["target_class"])
        return []

    @staticmethod
    def normalize_class_list(value):
        if isinstance(value, str):
            if "," in value:
                return [item.strip() for item in value.split(",") if item.strip()]
            return [value.strip()] if value.strip() else []
        if isinstance(value, (list, tuple)):
            return [str(item).strip() for item in value if str(item).strip()]
        return []

    def update_params_from_command(self, command):
        numeric_fields = [
            "min_confidence",
            "desired_bbox_area_ratio",
            "deadband_x",
            "deadband_area",
            "linear_gain",
            "angular_gain",
            "max_linear_speed",
            "max_angular_speed",
            "lost_timeout_sec",
        ]
        for field in numeric_fields:
            if field in command:
                setattr(self, field, float(command[field]))
        if "allow_fallback" in command:
            self.allow_fallback = bool(command["allow_fallback"])
        if "publish_stop_on_lost" in command:
            self.publish_stop_on_lost = bool(command["publish_stop_on_lost"])

    def current_params(self):
        return {
            "target_classes": self.target_classes,
            "fallback_classes": self.fallback_classes,
            "allow_fallback": self.allow_fallback,
            "min_confidence": self.min_confidence,
            "desired_bbox_area_ratio": self.desired_bbox_area_ratio,
            "max_linear_speed": self.max_linear_speed,
            "max_angular_speed": self.max_angular_speed,
            "cmd_vel_topic": self.cmd_vel_topic,
        }

    @staticmethod
    def clamp(value, min_value, max_value):
        return max(min_value, min(max_value, value))


def main(args=None):
    rclpy.init(args=args)
    node = TargetTrackerNode()
    try:
        rclpy.spin(node)
    finally:
        node.destroy_node()
        rclpy.shutdown()


if __name__ == "__main__":
    main()
