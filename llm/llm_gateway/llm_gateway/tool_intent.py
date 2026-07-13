"""Deterministic safety-first intents for executable robot commands.

The LLM gateway uses these rules as an offline fallback and as a fast path for
commands that must not wait for a cloud model, especially emergency stop.
"""

import re
from typing import Dict, List, Optional


_POINT_PATTERN = re.compile(r"(?<![A-Z])([A-F])(?![A-Z])", re.IGNORECASE)


def _extract_route(text: str, default_route: List[str]) -> List[str]:
    route = []
    for point in _POINT_PATTERN.findall(text.upper()):
        if point not in route:
            route.append(point)
    return route or list(default_route)


def is_reset_confirmation(text: str) -> bool:
    compact = re.sub(r"\s+", "", str(text)).lower()
    return any(
        marker in compact
        for marker in ("确认复位", "确认重置", "确认安全", "confirmreset")
    )


def parse_tool_intent(
    user_input: str, default_route: Optional[List[str]] = None
) -> Optional[Dict[str, object]]:
    """Return a supported tool call when rules confidently match the input."""
    text = user_input.strip()
    compact = re.sub(r"\s+", "", text).lower()
    if not compact:
        return None
    default_route = default_route or ["A", "B", "C"]

    tracking_words = ("跟踪", "追踪", "跟随", "尾随")
    stop_words = ("停止", "停下", "别动", "不要动", "急停", "紧急停车")

    if any(word in compact for word in tracking_words):
        if any(word in compact for word in stop_words + ("取消", "结束", "关闭")):
            return {
                "tool_name": "stop_tracking",
                "arguments": {"reason": text},
            }
        targets = ["person"]
        if "车辆" in compact or "小车" in compact:
            targets = ["vehicle"]
        return {
            "tool_name": "start_tracking",
            "arguments": {"target_classes": targets, "user_text": text},
        }

    if "取消" in compact and any(
        word in compact for word in ("任务", "巡检", "巡逻", "导航")
    ):
        return {"tool_name": "cancel_task", "arguments": {"reason": text}}

    if is_reset_confirmation(compact) or "安全后复位" in compact:
        return {"tool_name": "reset_task", "arguments": {"reason": text}}

    if any(word in compact for word in stop_words):
        return {"tool_name": "stop_robot", "arguments": {"reason": text}}

    if any(word in compact for word in ("巡检", "巡逻", "巡视")) or re.search(
        r"(?:去|前往|导航到)[A-Fa-f](?:点)?", compact
    ):
        return {
            "tool_name": "start_patrol",
            "arguments": {
                "route": _extract_route(text, default_route),
                "user_text": text,
            },
        }

    if any(word in compact for word in ("看到什么", "看见什么", "摄像头", "检测到什么", "前面有人")):
        return {"tool_name": "query_vision", "arguments": {}}
    if any(word in compact for word in ("安全吗", "障碍物", "有障碍", "危险吗", "会撞")):
        return {"tool_name": "check_safety", "arguments": {}}
    if any(word in compact for word in ("在哪里", "在哪", "到了吗", "还有多远", "导航状态", "到哪")):
        return {"tool_name": "query_navigation", "arguments": {}}
    if any(word in compact for word in ("任务状态", "当前状态", "进度", "在做什么", "什么状态")):
        return {"tool_name": "get_robot_status", "arguments": {}}

    audio_map = {
        "欢迎": "welcome",
        "提示音": "beep",
        "警告": "alert",
        "告警": "alert",
        "危险": "danger",
        "完成": "complete",
        "再见": "bye",
    }
    if any(word in compact for word in ("播放", "放一段", "播报", "提示音")):
        name = next(
            (audio_name for word, audio_name in audio_map.items() if word in compact),
            "beep",
        )
        return {"tool_name": "play_audio", "arguments": {"name": name}}

    return None
