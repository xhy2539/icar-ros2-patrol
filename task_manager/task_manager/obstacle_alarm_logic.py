"""Pure transition logic for obstacle alarms."""

from dataclasses import dataclass


@dataclass(frozen=True)
class AlarmDecision:
    event: str = "none"
    active: bool = False
    should_beep: bool = False


class ObstacleAlarmController:
    """Emit edge-triggered alarms with a bounded repeat interval."""

    def __init__(self, repeat_sec: float = 5.0) -> None:
        self.repeat_sec = max(0.1, float(repeat_sec))
        self.active = False
        self.last_alarm_at = float("-inf")

    def update(
        self,
        risk_level: str,
        action: str,
        now: float,
    ) -> AlarmDecision:
        danger = str(risk_level).lower() == "danger" or str(action).lower() == "stop"

        if danger and not self.active:
            self.active = True
            self.last_alarm_at = float(now)
            return AlarmDecision("started", True, True)

        if danger and float(now) - self.last_alarm_at >= self.repeat_sec:
            self.last_alarm_at = float(now)
            return AlarmDecision("repeated", True, True)

        if not danger and self.active:
            self.active = False
            return AlarmDecision("cleared", False, False)

        return AlarmDecision("none", self.active, False)
