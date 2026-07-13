"""Pure helpers for normalizing fall detections from box or pose models."""

import math


FALLEN_PERSON_CLASS_KEYS = {
    "fallen_person",
    "fallen person",
    "person_down",
    "person down",
    "person lying",
    "lying person",
    "fall",
    "摔倒",
    "人员摔倒",
}

PERSON_CLASS_KEYS = {"person", "people", "pedestrian", "行人", "人员"}


def _point(keypoints, index, min_confidence):
    if keypoints is None or index >= len(keypoints):
        return None
    point = keypoints[index]
    if point is None or len(point) < 2:
        return None
    x = float(point[0])
    y = float(point[1])
    confidence = float(point[2]) if len(point) > 2 else 1.0
    if not math.isfinite(x) or not math.isfinite(y) or confidence < min_confidence:
        return None
    return x, y


def _midpoint(first, second):
    if first is None and second is None:
        return None
    if first is None:
        return second
    if second is None:
        return first
    return ((first[0] + second[0]) / 2.0, (first[1] + second[1]) / 2.0)


def classify_person_fall(
    raw_class_name,
    mapped_class_name,
    bbox,
    frame_width,
    frame_height,
    *,
    keypoints=None,
    aspect_ratio_threshold=1.15,
    min_area_ratio=0.012,
    keypoint_confidence=0.25,
    torso_horizontal_ratio=0.9,
):
    """Return ``(class_name, is_fallen, reason)`` for one detection.

    Custom fall-model labels take priority. For a normal person label, a pose
    torso close to horizontal or a sufficiently wide box is treated as a fall
    candidate. Task-level multi-frame confirmation handles transient poses.
    """
    raw_key = str(raw_class_name).strip().lower()
    mapped_key = str(mapped_class_name).strip().lower()
    if raw_key in FALLEN_PERSON_CLASS_KEYS or mapped_key in FALLEN_PERSON_CLASS_KEYS:
        return "fallen_person", True, "model_label"
    if raw_key not in PERSON_CLASS_KEYS and mapped_key not in PERSON_CLASS_KEYS:
        return mapped_class_name, False, "not_person"

    x1, y1, x2, y2 = [float(value) for value in bbox[:4]]
    width = max(0.0, x2 - x1)
    height = max(0.0, y2 - y1)
    frame_area = max(1.0, float(frame_width) * float(frame_height))
    if width * height / frame_area < float(min_area_ratio):
        return mapped_class_name, False, "too_small"

    left_shoulder = _point(keypoints, 5, keypoint_confidence)
    right_shoulder = _point(keypoints, 6, keypoint_confidence)
    left_hip = _point(keypoints, 11, keypoint_confidence)
    right_hip = _point(keypoints, 12, keypoint_confidence)
    shoulder = _midpoint(left_shoulder, right_shoulder)
    hip = _midpoint(left_hip, right_hip)
    if shoulder is not None and hip is not None:
        torso_dx = abs(hip[0] - shoulder[0])
        torso_dy = abs(hip[1] - shoulder[1])
        if torso_dx >= max(1.0, torso_dy * float(torso_horizontal_ratio)):
            return "fallen_person", True, "horizontal_torso"

    aspect_ratio = width / max(height, 1.0)
    if aspect_ratio >= float(aspect_ratio_threshold):
        return "fallen_person", True, "wide_person_box"
    return mapped_class_name, False, "upright"
