"""Safe multi-step task plans for the executable LLM gateway."""

from dataclasses import dataclass
from typing import Dict, Iterable, List, Optional


ALLOWED_PLAN_TOOLS = {
    "start_patrol",
    "get_robot_status",
    "query_vision",
    "query_navigation",
    "check_safety",
    "play_audio",
    "start_tracking",
    "stop_tracking",
}
TASK_TERMINAL_STATES = {"COMPLETED", "FAILED", "CANCELLED"}
COMPOUND_MARKERS = ("然后", "之后", "完成后", "接着", "随后", "最后", "并且", "再")


@dataclass(frozen=True)
class PlanStep:
    tool_name: str
    arguments: Dict[str, object]
    wait_for: str = ""


def normalize_plan_steps(raw_steps: Iterable[dict]) -> List[PlanStep]:
    if not isinstance(raw_steps, list) or not raw_steps:
        raise ValueError("complex plan requires a non-empty steps list")
    if len(raw_steps) > 12:
        raise ValueError("complex plan supports at most 12 steps")

    steps = []
    for index, raw in enumerate(raw_steps, start=1):
        if not isinstance(raw, dict):
            raise ValueError(f"plan step {index} must be an object")
        tool_name = str(raw.get("tool_name", "")).strip()
        if tool_name not in ALLOWED_PLAN_TOOLS:
            raise ValueError(f"plan step {index} uses unsupported tool: {tool_name}")
        arguments = raw.get("arguments", {})
        if not isinstance(arguments, dict):
            raise ValueError(f"plan step {index} arguments must be an object")
        wait_for = str(raw.get("wait_for", "")).strip()
        if tool_name == "start_patrol":
            wait_for = wait_for or "task_completed"
        elif wait_for:
            raise ValueError(f"plan step {index} cannot wait for {wait_for}")
        steps.append(PlanStep(tool_name, dict(arguments), wait_for))
    return steps


def build_rule_plan(user_input: str, default_route: List[str]) -> Optional[dict]:
    """Build common compound plans locally; leave open-ended text to the LLM."""
    text = str(user_input).strip()
    if not text or not any(marker in text for marker in COMPOUND_MARKERS):
        return None

    occurrences = []

    patrol_index = min(
        (text.find(word) for word in ("巡检", "巡逻", "巡视") if word in text),
        default=-1,
    )
    if patrol_index >= 0:
        from .tool_intent import _extract_route

        occurrences.append(
            (
                patrol_index,
                {
                    "tool_name": "start_patrol",
                    "arguments": {
                        "route": _extract_route(text, default_route),
                        "user_text": text,
                    },
                    "wait_for": "task_completed",
                },
            )
        )

    audio_words = {
        "播放完成": "complete",
        "完成提示音": "complete",
        "播报完成": "complete",
        "播放警告": "alert",
        "发出警告": "alert",
        "报警": "alert",
        "播放提示音": "beep",
    }
    for phrase, name in audio_words.items():
        index = text.find(phrase)
        if index >= 0:
            occurrences.append(
                (index, {"tool_name": "play_audio", "arguments": {"name": name}})
            )
            break

    query_specs = (
        (("查询视觉", "查看识别结果", "看看识别结果", "看到什么"), "query_vision"),
        (("查询导航", "导航状态", "到了哪里"), "query_navigation"),
        (("检查安全", "是否安全", "障碍物状态"), "check_safety"),
        (("任务状态", "执行进度"), "get_robot_status"),
    )
    for phrases, tool_name in query_specs:
        indices = [text.find(phrase) for phrase in phrases if phrase in text]
        if indices:
            occurrences.append((min(indices), {"tool_name": tool_name, "arguments": {}}))

    occurrences.sort(key=lambda item: item[0])
    steps = [step for _, step in occurrences]
    if len(steps) < 2:
        return None
    return {"tool_name": "execute_plan", "arguments": {"steps": steps}}


class ComplexTaskRunner:
    """Pure state machine; the ROS node performs the returned tool actions."""

    def __init__(self) -> None:
        self.steps: List[PlanStep] = []
        self.index = 0
        self.state = "IDLE"
        self.error = ""

    @property
    def active(self) -> bool:
        return self.state in {"RUNNING", "WAITING"}

    def start(self, raw_steps: List[dict]) -> PlanStep:
        if self.active:
            raise ValueError("another complex plan is already active")
        self.steps = normalize_plan_steps(raw_steps)
        self.index = 0
        self.state = "RUNNING"
        self.error = ""
        return self.steps[0]

    def record_result(self, success: bool, message: str = "") -> Optional[PlanStep]:
        if self.state != "RUNNING":
            return None
        if not success:
            self.state = "FAILED"
            self.error = str(message or "tool execution failed")
            return None

        step = self.steps[self.index]
        if step.wait_for == "task_completed":
            self.state = "WAITING"
            return None
        return self._advance()

    def on_task_status(self, status: str) -> Optional[PlanStep]:
        if self.state != "WAITING":
            return None
        normalized = str(status).upper()
        if normalized not in TASK_TERMINAL_STATES:
            return None
        if normalized != "COMPLETED":
            self.state = "FAILED"
            self.error = f"patrol ended with {normalized}"
            return None
        self.state = "RUNNING"
        return self._advance()

    def _advance(self) -> Optional[PlanStep]:
        self.index += 1
        if self.index >= len(self.steps):
            self.state = "COMPLETED"
            return None
        self.state = "RUNNING"
        return self.steps[self.index]

    def snapshot(self) -> dict:
        return {
            "status": self.state,
            "current_step": min(self.index + 1, len(self.steps)) if self.steps else 0,
            "total_steps": len(self.steps),
            "error": self.error,
            "steps": [step.tool_name for step in self.steps],
        }
