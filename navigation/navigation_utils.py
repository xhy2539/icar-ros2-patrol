import json
import math
from pathlib import Path

import yaml


NAVIGATION_DIR = Path(__file__).resolve().parent
PROJECT_ROOT = NAVIGATION_DIR.parent
# 兼容 ROS2 workspace 布局 (src/navigation) 和开发布局 (navigation/)
if PROJECT_ROOT.name == "src":
    PROJECT_ROOT = PROJECT_ROOT.parent
MOCK_CONFIG_DIR = PROJECT_ROOT / "config" / "navigation" / "mock"
MAP_DIR = PROJECT_ROOT / "config" / "navigation" / "maps"


def load_yaml(path: Path):
    with path.open("r", encoding="utf-8") as file:
        return yaml.safe_load(file)


def clamp(value: float, minimum: float, maximum: float) -> float:
    return max(minimum, min(maximum, value))


def yaw_to_quaternion(yaw: float):
    return {
        "x": 0.0,
        "y": 0.0,
        "z": math.sin(yaw / 2.0),
        "w": math.cos(yaw / 2.0),
    }


def quaternion_to_yaw(z: float, w: float) -> float:
    return math.atan2(2.0 * w * z, 1.0 - 2.0 * z * z)


def interpolate_pose(start_pose: dict, end_pose: dict, progress: float):
    progress = clamp(progress, 0.0, 1.0)
    return {
        "x": start_pose["x"] + (end_pose["x"] - start_pose["x"]) * progress,
        "y": start_pose["y"] + (end_pose["y"] - start_pose["y"]) * progress,
        "yaw": start_pose["yaw"] + (end_pose["yaw"] - start_pose["yaw"]) * progress,
    }


def distance_between(start_pose: dict, end_pose: dict) -> float:
    return math.hypot(end_pose["x"] - start_pose["x"], end_pose["y"] - start_pose["y"])


def parse_pgm(file_path: Path, invert: bool = False):
    """Parse PGM (P2 ASCII or P5 binary) into occupancy grid values.

    Args:
        file_path: Path to .pgm file.
        invert: If False (default), bright=occupied, dark=free (mock map
                convention: pixel value directly encodes occupancy×100).
                If True, dark=occupied, bright=free (standard ROS SLAM map
                convention: 0=black=obstacle, 254=white=free).

    Returns (width, height, occupancy_list) where occupancy values are:
        100 — occupied (obstacle)
        0   — free (drivable)
        -1  — unknown (intermediate pixel)
    """
    with file_path.open("rb") as fh:
        magic = fh.readline().strip()
        if magic not in (b"P2", b"P5"):
            raise ValueError(f"Unsupported PGM format: {magic!r} in {file_path}")

        # Collect header tokens (skip comments)
        header_tokens = []
        while len(header_tokens) < 3:
            line = fh.readline()
            stripped = line.strip()
            if not stripped or stripped.startswith(b"#"):
                continue
            header_tokens.extend(stripped.split())

        width = int(header_tokens[0])
        height = int(header_tokens[1])
        max_value = int(header_tokens[2])

        if magic == b"P2":
            # Remaining ASCII tokens
            tokens = [int(header_tokens[0]), int(header_tokens[1]), int(header_tokens[2])]
            for line in fh:
                stripped = line.strip()
                if not stripped or stripped.startswith(b"#"):
                    continue
                tokens.extend(int(v) for v in stripped.split())
            raw_values = tokens[3:]  # skip width, height, max_value
        else:
            # P5 — remaining bytes are binary pixel data
            raw_bytes = fh.read()
            expected = width * height
            if max_value <= 255:
                raw_values = list(raw_bytes[:expected])
            else:
                raw_values = []
                for i in range(0, min(len(raw_bytes), expected * 2), 2):
                    raw_values.append(int.from_bytes(raw_bytes[i:i + 2], "big"))

    if len(raw_values) != width * height:
        raise ValueError(
            f"PGM size mismatch in {file_path}: "
            f"expected {width}×{height}={width * height}, "
            f"got {len(raw_values)}"
        )

    occupancy = []
    occupied_thresh = 0.65
    free_thresh = 0.20

    for pixel in raw_values:
        ratio = pixel / max_value
        if invert:
            # Standard ROS SLAM convention: dark=obstacle, bright=free
            # pixel=0       → ratio=0.0 → occupied (100)
            # pixel=max_val → ratio=1.0 → free (0)
            if ratio <= (1.0 - occupied_thresh):
                occupancy.append(100)
            elif ratio >= (1.0 - free_thresh):
                occupancy.append(0)
            else:
                occupancy.append(-1)
        else:
            # Mock map convention: bright=obstacle, dark=free
            if ratio >= occupied_thresh:
                occupancy.append(100)
            elif ratio <= free_thresh:
                occupancy.append(0)
            else:
                occupancy.append(-1)
    return width, height, occupancy


def load_checkpoints():
    data = load_yaml(MOCK_CONFIG_DIR / "checkpoints.yaml")
    return data.get("route", []), data.get("checkpoints", {})


def load_map_metadata():
    return load_yaml(MOCK_CONFIG_DIR / "map_metadata.yaml")


def load_nav_scenarios():
    return load_yaml(MOCK_CONFIG_DIR / "nav_scenarios.yaml")


def load_obstacle_scenarios():
    return load_yaml(MOCK_CONFIG_DIR / "obstacle_scenarios.yaml")


def parse_json_message(raw_message: str):
    if not raw_message:
        return {}
    try:
        return json.loads(raw_message)
    except json.JSONDecodeError:
        return {}


def dump_json_message(payload: dict) -> str:
    return json.dumps(payload, ensure_ascii=False, sort_keys=True)
