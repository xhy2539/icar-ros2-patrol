import json
import time

import rclpy
from rclpy.node import Node
from rclpy.qos import DurabilityPolicy, HistoryPolicy, QoSProfile, ReliabilityPolicy
from sensor_msgs.msg import Image
from std_msgs.msg import String

from .fall_detection_logic import classify_person_fall

try:
    from icar_interfaces.msg import Detection, DetectionArray
except ImportError:
    Detection = None
    DetectionArray = None

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

try:
    from ultralytics import YOLO
except ImportError:
    YOLO = None


DEFAULT_OBSTACLE_CLASSES = [
    "backpack",
    "handbag",
    "suitcase",
    "bottle",
    "cup",
    "chair",
    "couch",
    "bed",
    "dining table",
    "bench",
    "potted plant",
    "traffic cone",
    "cone",
    "box",
    "cart",
    "wheelchair",
    "stroller",
]

DEFAULT_WATER_CLASSES = [
    "water puddle",
    "puddle",
    "standing water",
    "wet floor",
    "water on floor",
]


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
        self.declare_parameter("detections_json_topic", "/vision/detections_json")
        self.declare_parameter("annotated_topic", "/vision/annotated_image")
        self.declare_parameter("mode", "detect")
        self.declare_parameter("detector_backend", "auto")
        self.declare_parameter("publish_json_debug", True)
        self.declare_parameter("publish_annotated", False)
        self.declare_parameter("inference_frame_stride", 1)
        self.declare_parameter("enable_road_detection", False)
        self.declare_parameter("min_color_area", 600.0)
        self.declare_parameter("yolo_model", "")
        self.declare_parameter("yolo_device", "")
        self.declare_parameter("yolo_confidence", 0.35)
        self.declare_parameter("yolo_iou", 0.5)
        self.declare_parameter("yolo_imgsz", 640)
        self.declare_parameter("target_classes", [""])
        self.declare_parameter("obstacle_alias_enabled", True)
        self.declare_parameter("obstacle_classes", DEFAULT_OBSTACLE_CLASSES)
        self.declare_parameter("obstacle_min_area_ratio", 0.003)
        self.declare_parameter("water_detector_backend", "auto")
        self.declare_parameter("water_model", "")
        self.declare_parameter("water_classes", DEFAULT_WATER_CLASSES)
        self.declare_parameter("water_confidence", 0.15)
        self.declare_parameter("water_iou", 0.5)
        self.declare_parameter("water_imgsz", 640)
        self.declare_parameter("water_device", "")
        self.declare_parameter("water_min_area_ratio", 0.002)
        self.declare_parameter("water_class_name", "water")
        self.declare_parameter("fall_detection_enabled", True)
        self.declare_parameter("fall_aspect_ratio", 1.15)
        self.declare_parameter("fall_min_area_ratio", 0.012)
        self.declare_parameter("fall_keypoint_confidence", 0.25)
        self.declare_parameter("fall_torso_horizontal_ratio", 0.9)

        self.image_topic = self.get_parameter("image_topic").value
        self.detections_topic = self.get_parameter("detections_topic").value
        self.detections_json_topic = self.get_parameter("detections_json_topic").value
        self.annotated_topic = self.get_parameter("annotated_topic").value
        self.mode = self.get_parameter("mode").value
        self.detector_backend = str(self.get_parameter("detector_backend").value).lower()
        self.publish_json_debug = bool(self.get_parameter("publish_json_debug").value)
        self.publish_annotated = bool(self.get_parameter("publish_annotated").value)
        self.inference_frame_stride = max(
            1, int(self.get_parameter("inference_frame_stride").value)
        )
        self.enable_road_detection = bool(
            self.get_parameter("enable_road_detection").value
        )
        self.min_color_area = float(self.get_parameter("min_color_area").value)
        self.yolo_model_path = str(self.get_parameter("yolo_model").value).strip()
        self.yolo_device = str(self.get_parameter("yolo_device").value).strip()
        self.yolo_confidence = float(self.get_parameter("yolo_confidence").value)
        self.yolo_iou = float(self.get_parameter("yolo_iou").value)
        self.yolo_imgsz = int(self.get_parameter("yolo_imgsz").value)
        self.target_classes = self.normalize_class_list(
            self.get_parameter("target_classes").value
        )
        self.obstacle_alias_enabled = bool(
            self.get_parameter("obstacle_alias_enabled").value
        )
        self.obstacle_classes = self.normalize_class_list(
            self.get_parameter("obstacle_classes").value
        )
        self.obstacle_class_set = {
            self.class_key(class_name) for class_name in self.obstacle_classes
        }
        self.obstacle_min_area_ratio = float(
            self.get_parameter("obstacle_min_area_ratio").value
        )
        self.water_detector_backend = str(
            self.get_parameter("water_detector_backend").value
        ).lower()
        self.water_model_path = str(self.get_parameter("water_model").value).strip()
        self.water_classes = self.normalize_class_list(
            self.get_parameter("water_classes").value
        )
        self.water_confidence = float(self.get_parameter("water_confidence").value)
        self.water_iou = float(self.get_parameter("water_iou").value)
        self.water_imgsz = int(self.get_parameter("water_imgsz").value)
        self.water_device = str(self.get_parameter("water_device").value).strip()
        self.water_min_area_ratio = float(
            self.get_parameter("water_min_area_ratio").value
        )
        self.water_class_name = (
            str(self.get_parameter("water_class_name").value).strip() or "water"
        )
        self.fall_detection_enabled = bool(
            self.get_parameter("fall_detection_enabled").value
        )
        self.fall_aspect_ratio = float(
            self.get_parameter("fall_aspect_ratio").value
        )
        self.fall_min_area_ratio = float(
            self.get_parameter("fall_min_area_ratio").value
        )
        self.fall_keypoint_confidence = float(
            self.get_parameter("fall_keypoint_confidence").value
        )
        self.fall_torso_horizontal_ratio = float(
            self.get_parameter("fall_torso_horizontal_ratio").value
        )

        self.bridge = CvBridge() if CvBridge else None
        self.frame_count = 0
        self.started_at = time.monotonic()
        self.yolo_model = None
        self.water_model = None
        self.water_uses_world_prompts = False
        self.yolo_unavailable_logged = False
        self.typed_detections_available = Detection is not None and DetectionArray is not None

        detections_msg_type = DetectionArray if self.typed_detections_available else String
        self.detections_pub = self.create_publisher(
            detections_msg_type, self.detections_topic, 10
        )
        self.detections_json_pub = None
        if self.publish_json_debug and self.typed_detections_available:
            self.detections_json_pub = self.create_publisher(
                String, self.detections_json_topic, 10
            )
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
            f"Vision node mode={self.mode}, backend={self.detector_backend}, "
            f"image_topic={self.image_topic}, "
            f"detections_topic={self.detections_topic}, "
            f"inference_frame_stride={self.inference_frame_stride}"
        )
        if not self.typed_detections_available:
            self.get_logger().warning(
                "icar_interfaces is unavailable; publishing JSON String on "
                f"{self.detections_topic} as a fallback"
            )
        if self.bridge is None:
            self.get_logger().warning(
                "cv_bridge is unavailable; publishing metadata-only detections"
            )
        self.load_yolo_if_requested()
        self.load_water_model_if_requested()

    def load_yolo_if_requested(self):
        if self.detector_backend not in ("auto", "yolo"):
            return
        if not self.yolo_model_path:
            if self.detector_backend == "yolo":
                self.get_logger().warning(
                    "detector_backend=yolo but yolo_model is empty; "
                    "falling back to lightweight color detector"
                )
            return
        if YOLO is None:
            self.get_logger().warning(
                "ultralytics is not installed; falling back to lightweight color detector"
            )
            return
        try:
            self.yolo_model = YOLO(self.yolo_model_path)
            self.get_logger().info(
                f"Loaded YOLO model: {self.yolo_model_path}; "
                f"device={self.yolo_device or 'auto'}; "
                f"target_classes={self.target_classes or 'all'}; "
                f"obstacle_alias_enabled={self.obstacle_alias_enabled}"
            )
        except Exception as exc:  # pylint: disable=broad-except
            self.get_logger().warning(
                f"failed to load YOLO model '{self.yolo_model_path}': {exc}; "
                "falling back to lightweight color detector"
            )

    def load_water_model_if_requested(self):
        if self.water_detector_backend == "none":
            return
        if not self.water_model_path:
            return
        if YOLO is None:
            self.get_logger().warning(
                "ultralytics is not installed; water detector is disabled"
            )
            return
        try:
            self.water_model = YOLO(self.water_model_path)
            set_classes = getattr(self.water_model, "set_classes", None)
            if callable(set_classes) and self.water_classes:
                set_classes(self.water_classes)
                self.water_uses_world_prompts = True
            elif self.water_detector_backend == "world":
                self.get_logger().warning(
                    "water_detector_backend=world but this model does not support "
                    "set_classes; use a YOLO-World checkpoint or a custom water model"
                )
            self.get_logger().info(
                f"Loaded water detector: {self.water_model_path}; "
                f"backend={self.water_detector_backend}; "
                f"classes={self.water_classes or 'model default'}; "
                f"device={self.water_device or self.yolo_device or 'auto'}"
            )
        except Exception as exc:  # pylint: disable=broad-except
            self.water_model = None
            self.get_logger().warning(
                f"failed to load water model '{self.water_model_path}': {exc}; "
                "water detector is disabled"
            )

    def on_image(self, msg):
        self.frame_count += 1
        if (self.frame_count - 1) % self.inference_frame_stride != 0:
            return

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
            "detector": {
                "backend": self.active_backend(),
                "model": self.yolo_model_path if self.yolo_model is not None else "",
                "target_classes": self.target_classes,
                "water_model": (
                    self.water_model_path if self.water_model is not None else ""
                ),
                "water_classes": self.water_classes,
            },
            "detections": detections,
            "road": road,
        }
        self.publish_detections(msg, detections, payload)

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
        if self.yolo_model is not None:
            detections = self.run_yolo_detection(frame)
        else:
            if self.detector_backend == "yolo" and not self.yolo_unavailable_logged:
                self.yolo_unavailable_logged = True
                self.get_logger().warning(
                    "YOLO backend requested but no model is available; using color detector"
                )
            detections = self.run_color_detection(frame)

        if self.water_model is not None:
            detections.extend(self.run_water_detection(frame))
        return detections

    def run_color_detection(self, frame):
        # Lightweight simulation detector for no-model ROS2 chain checks.
        color_specs = [
            ("obstacle", (0, 90, 90), (10, 255, 255), "red"),
            ("obstacle", (170, 90, 90), (180, 255, 255), "red"),
            ("sign", (35, 70, 60), (90, 255, 255), "green"),
            ("person", (20, 80, 80), (34, 255, 255), "yellow"),
            ("water", (95, 70, 60), (130, 255, 255), "blue"),
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
                mapped_class = class_name
                fall_reason = ""
                if self.fall_detection_enabled and class_name == "person":
                    mapped_class, _, fall_reason = classify_person_fall(
                        class_name,
                        class_name,
                        [x, y, x + w, y + h],
                        frame.shape[1],
                        frame.shape[0],
                        aspect_ratio_threshold=self.fall_aspect_ratio,
                        min_area_ratio=self.fall_min_area_ratio,
                        keypoint_confidence=self.fall_keypoint_confidence,
                        torso_horizontal_ratio=self.fall_torso_horizontal_ratio,
                    )
                detections.append(
                    {
                        "class_name": mapped_class,
                        "confidence": round(min(0.99, 0.45 + area / 12000.0), 2),
                        "bbox": [int(x), int(y), int(x + w), int(y + h)],
                        "source": f"color_{color_name}",
                        "fall_reason": fall_reason,
                    }
                )
        return detections

    def publish_detections(self, image_msg, detections, payload):
        if self.typed_detections_available:
            typed_msg = DetectionArray()
            typed_msg.header = image_msg.header
            typed_msg.detections = [
                self.to_detection_msg(det) for det in detections
            ]
            self.detections_pub.publish(typed_msg)

            if self.detections_json_pub is not None:
                self.detections_json_pub.publish(
                    String(data=json.dumps(payload, ensure_ascii=False))
                )
            return

        self.detections_pub.publish(String(data=json.dumps(payload, ensure_ascii=False)))

    @staticmethod
    def to_detection_msg(det):
        msg = Detection()
        bbox = det.get("bbox") or [0, 0, 0, 0]
        x1, y1, x2, y2 = [int(v) for v in bbox[:4]]
        msg.class_name = str(det.get("class_name", "unknown"))
        msg.confidence = float(det.get("confidence", 0.0) or 0.0)
        msg.x_min = x1
        msg.y_min = y1
        msg.x_max = x2
        msg.y_max = y2
        msg.image_path = str(det.get("image_path", ""))
        return msg

    def run_yolo_detection(self, frame):
        kwargs = {
            "imgsz": self.yolo_imgsz,
            "conf": self.yolo_confidence,
            "iou": self.yolo_iou,
            "verbose": False,
        }
        if self.yolo_device:
            kwargs["device"] = self.yolo_device
        try:
            results = self.yolo_model.predict(frame, **kwargs)
        except Exception as exc:  # pylint: disable=broad-except
            self.get_logger().warning(f"YOLO inference failed: {exc}")
            return []
        if not results:
            return []

        result = results[0]
        names = getattr(result, "names", {}) or {}
        boxes = getattr(result, "boxes", None)
        if boxes is None:
            return []

        detections = []
        track_ids = getattr(boxes, "id", None)
        pose_keypoints = getattr(getattr(result, "keypoints", None), "data", None)
        height, width = frame.shape[:2]
        for index, box in enumerate(boxes):
            cls_id = int(box.cls[0].item())
            confidence = float(box.conf[0].item())
            x1, y1, x2, y2 = [int(round(v)) for v in box.xyxy[0].tolist()]
            raw_class_name = str(names.get(cls_id, cls_id))
            class_name, is_obstacle = self.map_yolo_class(
                raw_class_name,
                [x1, y1, x2, y2],
                width,
                height,
            )
            if class_name is None:
                continue
            fall_reason = ""
            is_fallen = False
            keypoints = None
            if pose_keypoints is not None and index < len(pose_keypoints):
                try:
                    keypoints = pose_keypoints[index].tolist()
                except (AttributeError, TypeError):
                    keypoints = None
            if self.fall_detection_enabled:
                class_name, is_fallen, fall_reason = classify_person_fall(
                    raw_class_name,
                    class_name,
                    [x1, y1, x2, y2],
                    width,
                    height,
                    keypoints=keypoints,
                    aspect_ratio_threshold=self.fall_aspect_ratio,
                    min_area_ratio=self.fall_min_area_ratio,
                    keypoint_confidence=self.fall_keypoint_confidence,
                    torso_horizontal_ratio=self.fall_torso_horizontal_ratio,
                )
            if not self.keep_detection_class(raw_class_name, class_name):
                continue
            det = {
                "class_name": class_name,
                "confidence": round(confidence, 3),
                "bbox": [x1, y1, x2, y2],
                "source": (
                    "yolo_fall"
                    if is_fallen
                    else ("yolo_obstacle" if is_obstacle else "yolo")
                ),
                "model": self.yolo_model_path,
                "raw_class_name": raw_class_name,
                "fall_reason": fall_reason,
            }
            if track_ids is not None and index < len(track_ids):
                det["track_id"] = int(track_ids[index].item())
            detections.append(det)
        return detections

    def run_water_detection(self, frame):
        kwargs = {
            "imgsz": self.water_imgsz,
            "conf": self.water_confidence,
            "iou": self.water_iou,
            "verbose": False,
        }
        device = self.water_device or self.yolo_device
        if device:
            kwargs["device"] = device
        try:
            results = self.water_model.predict(frame, **kwargs)
        except Exception as exc:  # pylint: disable=broad-except
            self.get_logger().warning(f"water detector inference failed: {exc}")
            return []
        if not results:
            return []

        result = results[0]
        names = getattr(result, "names", {}) or {}
        boxes = getattr(result, "boxes", None)
        if boxes is None:
            return []

        height, width = frame.shape[:2]
        frame_area = float(max(1, width * height))
        detections = []
        for box in boxes:
            cls_id = int(box.cls[0].item())
            confidence = float(box.conf[0].item())
            x1, y1, x2, y2 = [int(round(v)) for v in box.xyxy[0].tolist()]
            bbox_area = max(0.0, float(x2 - x1)) * max(0.0, float(y2 - y1))
            if (
                self.water_min_area_ratio > 0
                and bbox_area / frame_area < self.water_min_area_ratio
            ):
                continue
            raw_class_name = str(names.get(cls_id, cls_id))
            if not self.keep_detection_class(raw_class_name, self.water_class_name):
                continue
            detections.append(
                {
                    "class_name": self.water_class_name,
                    "confidence": round(confidence, 3),
                    "bbox": [x1, y1, x2, y2],
                    "source": (
                        "yolo_world_water"
                        if self.water_uses_world_prompts
                        else "yolo_water"
                    ),
                    "model": self.water_model_path,
                    "raw_class_name": raw_class_name,
                }
            )
        return detections

    def map_yolo_class(self, raw_class_name, bbox, width, height):
        """Map COCO/custom YOLO classes that block passage to project obstacle."""
        if not self.obstacle_alias_enabled:
            return raw_class_name, False
        if self.class_key(raw_class_name) not in self.obstacle_class_set:
            return raw_class_name, False

        if self.obstacle_min_area_ratio > 0:
            x1, y1, x2, y2 = [float(v) for v in bbox]
            bbox_area = max(0.0, x2 - x1) * max(0.0, y2 - y1)
            frame_area = float(max(1, width * height))
            if bbox_area / frame_area < self.obstacle_min_area_ratio:
                return None, False

        return "obstacle", True

    def keep_detection_class(self, raw_class_name, class_name):
        if not self.target_classes:
            return True
        target_keys = {self.class_key(item) for item in self.target_classes}
        return (
            self.class_key(class_name) in target_keys
            or self.class_key(raw_class_name) in target_keys
        )

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
            raw_label = det.get("raw_class_name", "")
            if raw_label and raw_label != label:
                label = f"{label}:{raw_label}"
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

    def active_backend(self):
        suffix = ""
        if self.water_model is not None:
            suffix = f"+water_{self.water_detector_backend}"
        if self.yolo_model is not None:
            return f"yolo{suffix}"
        return f"color{suffix}"

    @staticmethod
    def normalize_class_list(value):
        if isinstance(value, str):
            if not value.strip():
                return []
            return [item.strip() for item in value.split(",") if item.strip()]
        if isinstance(value, (list, tuple)):
            return [str(item).strip() for item in value if str(item).strip()]
        return []

    @staticmethod
    def class_key(value):
        return str(value).strip().lower()


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
