#!/usr/bin/env python3
"""Test every single tool end-to-end."""
import sys, json, os
sys.path.insert(0, 'llm')
from robot_tools import RobotTools
from deepseek_client import DeepSeekClient
try:
    from json_protocol import extract_json_from_response
except ImportError:
    def extract_json_from_response(text):
        s = text.find('{')
        e = text.rfind('}') + 1
        return text[s:e] if s != -1 and e > 0 else text

tools = RobotTools()
client = DeepSeekClient()

tests = {
    # (user_input, expected_tool)
    "task": [
        ("巡检A点和B点", "get_robot_status"),
        ("当前状态怎么样", "get_robot_status"),
        ("立即停下", "stop_robot"),
        ("取消当前巡检任务", "cancel_task"),
        ("复位任务重新开始", "reset_task"),
    ],
    "query": [
        ("看到什么了", "query_vision"),
        ("前面摄像头检测到什么", "query_vision"),
        ("到哪了", "query_navigation"),
        ("导航到哪个点了", "query_navigation"),
        ("安全吗", "check_safety"),
        ("有没有障碍物", "check_safety"),
    ],
    "audio": [
        ("播放欢迎语音", "play_audio"),
        ("嘀一声", "play_audio"),
        ("发警告", "play_audio"),
        ("播放碎玉轩小曲", "play_audio"),
    ],
}

print("=" * 60)
print("TEST 1: LLM TOOL PARSING (all 10 tools)")
print("=" * 60)
all_ok = 0
all_fail = 0
for category, cases in tests.items():
    print("\n--- %s ---" % category)
    for user_input, expected_tool in cases:
        try:
            raw = client.parse_tool_call(user_input)
            data = json.loads(raw)
            actual = data.get("tool_name", "?")
            match = "OK" if actual == expected_tool else "MISMATCH(expected:%s)" % expected_tool
            if actual == expected_tool:
                all_ok += 1
            else:
                all_fail += 1
            print("  %s %-20s -> %-20s %s" % (match, user_input, actual, json.dumps(data.get("arguments", {}), ensure_ascii=False)[:50]))
        except Exception as e:
            all_fail += 1
            print("  FAIL %-20s -> ERROR: %s" % (user_input, e))

print("\n" + "=" * 60)
print("TEST 2: DIRECT TOOL EXECUTION")
print("=" * 60)

# Audio tools (no ROS2 needed)
print("\n--- play_audio ---")
r = tools.play_audio("beep", blocking=True)
print("  beep: success=%s, msg=%s" % (r["success"], r["message"][:70]))

avail = tools.list_available_audio()
print("  available: %d files -> %s..." % (len(avail), str(avail[:5])))

# Check if playing Chinese-named file works
if "碎玉轩小曲" in avail:
    path = RobotTools._resolve_audio_path("碎玉轩小曲")
    print("  碎玉轩小曲: resolved to %s (%dKB)" % (path, os.path.getsize(path)//1024 if path else 0))

print("\n--- download_audio ---")
r = tools.download_audio("", blocking=True)
print("  empty query: success=%s -> %s" % (r["success"], r["message"][:60]))

print("\n--- query tools (no ROS2 node = no data) ---")
for method, label in [(tools.query_vision, "query_vision"),
                       (tools.query_navigation, "query_navigation"),
                       (tools.check_safety, "check_safety")]:
    r = method()
    print("  %s: success=%s, msg=%s" % (label, r["success"], r["message"]))

# ROS2 tools — only if node available
print("\n--- task tools (require ROS2) ---")
if tools.node is None:
    print("  SKIP: no ROS2 node (run with --ros2 for full test)")
else:
    r = tools.get_robot_status()
    print("  get_robot_status: success=%s, msg=%s" % (r["success"], r["message"][:70]))

print("\n" + "=" * 60)
print("RESULT: %d/%d LLM parsing correct" % (all_ok, all_ok + all_fail))
print("=" * 60)
