import math
from dataclasses import dataclass
from pathlib import Path

import yaml


PROJECT_ROOT = Path(__file__).resolve().parents[2]
CHECKPOINTS_FILE = PROJECT_ROOT / "config" / "navigation" / "mock" / "checkpoints.yaml"


class UnknownCheckpointError(ValueError):
    def __init__(self, name):
        super().__init__(f"unknown checkpoint: {name}")
        self.name = name


@dataclass(frozen=True)
class NavigationGoal:
    name: str
    x: float
    y: float
    yaw: float


def yaw_to_quaternion(yaw):
    return {
        "x": 0.0,
        "y": 0.0,
        "z": math.sin(yaw / 2.0),
        "w": math.cos(yaw / 2.0),
    }


def load_navigation_checkpoints(path=CHECKPOINTS_FILE):
    with Path(path).open("r", encoding="utf-8") as file:
        data = yaml.safe_load(file) or {}
    return data.get("checkpoints", {})


def resolve_route_goals(route, checkpoints):
    goals = []
    for name in route:
        if name not in checkpoints:
            raise UnknownCheckpointError(name)
        checkpoint = checkpoints[name]
        goals.append(
            NavigationGoal(
                name=name,
                x=float(checkpoint["x"]),
                y=float(checkpoint["y"]),
                yaw=float(checkpoint.get("yaw", 0.0)),
            )
        )
    return goals


def goal_to_pose_payload(goal):
    return {
        "frame_id": "map",
        "position": {
            "x": goal.x,
            "y": goal.y,
            "z": 0.0,
        },
        "orientation": yaw_to_quaternion(goal.yaw),
    }
