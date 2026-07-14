import argparse
import csv
import glob
import json
import time
from pathlib import Path

import cv2
import numpy as np

try:
    from ultralytics import YOLO
except ImportError as exc:
    raise SystemExit("ultralytics is required: pip install ultralytics") from exc


IMAGE_EXTS = {".jpg", ".jpeg", ".png", ".bmp", ".webp"}
VIDEO_EXTS = {".mp4", ".avi", ".mov", ".mkv", ".m4v"}


def parse_size(value):
    text = str(value or "").strip().lower()
    if not text or text in {"none", "off"}:
        return None
    if "x" in text:
        left, right = text.split("x", 1)
    elif "," in text:
        left, right = text.split(",", 1)
    else:
        raise ValueError(f"size must look like 640x480, got {value!r}")
    width = int(left.strip())
    height = int(right.strip())
    if width <= 0 or height <= 0:
        raise ValueError(f"invalid size: {value!r}")
    return width, height


def is_camera_source(source):
    text = str(source).strip().lower()
    if text.startswith("camera:"):
        return True
    return text.isdigit()


def camera_index(source):
    text = str(source).strip().lower()
    if text.startswith("camera:"):
        return int(text.split(":", 1)[1])
    return int(text)


def expand_image_sources(source):
    path = Path(source)
    if path.is_dir():
        files = [
            item
            for item in sorted(path.iterdir())
            if item.is_file() and item.suffix.lower() in IMAGE_EXTS
        ]
        return files
    matches = [Path(item) for item in sorted(glob.glob(source))]
    if matches:
        return [
            item
            for item in matches
            if item.is_file() and item.suffix.lower() in IMAGE_EXTS
        ]
    if path.is_file() and path.suffix.lower() in IMAGE_EXTS:
        return [path]
    return []


def resize_frame(frame, size):
    if size is None:
        return frame
    width, height = size
    return cv2.resize(frame, (width, height), interpolation=cv2.INTER_AREA)


def open_camera(index, size):
    backends = [cv2.CAP_DSHOW, cv2.CAP_MSMF, cv2.CAP_ANY]
    for backend in backends:
        capture = cv2.VideoCapture(index, backend)
        if not capture.isOpened():
            capture.release()
            continue
        if size is not None:
            capture.set(cv2.CAP_PROP_FRAME_WIDTH, size[0])
            capture.set(cv2.CAP_PROP_FRAME_HEIGHT, size[1])
        ok, frame = capture.read()
        if ok and frame is not None:
            return capture
        capture.release()
    raise RuntimeError(f"cannot open camera index {index}")


def iter_frames(args):
    source = str(args.source)
    capture_size = parse_size(args.camera_size)
    eval_size = parse_size(args.eval_size)

    if is_camera_source(source):
        capture = open_camera(camera_index(source), capture_size)
        try:
            index = 0
            while args.frames <= 0 or index < args.frames:
                ok, frame = capture.read()
                if not ok or frame is None:
                    break
                index += 1
                if args.sample_every > 1 and (index - 1) % args.sample_every != 0:
                    continue
                yield index, f"camera:{camera_index(source)}", resize_frame(frame, eval_size)
        finally:
            capture.release()
        return

    path = Path(source)
    if path.is_file() and path.suffix.lower() in VIDEO_EXTS:
        capture = cv2.VideoCapture(str(path))
        if not capture.isOpened():
            raise RuntimeError(f"cannot open video: {path}")
        try:
            index = 0
            saved = 0
            while args.frames <= 0 or saved < args.frames:
                ok, frame = capture.read()
                if not ok or frame is None:
                    break
                index += 1
                if args.sample_every > 1 and (index - 1) % args.sample_every != 0:
                    continue
                saved += 1
                yield index, path.name, resize_frame(frame, eval_size)
        finally:
            capture.release()
        return

    image_files = expand_image_sources(source)
    if not image_files:
        raise RuntimeError(f"no image/video/camera source found for {source!r}")
    for index, image_path in enumerate(image_files, start=1):
        if args.frames > 0 and index > args.frames:
            break
        frame = cv2.imread(str(image_path))
        if frame is None:
            continue
        yield index, image_path.name, resize_frame(frame, eval_size)


def tensor_to_numpy(value):
    if value is None:
        return None
    if hasattr(value, "cpu"):
        value = value.cpu()
    if hasattr(value, "numpy"):
        return value.numpy()
    return value


def border_touches(bbox, width, height):
    x1, y1, x2, y2 = bbox
    margin = max(4, int(min(width, height) * 0.015))
    touches = 0
    if x1 <= margin:
        touches += 1
    if y1 <= margin:
        touches += 1
    if x2 >= width - 1 - margin:
        touches += 1
    if y2 >= height - 1 - margin:
        touches += 1
    return touches


def rejection_reason(det, args):
    if args.max_area_ratio < 1.0 and det["bbox_area_ratio"] > args.max_area_ratio:
        return "bbox_too_large"
    if (
        args.max_mask_area_ratio < 1.0
        and det["mask_area_ratio"] > args.max_mask_area_ratio
    ):
        return "mask_too_large"
    if (
        args.reject_full_border
        and det["border_touches"] >= 4
        and det["bbox_area_ratio"] > args.full_border_min_area_ratio
    ):
        return "touches_all_borders"
    return ""


def boxes_are_near(first, second, proximity):
    ax1, ay1, ax2, ay2 = first
    bx1, by1, bx2, by2 = second
    return not (
        ax2 + proximity < bx1
        or bx2 + proximity < ax1
        or ay2 + proximity < by1
        or by2 + proximity < ay1
    )


def merge_component_clusters(components, proximity):
    parent = list(range(len(components)))

    def find(index):
        while parent[index] != index:
            parent[index] = parent[parent[index]]
            index = parent[index]
        return index

    def union(left, right):
        left_root = find(left)
        right_root = find(right)
        if left_root != right_root:
            parent[right_root] = left_root

    for left in range(len(components)):
        for right in range(left + 1, len(components)):
            if boxes_are_near(components[left]["bbox"], components[right]["bbox"], proximity):
                union(left, right)

    clusters = {}
    for index, component in enumerate(components):
        clusters.setdefault(find(index), []).append(component)
    return list(clusters.values())


def reflective_water_candidates(frame, args, base_confidence, raw_class):
    """Refine broad reflective-floor predictions into local puddle candidates.

    Transparent water in the corridor often appears as thin local highlights
    and curved bright boundaries. This heuristic is only used after the YOLO
    mask is rejected for being too broad.
    """
    height, width = frame.shape[:2]
    frame_area = float(max(1, width * height))
    gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
    hsv = cv2.cvtColor(frame, cv2.COLOR_BGR2HSV)
    saturation = hsv[:, :, 1]
    value = hsv[:, :, 2]

    blur = cv2.GaussianBlur(gray, (0, 0), 9)
    local_bright = cv2.subtract(gray, blur)
    top_hat = cv2.morphologyEx(
        gray,
        cv2.MORPH_TOPHAT,
        cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (21, 21)),
    )
    mask = (
        ((local_bright > args.refine_local_contrast) | (top_hat > args.refine_tophat))
        & (value > args.refine_min_value)
        & (saturation < args.refine_max_saturation)
    ).astype("uint8") * 255
    mask = cv2.morphologyEx(mask, cv2.MORPH_OPEN, np.ones((2, 2), np.uint8))
    dilation = max(3, int(args.refine_dilation))
    if dilation % 2 == 0:
        dilation += 1
    kernel = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (dilation, dilation))
    mask = cv2.dilate(mask, kernel, iterations=1)
    close_kernel = cv2.getStructuringElement(
        cv2.MORPH_ELLIPSE, (dilation * 2 + 1, dilation + 2)
    )
    mask = cv2.morphologyEx(mask, cv2.MORPH_CLOSE, close_kernel)

    count, _labels, stats, _centroids = cv2.connectedComponentsWithStats(mask)
    components = []
    min_component_area = max(80, int(frame_area * 0.00025))
    for index in range(1, count):
        x, y, component_width, component_height, area = [int(value) for value in stats[index]]
        if area < min_component_area or component_width < 8 or component_height < 8:
            continue
        bbox = [x, y, x + component_width, y + component_height]
        bbox_area_ratio = component_width * component_height / frame_area
        if bbox_area_ratio > args.refine_max_component_area_ratio:
            continue
        if border_touches(bbox, width, height) > 0:
            continue
        components.append({"bbox": bbox, "area": area})

    proximity = max(18, int(min(width, height) * args.refine_cluster_proximity_ratio))
    clusters = merge_component_clusters(components, proximity)
    candidates = []
    for cluster in clusters:
        x1 = min(item["bbox"][0] for item in cluster)
        y1 = min(item["bbox"][1] for item in cluster)
        x2 = max(item["bbox"][2] for item in cluster)
        y2 = max(item["bbox"][3] for item in cluster)
        bbox_width = x2 - x1
        bbox_height = y2 - y1
        bbox_area_ratio = bbox_width * bbox_height / frame_area
        if bbox_area_ratio < args.refine_min_area_ratio:
            continue
        if bbox_area_ratio > args.refine_max_area_ratio:
            continue
        if bbox_width < width * 0.06 or bbox_height < height * 0.035:
            continue
        if border_touches([x1, y1, x2, y2], width, height) >= 2:
            continue
        component_area = sum(item["area"] for item in cluster)
        score = component_area * (1.0 + min(0.3, bbox_area_ratio))
        candidates.append(
            {
                "class_name": args.water_class_name,
                "raw_class_name": raw_class,
                "confidence": round(max(0.01, min(0.72, base_confidence * 0.75)), 4),
                "bbox": [int(x1), int(y1), int(x2), int(y2)],
                "bbox_area_ratio": round(bbox_area_ratio, 6),
                "mask_area_ratio": round(component_area / frame_area, 6),
                "border_touches": border_touches([x1, y1, x2, y2], width, height),
                "source": "reflection_refine",
                "refined": True,
                "refine_score": round(float(score), 2),
            }
        )

    candidates.sort(key=lambda item: item["refine_score"], reverse=True)
    return candidates[: args.refine_max_candidates]


def detect_water(model, frame, args):
    results = model.predict(
        frame,
        imgsz=args.imgsz,
        conf=args.conf,
        iou=args.iou,
        device=args.device or None,
        verbose=False,
    )
    if not results:
        return []

    result = results[0]
    names = getattr(result, "names", {}) or {}
    boxes = getattr(result, "boxes", None)
    masks = getattr(result, "masks", None)
    mask_data = tensor_to_numpy(getattr(masks, "data", None)) if masks is not None else None
    if boxes is None:
        return []

    height, width = frame.shape[:2]
    frame_area = float(max(1, width * height))
    detections = []
    broad_rejections = []
    for index, box in enumerate(boxes):
        cls_id = int(box.cls[0].item())
        raw_class = str(names.get(cls_id, cls_id))
        confidence = float(box.conf[0].item())
        x1, y1, x2, y2 = [int(round(v)) for v in box.xyxy[0].tolist()]
        x1 = max(0, min(width - 1, x1))
        y1 = max(0, min(height - 1, y1))
        x2 = max(0, min(width - 1, x2))
        y2 = max(0, min(height - 1, y2))
        bbox_area_ratio = max(0, x2 - x1) * max(0, y2 - y1) / frame_area
        mask_area_ratio = 0.0
        if mask_data is not None and index < len(mask_data):
            mask = mask_data[index]
            mask_area_ratio = float((mask > 0.5).sum()) / float(max(1, mask.size))
        if bbox_area_ratio < args.min_area_ratio and mask_area_ratio < args.min_area_ratio:
            continue
        det = {
            "class_name": args.water_class_name,
            "raw_class_name": raw_class,
            "confidence": round(confidence, 4),
            "bbox": [x1, y1, x2, y2],
            "bbox_area_ratio": round(bbox_area_ratio, 6),
            "mask_area_ratio": round(mask_area_ratio, 6),
            "border_touches": border_touches([x1, y1, x2, y2], width, height),
        }
        reason = rejection_reason(det, args)
        if reason:
            det["rejected"] = True
            det["reject_reason"] = reason
            broad_rejections.append(det)
        detections.append(det)
    kept = [det for det in detections if not det.get("rejected")]
    rejected = [det for det in detections if det.get("rejected")]
    if args.refine_reflection and broad_rejections:
        best_rejected = max(broad_rejections, key=lambda item: item["confidence"])
        refined = reflective_water_candidates(
            frame,
            args,
            best_rejected["confidence"],
            best_rejected.get("raw_class_name", args.water_class_name),
        )
        if refined:
            for item in refined:
                item["refined_from_reject_reason"] = best_rejected.get("reject_reason", "")
            kept.extend(refined)
    return kept, rejected


def draw(frame, detections, label_prefix, rejected=None):
    output = frame.copy()
    rejected = rejected or []
    for det in detections:
        x1, y1, x2, y2 = det["bbox"]
        label = (
            f"{det['class_name']} {det['confidence']:.2f} "
            f"a={det['bbox_area_ratio']:.3f}"
        )
        cv2.rectangle(output, (x1, y1), (x2, y2), (255, 120, 0), 2)
        cv2.putText(
            output,
            label,
            (x1, max(18, y1 - 8)),
            cv2.FONT_HERSHEY_SIMPLEX,
            0.5,
            (255, 120, 0),
            2,
            cv2.LINE_AA,
        )
    for det in rejected:
        x1, y1, x2, y2 = det["bbox"]
        reason = det.get("reject_reason", "rejected")
        label = f"reject:{reason} {det['confidence']:.2f}"
        cv2.rectangle(output, (x1, y1), (x2, y2), (40, 40, 255), 2)
        cv2.putText(
            output,
            label,
            (x1, min(output.shape[0] - 8, max(18, y1 + 18))),
            cv2.FONT_HERSHEY_SIMPLEX,
            0.5,
            (40, 40, 255),
            2,
            cv2.LINE_AA,
        )
    cv2.putText(
        output,
        label_prefix,
        (10, 24),
        cv2.FONT_HERSHEY_SIMPLEX,
        0.65,
        (240, 240, 240),
        2,
        cv2.LINE_AA,
    )
    return output


def should_save_frame(args, frame_count, detections, rejected=None):
    if args.save_all:
        return True
    if detections and args.save_positives:
        return True
    if rejected and args.save_positives:
        return True
    if args.save_every > 0 and frame_count % args.save_every == 0:
        return True
    return frame_count == 1


def summarize(rows):
    total = len(rows)
    positive = sum(1 for row in rows if row["positive"])
    max_conf = max((row["max_confidence"] for row in rows), default=0.0)
    stable_runs = []
    run = 0
    for row in rows:
        if row["positive"]:
            run += 1
        elif run:
            stable_runs.append(run)
            run = 0
    if run:
        stable_runs.append(run)
    return {
        "frames": total,
        "positive_frames": positive,
        "positive_rate": round(positive / total, 4) if total else 0.0,
        "max_confidence": round(max_conf, 4),
        "max_consecutive_positive": max(stable_runs, default=0),
    }


def build_parser():
    parser = argparse.ArgumentParser(
        description="Evaluate the local water/puddle YOLO model on camera, images, or video."
    )
    parser.add_argument("--source", default="0", help="camera index, image, directory, glob, or video")
    parser.add_argument("--model", default="models/water_seg_v1.pt")
    parser.add_argument("--out-dir", default="local_detection_samples/water_eval")
    parser.add_argument("--tag", default="water_eval")
    parser.add_argument("--device", default="", help="cpu, 0, cuda:0, etc.")
    parser.add_argument("--imgsz", type=int, default=320)
    parser.add_argument("--conf", type=float, default=0.25)
    parser.add_argument("--iou", type=float, default=0.5)
    parser.add_argument("--min-area-ratio", type=float, default=0.002)
    parser.add_argument(
        "--max-area-ratio",
        type=float,
        default=0.85,
        help="reject detections whose bbox covers too much of the image; use 1.0 to disable",
    )
    parser.add_argument(
        "--max-mask-area-ratio",
        type=float,
        default=0.75,
        help="reject segmentation masks that cover too much of the image; use 1.0 to disable",
    )
    border_group = parser.add_mutually_exclusive_group()
    border_group.add_argument(
        "--reject-full-border",
        dest="reject_full_border",
        action="store_true",
        help="reject broad boxes touching all four image borders",
    )
    border_group.add_argument(
        "--no-reject-full-border",
        dest="reject_full_border",
        action="store_false",
        help="keep broad boxes even if they touch all four image borders",
    )
    parser.set_defaults(reject_full_border=True)
    parser.add_argument("--full-border-min-area-ratio", type=float, default=0.5)
    refine_group = parser.add_mutually_exclusive_group()
    refine_group.add_argument(
        "--refine-reflection",
        dest="refine_reflection",
        action="store_true",
        help="refine over-broad water predictions using reflective puddle highlights",
    )
    refine_group.add_argument(
        "--no-refine-reflection",
        dest="refine_reflection",
        action="store_false",
        help="disable reflective puddle refinement",
    )
    parser.set_defaults(refine_reflection=True)
    parser.add_argument("--refine-local-contrast", type=float, default=12.0)
    parser.add_argument("--refine-tophat", type=float, default=16.0)
    parser.add_argument("--refine-min-value", type=float, default=120.0)
    parser.add_argument("--refine-max-saturation", type=float, default=90.0)
    parser.add_argument("--refine-dilation", type=int, default=9)
    parser.add_argument("--refine-cluster-proximity-ratio", type=float, default=0.055)
    parser.add_argument("--refine-min-area-ratio", type=float, default=0.008)
    parser.add_argument("--refine-max-area-ratio", type=float, default=0.28)
    parser.add_argument("--refine-max-component-area-ratio", type=float, default=0.12)
    parser.add_argument("--refine-max-candidates", type=int, default=1)
    parser.add_argument("--water-class-name", default="water")
    parser.add_argument("--camera-size", default="640x480")
    parser.add_argument(
        "--eval-size",
        default="640x480",
        help="resize each frame before inference; use none to keep source size",
    )
    parser.add_argument("--frames", type=int, default=60, help="0 means all/live until stopped")
    parser.add_argument("--sample-every", type=int, default=1)
    parser.add_argument("--save-every", type=int, default=30)
    parser.add_argument("--save-all", action="store_true")
    parser.add_argument("--save-positives", action="store_true", default=True)
    parser.add_argument("--show", action="store_true")
    return parser


def main():
    args = build_parser().parse_args()
    out_dir = Path(args.out_dir) / f"{args.tag}_{time.strftime('%Y%m%d_%H%M%S')}"
    image_dir = out_dir / "frames"
    out_dir.mkdir(parents=True, exist_ok=True)
    image_dir.mkdir(parents=True, exist_ok=True)

    model = YOLO(args.model)
    rows = []
    csv_path = out_dir / "frames.csv"
    jsonl_path = out_dir / "frames.jsonl"

    with csv_path.open("w", newline="", encoding="utf-8") as csv_file, jsonl_path.open(
        "w", encoding="utf-8"
    ) as jsonl_file:
        fieldnames = [
            "frame_index",
            "source",
            "positive",
            "detections",
            "rejected_detections",
            "max_confidence",
            "max_bbox_area_ratio",
            "max_mask_area_ratio",
            "image_path",
        ]
        writer = csv.DictWriter(csv_file, fieldnames=fieldnames)
        writer.writeheader()

        for count, (frame_index, source_name, frame) in enumerate(iter_frames(args), start=1):
            detections, rejected = detect_water(model, frame, args)
            max_conf = max((det["confidence"] for det in detections), default=0.0)
            max_bbox_area = max(
                (det["bbox_area_ratio"] for det in detections), default=0.0
            )
            max_mask_area = max(
                (det["mask_area_ratio"] for det in detections), default=0.0
            )
            label = f"{args.tag} frame={frame_index} det={len(detections)}"
            image_path = ""
            if should_save_frame(args, count, detections, rejected):
                annotated = draw(frame, detections, label, rejected)
                image_path = str(image_dir / f"{count:06d}.jpg")
                cv2.imwrite(image_path, annotated)
            row = {
                "frame_index": frame_index,
                "source": source_name,
                "positive": bool(detections),
                "detections": len(detections),
                "rejected_detections": len(rejected),
                "max_confidence": float(max_conf),
                "max_bbox_area_ratio": float(max_bbox_area),
                "max_mask_area_ratio": float(max_mask_area),
                "image_path": image_path,
            }
            rows.append(row)
            writer.writerow(row)
            jsonl_file.write(
                json.dumps(
                    {"frame": row, "detections": detections, "rejected": rejected},
                    ensure_ascii=False,
                    separators=(",", ":"),
                )
                + "\n"
            )
            print(
                json.dumps(
                    {"frame": row, "detections": detections, "rejected": rejected},
                    ensure_ascii=False,
                )
            )

            if args.show:
                cv2.imshow("water_eval", draw(frame, detections, label, rejected))
                if cv2.waitKey(1) & 0xFF == ord("q"):
                    break

    summary = summarize(rows)
    summary["model"] = args.model
    summary["source"] = str(args.source)
    summary["tag"] = args.tag
    summary["conf"] = args.conf
    summary["imgsz"] = args.imgsz
    summary["min_area_ratio"] = args.min_area_ratio
    summary["max_area_ratio"] = args.max_area_ratio
    summary["max_mask_area_ratio"] = args.max_mask_area_ratio
    summary["reject_full_border"] = args.reject_full_border
    summary["refine_reflection"] = args.refine_reflection
    summary["out_dir"] = str(out_dir)
    (out_dir / "summary.json").write_text(
        json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    if args.show:
        cv2.destroyAllWindows()
    print("SUMMARY " + json.dumps(summary, ensure_ascii=False))


if __name__ == "__main__":
    main()
