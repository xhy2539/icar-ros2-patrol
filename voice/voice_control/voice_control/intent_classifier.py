"""Deterministic voice intent classification for safety-critical routing."""

import re


EMERGENCY_PATTERNS = (
    r"救命|快来人|紧急停止|立即停止|急停|着火|火灾",
    r"摔倒了|跌倒了|站不起来",
    r"胸痛|喘不上气|呼吸困难",
)

CARE_ALERT_PATTERNS = (
    r"找护士|叫护士|护理员|通知工作人员",
    r"不舒服|头晕|恶心|发烧|疼得厉害",
    r"找不到房间|我迷路了",
)

ROBOT_TASK_PATTERNS = (
    r"开始巡检|去巡检|巡检.+(?:点|区域|房间|走廊)",
    r"去[ABCDEF一二三四五六](?:点|号点)",
    r"返回充电|回充|回到充电",
    r"拍照|识别目标|查看(?:走廊|房间|活动室)",
    r"小车(?:前进|后退|左转|右转|停止)",
)


def classify_intent(text):
    """Return a stable routing decision without calling an LLM."""
    normalized = re.sub(r"\s+", "", str(text or "")).strip()
    if not normalized:
        return {
            "intent": "unknown",
            "confidence": 0.0,
            "requires_confirmation": False,
            "interaction": "clarify",
        }

    if _matches(normalized, EMERGENCY_PATTERNS):
        return {
            "intent": "emergency",
            "confidence": 1.0,
            "requires_confirmation": False,
            "interaction": "interrupt",
        }

    if _matches(normalized, CARE_ALERT_PATTERNS):
        return {
            "intent": "care_alert",
            "confidence": 0.95,
            "requires_confirmation": False,
            "interaction": "notify_staff",
        }

    if _matches(normalized, ROBOT_TASK_PATTERNS):
        return {
            "intent": "robot_task",
            "confidence": 0.9,
            "requires_confirmation": True,
            "interaction": "confirm",
        }

    return {
        "intent": "chat",
        "confidence": 0.8,
        "requires_confirmation": False,
        "interaction": "conversation",
    }


def _matches(text, patterns):
    return any(re.search(pattern, text) for pattern in patterns)
