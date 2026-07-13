#!/usr/bin/env python3
"""Test LLM tool parsing + direct execution."""
import sys, json
sys.path.insert(0, 'llm')
from robot_tools import RobotTools
from deepseek_client import DeepSeekClient

print("=== LLM TOOL PARSING ===")
client = DeepSeekClient()
tests = [
    "播放欢迎语音",
    "前面看到什么了",
    "到哪个点了",
    "周围安全吗",
    "发个警告",
    "巡检A点和B点",
    "立即停下",
]
for t in tests:
    try:
        raw = client.parse_tool_call(t)
        print(">>>", t)
        print("   ", raw[:150])
    except Exception as e:
        print(">>>", t, "-> ERROR:", e)

print()
print("=== DIRECT TOOL EXECUTION ===")
tools = RobotTools()

r = tools.play_audio("beep", blocking=True)
print("play_audio(beep):", r["success"], r["message"][:60])

r = tools.list_available_audio()
print("available audio:", len(r))

r = tools.download_audio("")
print("download_audio(empty):", r["success"], r["message"][:60])

print()
print("All done")
