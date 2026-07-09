#!/usr/bin/env python3
"""Offline mock patrol demo.

This script does not require ROS2. It demonstrates the integration logic and
report format while navigation/vision/sensor modules are still being connected.
"""

from __future__ import annotations

import json
import time
from dataclasses import dataclass, asdict
from datetime import datetime


@dataclass
class SensorData:
    temperature: float
    humidity: float
    smoke: float
    pm25: float
    light: float
    pressure: float


@dataclass
class Detection:
    class_name: str
    confidence: float
    bbox: list[int]
    image_path: str


class MockNavigation:
    def go_to(self, point: str) -> dict:
        time.sleep(0.2)
        return {
            "status": "ARRIVED",
            "point": point,
            "distance_remain": 0.0,
            "message": f"mock arrived at {point}",
        }


class MockSensor:
    def collect(self, point: str) -> SensorData:
        offset = {"A": 0.0, "B": 1.0, "C": 2.0}.get(point, 0.0)
        return SensorData(
            temperature=28.0 + offset,
            humidity=61.0,
            smoke=8.0,
            pm25=35.0 + offset,
            light=320.0,
            pressure=1013.2,
        )


class MockVision:
    def detect(self, point: str) -> list[Detection]:
        target = "person" if point == "A" else "sign"
        return [
            Detection(
                class_name=target,
                confidence=0.86,
                bbox=[120, 80, 300, 420],
                image_path=f"logs/images/mock_{point}.jpg",
            )
        ]


class PatrolTaskManager:
    def __init__(self):
        self.navigation = MockNavigation()
        self.sensor = MockSensor()
        self.vision = MockVision()
        self.logs: list[dict] = []

    def run(self, route: list[str]) -> list[dict]:
        self._log("TASK_START", {"route": route})
        for point in route:
            self._log("NAV_START", {"point": point})
            nav_result = self.navigation.go_to(point)
            self._log("CHECKPOINT_REACHED", nav_result)

            sensor_data = self.sensor.collect(point)
            self._log("SENSOR_READING", {"point": point, **asdict(sensor_data)})

            detections = self.vision.detect(point)
            self._log(
                "VISION_DETECT",
                {
                    "point": point,
                    "detections": [asdict(item) for item in detections],
                },
            )

        self._log("TASK_END", {"visited": route})
        return self.logs

    def _log(self, event_type: str, data: dict):
        item = {
            "time": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            "event_type": event_type,
            "severity": "INFO",
            "data": data,
        }
        self.logs.append(item)
        print(json.dumps(item, ensure_ascii=False))


def generate_report(logs: list[dict]) -> str:
    points = [
        item["data"]["point"]
        for item in logs
        if item["event_type"] == "CHECKPOINT_REACHED"
    ]
    detections = []
    for item in logs:
        if item["event_type"] == "VISION_DETECT":
            detections.extend(
                det["class_name"] for det in item["data"].get("detections", [])
            )

    return "\n".join(
        [
            "巡检报告",
            f"- 巡检点: {' -> '.join(points)}",
            f"- 视觉目标: {'、'.join(sorted(set(detections))) or '无'}",
            f"- 日志事件数: {len(logs)}",
            "- 结论: mock 巡检闭环已跑通，等待真实导航/视觉/传感器替换。",
        ]
    )


def main():
    route = ["A", "B", "C"]
    manager = PatrolTaskManager()
    logs = manager.run(route)
    print("\n" + generate_report(logs))


if __name__ == "__main__":
    main()
