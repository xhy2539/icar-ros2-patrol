#!/usr/bin/env python3
"""Quick smoke test for play_audio and tool consistency."""
import sys
sys.path.insert(0, '.')
from robot_tools import RobotTools

tools = RobotTools()

# 1. Tool definitions
names = [t["tool_name"] for t in RobotTools.TOOLS_DEF]
assert len(names) == 9, f"Expected 9 tools, got {len(names)}: {names}"
print("TOOLS_DEF (9):", " ".join(names))

# 2. play_audio blocking tests
for name in ["beep", "alert", "complete"]:
    r = tools.play_audio(name, blocking=True)
    status = "OK" if r["success"] else "FAIL"
    print("%s play_audio(%s) -> %s" % (status, name, r["message"]))

# 3. Error handling
r = tools.play_audio("nonexistent")
assert r["success"] == False
print("OK   unknown name -> proper error")

r = tools.play_audio(file_path="/tmp/does_not_exist.wav")
assert r["success"] == False
print("OK   missing file -> proper error")

# 4. Query tools (no ROS2)
print("OK   query_vision:", tools.query_vision()["message"])
print("OK   query_navigation:", tools.query_navigation()["message"])
print("OK   check_safety:", tools.check_safety()["message"])

print("\n=== All tests passed ===")
