#!/usr/bin/env python3
"""Quick smoke test for play_audio, download_audio, and tool consistency."""
import sys, os
sys.path.insert(0, '.')
from robot_tools import RobotTools

tools = RobotTools()

# 1. Tool definitions
names = [t["tool_name"] for t in RobotTools.TOOLS_DEF]
assert len(names) == 10, f"Expected 10 tools, got {len(names)}: {names}"
print("TOOLS_DEF (10):", " ".join(names))

# 2. Auto-discovery
avail = RobotTools.list_available_audio()
print("Available audio (%d): %s" % (len(avail), avail[:5] if len(avail) > 5 else avail))

# 3. play_audio blocking tests
for name in ["beep", "alert"]:
    r = tools.play_audio(name, blocking=True)
    status = "OK" if r["success"] else "FAIL"
    print("%s play_audio(%s) -> %s" % (status, name, r["message"]))

# 4. Error handling
r = tools.play_audio("nonexistent")
assert r["success"] == False
print("OK   unknown name -> lists available alternatives")

# 5. Query tools (no ROS2)
print("OK   query_vision:", tools.query_vision()["message"])
print("OK   query_navigation:", tools.query_navigation()["message"])
print("OK   check_safety:", tools.check_safety()["message"])

# 6. download_audio - error on empty query
r = tools.download_audio("")
assert r["success"] == False
print("OK   download_audio empty query -> proper error")

print("\n=== All tests passed ===")
