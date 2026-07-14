"""Pure state machines for obstacle detours and water hazards."""

from dataclasses import dataclass
from typing import Any, Iterable, Optional


WATER_CLASS_KEYS = {
    "water",
    "puddle",
    "water puddle",
    "standing water",
    "water on floor",
    "flooded",
    "积水",
}

VISUAL_OBSTACLE_CLASS_KEYS = {
    "obstacle",
    "barrier",
    "blockage",
    "roadblock",
    "障碍物",
}

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


@dataclass(frozen=True)
class ObstacleDecision:
    event: str = "none"
    hold: bool = False
    should_replan: bool = False
    failed: bool = False
    retry_count: int = 0
    blocked_sec: float = 0.0


class ObstacleDetourController:
    """Hold motion on danger and resume the same goal after a stable clear."""

    def __init__(
        self,
        clear_sec: float = 1.0,
        max_block_sec: float = 20.0,
        max_replans: int = 3,
    ) -> None:
        self.clear_sec = max(0.0, float(clear_sec))
        self.max_block_sec = max(0.1, float(max_block_sec))
        self.max_replans = max(0, int(max_replans))
        self.hold = False
        self.blocked_since: Optional[float] = None
        self.clear_since: Optional[float] = None
        self.retry_count = 0
        self.failed = False

    def reset_for_goal(self) -> None:
        self.hold = False
        self.blocked_since = None
        self.clear_since = None
        self.retry_count = 0
        self.failed = False

    def update(self, danger: bool, clear: bool, now: float) -> ObstacleDecision:
        now = float(now)
        if self.failed:
            return ObstacleDecision(
                event="none",
                hold=True,
                failed=True,
                retry_count=self.retry_count,
            )

        if danger:
            self.clear_since = None
            if not self.hold:
                if self.retry_count >= self.max_replans:
                    self.failed = True
                    return ObstacleDecision(
                        event="failed",
                        hold=True,
                        failed=True,
                        retry_count=self.retry_count,
                    )
                self.hold = True
                self.blocked_since = now
                self.retry_count += 1
                return ObstacleDecision(
                    event="blocked",
                    hold=True,
                    should_replan=True,
                    retry_count=self.retry_count,
                )

            blocked_start = self.blocked_since if self.blocked_since is not None else now
            blocked_sec = max(0.0, now - float(blocked_start))
            if blocked_sec >= self.max_block_sec:
                self.failed = True
                return ObstacleDecision(
                    event="failed",
                    hold=True,
                    failed=True,
                    retry_count=self.retry_count,
                    blocked_sec=blocked_sec,
                )
            return ObstacleDecision(
                event="none",
                hold=True,
                retry_count=self.retry_count,
                blocked_sec=blocked_sec,
            )

        if not self.hold:
            return ObstacleDecision(retry_count=self.retry_count)

        # Warning/unknown readings keep the hold. Only an explicit safe reading
        # starts the clearance dwell timer.
        if not clear:
            self.clear_since = None
            return ObstacleDecision(hold=True, retry_count=self.retry_count)

        if self.clear_since is None:
            self.clear_since = now
        if now - self.clear_since < self.clear_sec:
            return ObstacleDecision(hold=True, retry_count=self.retry_count)

        self.hold = False
        self.blocked_since = None
        self.clear_since = None
        return ObstacleDecision(
            event="cleared",
            hold=False,
            retry_count=self.retry_count,
        )


@dataclass(frozen=True)
class VisualHazardDecision:
    event: str = "none"
    active: bool = False
    should_report: bool = False
    detection: Optional[dict] = None


def _field(detection: Any, name: str, default: Any = None) -> Any:
    if isinstance(detection, dict):
        return detection.get(name, default)
    return getattr(detection, name, default)


def _matching_detection(
    detections: Iterable[Any],
    min_confidence: float,
    class_keys,
    min_bbox_area: float = 0.0,
) -> Optional[dict]:
    best = None
    for detection in detections or []:
        class_name = str(_field(detection, "class_name", "")).strip()
        if class_name.lower() not in class_keys:
            continue
        confidence = float(_field(detection, "confidence", 0.0))
        if confidence < min_confidence:
            continue
        x_min = int(_field(detection, "x_min", 0))
        y_min = int(_field(detection, "y_min", 0))
        x_max = int(_field(detection, "x_max", 0))
        y_max = int(_field(detection, "y_max", 0))
        bbox_area = (x_max - x_min) * (y_max - y_min)
        if min_bbox_area > 0 and bbox_area < min_bbox_area:
            continue
        candidate = {
            "class_name": class_name,
            "confidence": confidence,
            "bbox": [x_min, y_min, x_max, y_max],
            "image_path": str(_field(detection, "image_path", "")),
        }
        if best is None or candidate["confidence"] > best["confidence"]:
            best = candidate
    return best


class VisualHazardController:
    """Confirm a visual class set and report start/repeat/clear edges."""

    def __init__(
        self,
        min_confidence: float = 0.7,
        confirm_frames: int = 2,
        clear_frames: int = 5,
        repeat_sec: float = 30.0,
        class_keys=None,
        latch_until_reset: bool = False,
    ) -> None:
        self.min_confidence = min(1.0, max(0.0, float(min_confidence)))
        self.confirm_frames = max(1, int(confirm_frames))
        self.clear_frames = max(1, int(clear_frames))
        self.repeat_sec = max(0.1, float(repeat_sec))
        self.class_keys = {
            str(item).strip().lower()
            for item in (class_keys or [])
            if str(item).strip()
        }
        self.latch_until_reset = bool(latch_until_reset)
        self.consecutive = 0
        self.missing_frames = 0
        self.active = False
        self.last_report_at = float("-inf")
        self.last_detection: Optional[dict] = None

    def reset(self) -> None:
        self.consecutive = 0
        self.missing_frames = 0
        self.active = False
        self.last_report_at = float("-inf")
        self.last_detection = None

    def update(self, detections: Iterable[Any], now: float) -> VisualHazardDecision:
        detection = _matching_detection(
            detections,
            self.min_confidence,
            self.class_keys,
        )
        if detection is None:
            self.consecutive = 0
            if self.active:
                if self.latch_until_reset:
                    return VisualHazardDecision(
                        active=True,
                        detection=self.last_detection,
                    )
                self.missing_frames += 1
                if self.missing_frames >= self.clear_frames:
                    previous = self.last_detection
                    self.active = False
                    self.missing_frames = 0
                    return VisualHazardDecision(
                        event="cleared",
                        active=False,
                        should_report=True,
                        detection=previous,
                    )
            return VisualHazardDecision(
                active=self.active,
                detection=self.last_detection,
            )

        self.missing_frames = 0
        self.last_detection = detection
        if self.active:
            if float(now) - self.last_report_at >= self.repeat_sec:
                self.last_report_at = float(now)
                return VisualHazardDecision(
                    event="repeated",
                    active=True,
                    should_report=True,
                    detection=detection,
                )
            return VisualHazardDecision(active=True, detection=detection)

        self.consecutive += 1
        if self.consecutive < self.confirm_frames:
            return VisualHazardDecision(detection=detection)

        self.active = True
        self.last_report_at = float(now)
        return VisualHazardDecision(
            event="started",
            active=True,
            should_report=True,
            detection=detection,
        )


class WaterHazardController(VisualHazardController):
    """Water-specific compatibility wrapper for the generic controller."""

    def __init__(
        self,
        min_confidence: float = 0.7,
        confirm_frames: int = 2,
        clear_frames: int = 5,
        repeat_sec: float = 30.0,
    ) -> None:
        super().__init__(
            min_confidence=min_confidence,
            confirm_frames=confirm_frames,
            clear_frames=clear_frames,
            repeat_sec=repeat_sec,
            class_keys=WATER_CLASS_KEYS,
        )
