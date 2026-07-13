import json
import math
from pathlib import Path

import yaml


NAVIGATION_DIR = Path(__file__).resolve().parent
PROJECT_ROOT = NAVIGATION_DIR.parent
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
