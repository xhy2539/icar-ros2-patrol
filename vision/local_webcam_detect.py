import argparse
import glob
import json
import time
from pathlib import Path

import cv2
import numpy as np

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

DEFAULT_FALL_HAZARD_CLASSES = [
    "stairs",
    "staircase",
    "stairway",
    "steps",
    "stair step",
    "downstairs",
    "upstairs",
    "curb",
    "kerb",
    "door threshold",
    "door sill",
    "raised threshold",
    "threshold",
    "transition strip",
    "ledge",
    "floor lip",
    "drop-off",
    "uneven floor",
    "floor height difference",
    "single step",
    "small step",
    "ramp",
    "slope",
]


def parse_list(value):
    if not value:
        return []
    if isinstance(value, (list, tuple)):
        return [str(item).strip() for item in value if str(item).strip()]
    return [item.strip() for item in str(value).split(",") if item.strip()]


def class_key(value):
    return str(value).strip().lower()


def color_for_class(class_name):
    colors = {
        "obstacle": (0, 80, 255),
        "water": (255, 120, 0),
        "fall_hazard": (180, 0, 255),
        "person": (0, 220, 255),
        "sign": (0, 200, 0),
    }
    return colors.get(class_name, (80, 220, 80))


class LocalWebcamDetector:
    def __init__(self, args):
        self.args = args
        self.model = None
        self.water_model = None
        self.fall_hazard_model = None
        self.water_uses_world_prompts = False
        self.fall_hazard_uses_world_prompts = False
        self.obstacle_classes = {class_key(item) for item in args.obstacle_classes}
        self.water_classes = [item for item in args.water_classes if item]
        self.fall_hazard_classes = [item for item in args.fall_hazard_classes if item]
        self.target_classes = {class_key(item) for item in args.target_classes}
        self.save_dir = Path(args.save_dir)
        self.save_dir.mkdir(parents=True, exist_ok=True)
        self.frame_index = 0
        self.last_print_at = 0.0
        self.last_fall_hazard_detections = []
        self.last_fall_hazard_frame = 0
        self.load_model()

    def load_model(self):
        if self.args.backend == "color":
            self.load_water_model()
            self.load_fall_hazard_model()
            return
        if self.args.model:
            if YOLO is None:
                if self.args.backend == "yolo":
                    raise RuntimeError("ultralytics is not installed")
            else:
                self.model = YOLO(self.args.model)
        elif self.args.backend == "yolo":
            raise RuntimeError("--backend yolo requires --model, for example yolo11n.pt")

        self.load_water_model()
        self.load_fall_hazard_model()

    def load_water_model(self):
        if self.args.water_backend == "none":
            return
        if not self.args.water_model:
            return
        if YOLO is None:
            raise RuntimeError("ultralytics is required for --water-model")
        self.water_model = YOLO(self.args.water_model)
        set_classes = getattr(self.water_model, "set_classes", None)
        if callable(set_classes) and self.water_classes:
            set_classes(self.water_classes)
            self.water_uses_world_prompts = True
        elif self.args.water_backend == "world":
            print(
                "warning: --water-backend world was requested, but this model "
                "does not support set_classes"
            )

    def load_fall_hazard_model(self):
        if self.args.fall_hazard_backend == "none":
            return
        if not self.args.fall_hazard_model:
            return
        if YOLO is None:
            raise RuntimeError("ultralytics is required for --fall-hazard-model")
        self.fall_hazard_model = YOLO(self.args.fall_hazard_model)
        set_classes = getattr(self.fall_hazard_model, "set_classes", None)
        if callable(set_classes) and self.fall_hazard_classes:
            set_classes(self.fall_hazard_classes)
            self.fall_hazard_uses_world_prompts = True
        elif self.args.fall_hazard_backend == "world":
            print(
                "warning: --fall-hazard-backend world was requested, but this model "
                "does not support set_classes"
            )

    def detect(self, frame):
        detections = []
        if self.model is not None:
            detections.extend(self.detect_yolo(frame))
        else:
            detections.extend(self.detect_color(frame))
        if self.water_model is not None:
            detections.extend(self.detect_water(frame))
        if self.fall_hazard_model is not None:
            should_run = (
                self.last_fall_hazard_frame == 0
                or self.frame_index - self.last_fall_hazard_frame
                >= self.args.fall_hazard_frame_stride
            )
            if should_run:
                self.last_fall_hazard_detections = self.detect_fall_hazards(frame)
                self.last_fall_hazard_frame = self.frame_index
            detections.extend(self.last_fall_hazard_detections)
        return detections

    def detect_yolo(self, frame):
        results = self.model.predict(
            frame,
            imgsz=self.args.imgsz,
            conf=self.args.conf,
            iou=self.args.iou,
            device=self.args.device or None,
            verbose=False,
        )
        if not results:
            return []

        result = results[0]
        names = getattr(result, "names", {}) or {}
        boxes = getattr(result, "boxes", None)
        if boxes is None:
            return []

        height, width = frame.shape[:2]
        detections = []
        masks = getattr(result, "masks", None)
        mask_polygons = getattr(masks, "xy", None) if masks is not None else None
        for index, box in enumerate(boxes):
            cls_id = int(box.cls[0].item())
            raw_class = str(names.get(cls_id, cls_id))
            confidence = float(box.conf[0].item())
            x1, y1, x2, y2 = [int(round(v)) for v in box.xyxy[0].tolist()]
            mapped_class, source = self.map_yolo_class(raw_class, (x1, y1, x2, y2), width, height)
            if mapped_class is None:
                continue
            if self.target_classes and class_key(mapped_class) not in self.target_classes and class_key(raw_class) not in self.target_classes:
                continue
            detections.append(
                {
                    "class_name": mapped_class,
                    "raw_class_name": raw_class,
                    "confidence": round(confidence, 3),
                    "bbox": [x1, y1, x2, y2],
                    "source": source,
                }
            )
        return detections

    def map_yolo_class(self, raw_class, bbox, width, height):
        if class_key(raw_class) not in self.obstacle_classes:
            return raw_class, "yolo"

        x1, y1, x2, y2 = [float(v) for v in bbox]
        bbox_area = max(0.0, x2 - x1) * max(0.0, y2 - y1)
        frame_area = float(max(1, width * height))
        if bbox_area / frame_area < self.args.obstacle_min_area_ratio:
            return None, "yolo_obstacle_too_small"
        return "obstacle", "yolo_obstacle"

    def detect_water(self, frame):
        results = self.water_model.predict(
            frame,
            imgsz=self.args.water_imgsz,
            conf=self.args.water_conf,
            iou=self.args.water_iou,
            device=self.args.water_device or self.args.device or None,
            verbose=False,
        )
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
        masks = getattr(result, "masks", None)
        mask_polygons = getattr(masks, "xy", None) if masks is not None else None
        for index, box in enumerate(boxes):
            cls_id = int(box.cls[0].item())
            raw_class = str(names.get(cls_id, cls_id))
            confidence = float(box.conf[0].item())
            x1, y1, x2, y2 = [int(round(v)) for v in box.xyxy[0].tolist()]
            bbox_area = max(0.0, float(x2 - x1)) * max(0.0, float(y2 - y1))
            if (
                self.args.water_min_area_ratio > 0
                and bbox_area / frame_area < self.args.water_min_area_ratio
            ):
                continue
            water_class = self.args.water_class_name
            if (
                self.target_classes
                and class_key(water_class) not in self.target_classes
                and class_key(raw_class) not in self.target_classes
            ):
                continue
            detection = {
                    "class_name": water_class,
                    "raw_class_name": raw_class,
                    "confidence": round(confidence, 3),
                    "bbox": [x1, y1, x2, y2],
                    "source": (
                        "yolo_world_water"
                        if self.water_uses_world_prompts
                        else "yolo_water"
                    ),
                }
            polygon = self.mask_polygon(mask_polygons, index, width, height)
            if polygon:
                contour = np.asarray(polygon, dtype=np.float32)
                detection["polygon"] = polygon
                detection["mask_area_ratio"] = round(
                    float(cv2.contourArea(contour)) / frame_area, 6
                )
            detections.append(detection)
        return detections

    @staticmethod
    def mask_polygon(mask_polygons, index, width, height, max_points=100):
        if mask_polygons is None or index >= len(mask_polygons):
            return []
        points = np.asarray(mask_polygons[index], dtype=np.float32)
        if len(points) < 3:
            return []
        epsilon = max(1.0, 0.002 * cv2.arcLength(points, True))
        points = cv2.approxPolyDP(points, epsilon, True).reshape(-1, 2)
        if len(points) > max_points:
            step = int(np.ceil(len(points) / max_points))
            points = points[::step]
        return [
            [
                int(np.clip(round(x), 0, max(0, width - 1))),
                int(np.clip(round(y), 0, max(0, height - 1))),
            ]
            for x, y in points
        ]

    def detect_fall_hazards(self, frame):
        results = self.fall_hazard_model.predict(
            frame,
            imgsz=self.args.fall_hazard_imgsz,
            conf=self.args.fall_hazard_conf,
            iou=self.args.fall_hazard_iou,
            device=self.args.fall_hazard_device or self.args.device or None,
            verbose=False,
        )
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
            raw_class = str(names.get(cls_id, cls_id))
            confidence = float(box.conf[0].item())
            x1, y1, x2, y2 = [int(round(v)) for v in box.xyxy[0].tolist()]
            bbox_area = max(0.0, float(x2 - x1)) * max(0.0, float(y2 - y1))
            if (
                self.args.fall_hazard_min_area_ratio > 0
                and bbox_area / frame_area < self.args.fall_hazard_min_area_ratio
            ):
                continue
            hazard_class = self.args.fall_hazard_class_name
            if (
                self.target_classes
                and class_key(hazard_class) not in self.target_classes
                and class_key(raw_class) not in self.target_classes
            ):
                continue
            detections.append(
                {
                    "class_name": hazard_class,
                    "raw_class_name": raw_class,
                    "confidence": round(confidence, 3),
                    "bbox": [x1, y1, x2, y2],
                    "source": (
                        "yolo_world_fall_hazard"
                        if self.fall_hazard_uses_world_prompts
                        else "yolo_fall_hazard"
                    ),
                }
            )
        return detections

    def detect_color(self, frame):
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
            contours, _ = cv2.findContours(mask, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
            for contour in contours:
                area = cv2.contourArea(contour)
                if area < self.args.min_color_area:
                    continue
                x, y, w, h = cv2.boundingRect(contour)
                detections.append(
                    {
                        "class_name": class_name,
                        "raw_class_name": color_name,
                        "confidence": round(min(0.99, 0.45 + area / 12000.0), 2),
                        "bbox": [int(x), int(y), int(x + w), int(y + h)],
                        "source": f"color_{color_name}",
                    }
                )
        return detections

    def draw(self, frame, detections):
        for det in detections:
            x1, y1, x2, y2 = [int(v) for v in det["bbox"]]
            class_name = det["class_name"]
            raw_class = det.get("raw_class_name", "")
            label = class_name
            if raw_class and raw_class != class_name:
                label = f"{class_name}:{raw_class}"
            label = f"{label} {det['confidence']:.2f}"
            color = color_for_class(class_name)
            polygon = det.get("polygon") or []
            if len(polygon) >= 3:
                contour = np.asarray(polygon, dtype=np.int32).reshape((-1, 1, 2))
                overlay = frame.copy()
                cv2.fillPoly(overlay, [contour], color)
                cv2.addWeighted(overlay, 0.2, frame, 0.8, 0, frame)
                cv2.polylines(frame, [contour], True, color, 2)
            cv2.rectangle(frame, (x1, y1), (x2, y2), color, 2)
            cv2.putText(frame, label, (x1, max(18, y1 - 8)), cv2.FONT_HERSHEY_SIMPLEX, 0.55, color, 2, cv2.LINE_AA)
        cv2.putText(
            frame,
            "q: quit  s: save",
            (12, 24),
            cv2.FONT_HERSHEY_SIMPLEX,
            0.65,
            (240, 240, 240),
            2,
            cv2.LINE_AA,
        )
        return frame

    def print_status(self, detections):
        now = time.monotonic()
        if now - self.last_print_at < self.args.print_every:
            return
        self.last_print_at = now
        payload = {
            "frame": self.frame_index,
            "backend": self.active_backend(),
            "detections": detections,
        }
        print(json.dumps(payload, ensure_ascii=False))

    def save_frame(self, frame, detections):
        stamp = time.strftime("%Y%m%d_%H%M%S")
        image_path = self.save_dir / f"local_detect_{stamp}_{self.frame_index:06d}.jpg"
        json_path = image_path.with_suffix(".json")
        cv2.imwrite(str(image_path), frame)
        json_path.write_text(json.dumps(detections, ensure_ascii=False, indent=2), encoding="utf-8")
        print(f"saved {image_path}")

    def active_backend(self):
        backend = "yolo" if self.model is not None else "color"
        if self.water_model is not None:
            backend = f"{backend}+water_{self.args.water_backend}"
        if self.fall_hazard_model is not None:
            backend = f"{backend}+fall_hazard_{self.args.fall_hazard_backend}"
        return backend


def open_camera(camera_index, width, height):
    backends = [cv2.CAP_DSHOW, cv2.CAP_MSMF, cv2.CAP_ANY]
    for backend in backends:
        cap = cv2.VideoCapture(camera_index, backend)
        if not cap.isOpened():
            cap.release()
            continue
        cap.set(cv2.CAP_PROP_FRAME_WIDTH, width)
        cap.set(cv2.CAP_PROP_FRAME_HEIGHT, height)
        ok, frame = cap.read()
        if ok and frame is not None:
            return cap
        cap.release()
    raise RuntimeError(f"Cannot open camera index {camera_index}")


def collect_image_paths(image_args, image_globs):
    paths = []
    for item in image_args:
        paths.append(Path(item))
    for pattern in image_globs:
        paths.extend(Path(match) for match in glob.glob(pattern))
    unique_paths = []
    seen = set()
    for path in paths:
        resolved = str(path.resolve())
        if resolved in seen:
            continue
        seen.add(resolved)
        unique_paths.append(path)
    return unique_paths


def run_image_files(detector, image_paths, show_window, save_results):
    for image_path in image_paths:
        frame = cv2.imread(str(image_path))
        if frame is None:
            print(json.dumps({"image": str(image_path), "error": "failed_to_read"}))
            continue
        detector.frame_index += 1
        detections = detector.detect(frame)
        payload = {
            "image": str(image_path),
            "backend": detector.active_backend(),
            "width": int(frame.shape[1]),
            "height": int(frame.shape[0]),
            "detections": detections,
        }
        print(json.dumps(payload, ensure_ascii=False))

        drawn = detector.draw(frame.copy(), detections)
        if save_results:
            stem = image_path.stem
            out_image = detector.save_dir / f"{stem}_detected.jpg"
            out_json = detector.save_dir / f"{stem}_detections.json"
            cv2.imwrite(str(out_image), drawn)
            out_json.write_text(
                json.dumps(payload, ensure_ascii=False, indent=2),
                encoding="utf-8",
            )
        if show_window:
            cv2.imshow("ICAR local image detection", drawn)
            key = cv2.waitKey(0) & 0xFF
            if key == ord("q"):
                break
    if show_window:
        cv2.destroyAllWindows()


def build_arg_parser():
    parser = argparse.ArgumentParser(description="Local webcam detection test without ROS2")
    parser.add_argument("--camera", type=int, default=0, help="OpenCV camera index")
    parser.add_argument(
        "--image",
        action="append",
        default=[],
        help="Image file to detect. Can be provided multiple times.",
    )
    parser.add_argument(
        "--image-glob",
        action="append",
        default=[],
        help="Glob pattern for image files, for example samples\\*.jpg",
    )
    parser.add_argument("--backend", choices=["auto", "yolo", "color"], default="auto")
    parser.add_argument("--model", default="", help="YOLO model path/name, e.g. yolo11n.pt")
    parser.add_argument("--device", default="", help="YOLO device, e.g. 0 or cpu")
    parser.add_argument("--conf", type=float, default=0.35)
    parser.add_argument("--iou", type=float, default=0.5)
    parser.add_argument("--imgsz", type=int, default=640)
    parser.add_argument("--width", type=int, default=640)
    parser.add_argument("--height", type=int, default=480)
    parser.add_argument("--target-classes", default="", help="Comma list to keep; empty keeps all")
    parser.add_argument(
        "--obstacle-classes",
        default=",".join(DEFAULT_OBSTACLE_CLASSES),
        help="Comma list of YOLO classes to publish as obstacle",
    )
    parser.add_argument("--obstacle-min-area-ratio", type=float, default=0.003)
    parser.add_argument("--water-backend", choices=["none", "auto", "world", "yolo"], default="auto")
    parser.add_argument("--water-model", default="", help="YOLO-World/custom water model path")
    parser.add_argument(
        "--water-classes",
        default=",".join(DEFAULT_WATER_CLASSES),
        help="Comma list of YOLO-World text prompts for puddle/water detection",
    )
    parser.add_argument("--water-class-name", default="water")
    parser.add_argument("--water-conf", type=float, default=0.15)
    parser.add_argument("--water-iou", type=float, default=0.5)
    parser.add_argument("--water-imgsz", type=int, default=640)
    parser.add_argument("--water-device", default="")
    parser.add_argument("--water-min-area-ratio", type=float, default=0.002)
    parser.add_argument(
        "--fall-hazard-backend",
        choices=["none", "auto", "world", "yolo"],
        default="none",
    )
    parser.add_argument(
        "--fall-hazard-model",
        default="",
        help="YOLO-World/custom model for stairs, curbs, thresholds, ramps, and drop-offs",
    )
    parser.add_argument(
        "--fall-hazard-classes",
        default=",".join(DEFAULT_FALL_HAZARD_CLASSES),
        help="Comma list of YOLO-World text prompts for fall-risk height changes",
    )
    parser.add_argument("--fall-hazard-class-name", default="fall_hazard")
    parser.add_argument("--fall-hazard-conf", type=float, default=0.12)
    parser.add_argument("--fall-hazard-iou", type=float, default=0.5)
    parser.add_argument("--fall-hazard-imgsz", type=int, default=640)
    parser.add_argument("--fall-hazard-device", default="")
    parser.add_argument("--fall-hazard-min-area-ratio", type=float, default=0.003)
    parser.add_argument("--fall-hazard-frame-stride", type=int, default=5)
    parser.add_argument("--min-color-area", type=float, default=600.0)
    parser.add_argument("--save-dir", default="local_detection_samples")
    parser.add_argument(
        "--save-image-results",
        action="store_true",
        help="Save annotated image and JSON files when using --image/--image-glob",
    )
    parser.add_argument("--frames", type=int, default=0, help="Stop after N frames; 0 means live")
    parser.add_argument("--no-window", action="store_true", help="Do not open cv2.imshow window")
    parser.add_argument("--print-every", type=float, default=1.0)
    return parser


def main():
    args = build_arg_parser().parse_args()
    args.target_classes = parse_list(args.target_classes)
    args.obstacle_classes = parse_list(args.obstacle_classes)
    args.water_classes = parse_list(args.water_classes)
    args.water_class_name = args.water_class_name.strip() or "water"
    args.fall_hazard_classes = parse_list(args.fall_hazard_classes)
    args.fall_hazard_class_name = (
        args.fall_hazard_class_name.strip() or "fall_hazard"
    )
    args.fall_hazard_frame_stride = max(1, int(args.fall_hazard_frame_stride))

    detector = LocalWebcamDetector(args)
    image_paths = collect_image_paths(args.image, args.image_glob)
    if image_paths:
        run_image_files(
            detector,
            image_paths,
            show_window=not args.no_window,
            save_results=args.save_image_results,
        )
        return

    cap = open_camera(args.camera, args.width, args.height)
    try:
        while True:
            ok, frame = cap.read()
            if not ok or frame is None:
                raise RuntimeError("Failed to read frame from camera")
            detector.frame_index += 1
            detections = detector.detect(frame)
            drawn = detector.draw(frame.copy(), detections)
            detector.print_status(detections)

            if not args.no_window:
                cv2.imshow("ICAR local webcam detection", drawn)
                key = cv2.waitKey(1) & 0xFF
                if key == ord("q"):
                    break
                if key == ord("s"):
                    detector.save_frame(drawn, detections)
            elif detector.frame_index == 1 or (args.frames and detector.frame_index >= args.frames):
                detector.save_frame(drawn, detections)

            if args.frames and detector.frame_index >= args.frames:
                break
    finally:
        cap.release()
        if not args.no_window:
            cv2.destroyAllWindows()


if __name__ == "__main__":
    main()
