"""Pure parsing rules for assistant text that may authorize robot motion."""

import re
from typing import Optional


CONTROL_PREFIX = "执行任务："


def command_from_assistant_result(text: str) -> Optional[str]:
    """Return only an explicitly marked command, never conversational text."""
    if CONTROL_PREFIX not in text:
        return None
    command = text.split(CONTROL_PREFIX, 1)[1].strip()
    command = re.split(r"[。！？\n]", command, maxsplit=1)[0].strip()
    return command or None
