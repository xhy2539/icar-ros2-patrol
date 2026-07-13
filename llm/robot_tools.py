"""
机器人工具封装
==============
功能：
  - 封装车端ROS2接口，提供安全的任务控制能力
  - get_robot_status(): 查询当前任务状态
  - stop_robot(): 立即停车，进入安全停止状态
  - cancel_task(): 取消当前巡检任务并停车
  - reset_task(): 复位任务状态，使小车可以接收新任务
  - start_patrol(): 启动巡检任务
  - play_audio(): 调用音箱播放音频文件
  - query_vision/navigation/safety(): 查询传感器缓存数据

ROS2接口映射：
  - /task/control (Service): 任务控制接口
  - /task/request (Topic): 任务请求发布

注意：需要ROS2环境和icar_interfaces包
"""
import json
import os
import shutil
import subprocess
import threading
import platform
from typing import Optional, List, Dict, Any

# ── 音频目录和注册表 ──────────────────────────────────────────
AUDIO_DIR = os.environ.get("ICAR_AUDIO_DIR", "/home/jetson/icar-ros2-patrol/audio")

AUDIO_REGISTRY: Dict[str, str] = {
    "welcome":      "welcome.wav",
    "start_patrol": "start_patrol.wav",
    "complete":     "complete.wav",
    "alert":        "alert.wav",
    "beep":         "beep.wav",
    "stop":         "stop.wav",
    "danger":       "danger.wav",
    "info":         "info.wav",
    "error":        "error.wav",
    "bye":          "bye.wav",
}


class RobotTools:
    def __init__(self, node=None):
        self.node = node
        self.task_control_client = None
        self.task_request_publisher = None
        self._init_ros2()

    def _init_ros2(self):
        if self.node is None:
            return

        try:
            from icar_interfaces.srv import TaskControl
            from icar_interfaces.msg import TaskRequest
            from rclpy.qos import QoSProfile, ReliabilityPolicy

            qos = QoSProfile(depth=10, reliability=ReliabilityPolicy.RELIABLE)

            self.task_control_client = self.node.create_client(
                TaskControl, '/task/control'
            )

            self.task_request_publisher = self.node.create_publisher(
                TaskRequest, '/task/request', qos
            )

            self.node.get_logger().info("Robot tools initialized")

        except ImportError as e:
            if self.node:
                self.node.get_logger().warn(f"icar_interfaces not available: {e}")

    def call_task_control(self, action: str, reason: str, payload_json: str = "{}") -> dict:
        if self.task_control_client is None:
            return {"success": False, "message": "ROS2 node not initialized, cannot call /task/control"}

        from icar_interfaces.srv import TaskControl
        import rclpy

        req = TaskControl.Request()
        req.action = action
        req.reason = reason
        req.payload_json = payload_json

        if not self.task_control_client.wait_for_service(timeout_sec=2.0):
            return {"success": False, "message": "Service /task/control not available"}

        future = self.task_control_client.call_async(req)
        rclpy.spin_until_future_complete(self.node, future)

        try:
            response = future.result()
            return {
                "success": response.success,
                "message": response.message,
                "task_id": response.task_id,
                "status": response.status,
                "data_json": response.data_json
            }
        except Exception as e:
            return {"success": False, "message": f"Service call failed: {str(e)}"}

    def get_robot_status(self) -> dict:
        return self.call_task_control(
            action="get_status",
            reason="LLM status query",
            payload_json="{}"
        )

    def stop_robot(self, reason: str = "user requested emergency stop") -> dict:
        return self.call_task_control(
            action="stop",
            reason=reason,
            payload_json=json.dumps({"source": "llm"})
        )

    def cancel_task(self, reason: str = "user cancelled patrol") -> dict:
        return self.call_task_control(
            action="cancel",
            reason=reason,
            payload_json=json.dumps({"source": "llm"})
        )

    def reset_task(self, reason: str = "operator confirmed reset") -> dict:
        return self.call_task_control(
            action="reset",
            reason=reason,
            payload_json=json.dumps({"source": "llm"})
        )

    def start_patrol(self, route: List[str], user_text: str = "") -> dict:
        if self.task_request_publisher is None:
            return {"success": False, "message": "ROS2 node not initialized, cannot publish /task/request"}

        from icar_interfaces.msg import TaskRequest

        req = TaskRequest()
        req.task_type = "patrol"
        req.route = route
        req.params = json.dumps({
            "source": "llm",
            "user_text": user_text
        }, ensure_ascii=False)

        self.task_request_publisher.publish(req)

        return {
            "success": True,
            "message": f"Patrol task sent: {route}",
            "task_type": "patrol",
            "route": route
        }

    # ── 信息查询工具（读取节点缓存的最新数据）─────────────────

    def query_vision(self) -> dict:
        """查询最近的视觉检测结果。"""
        if self.node and hasattr(self.node, '_latest_detections'):
            data = self.node._latest_detections
            if data:
                return {"success": True, "message": "vision data", "data": data}
        return {"success": False, "message": "no vision data available", "data": {}}

    def query_navigation(self) -> dict:
        """查询当前导航状态。"""
        if self.node and hasattr(self.node, '_latest_nav_status'):
            data = self.node._latest_nav_status
            if data:
                return {"success": True, "message": "navigation status", "data": data}
        return {"success": False, "message": "no navigation data available", "data": {}}

    def check_safety(self) -> dict:
        """查询障碍物状态和安全风险。"""
        if self.node and hasattr(self.node, '_latest_obstacle'):
            data = self.node._latest_obstacle
            if data:
                return {"success": True, "message": "safety status", "data": data}
        return {"success": False, "message": "no obstacle data available", "data": {}}

    # ── 音频播放 ──────────────────────────────────────────────

    def play_audio(self, name: str = "beep", file_path: str = "",
                   volume: float = 1.0, blocking: bool = False) -> dict:
        """通过音箱播放音频文件（不依赖 ROS2）。"""
        if file_path:
            target = file_path
        elif name in AUDIO_REGISTRY:
            target = os.path.join(AUDIO_DIR, AUDIO_REGISTRY[name])
        else:
            return {
                "success": False,
                "message": f"Unknown audio name: '{name}'. "
                           f"Available: {list(AUDIO_REGISTRY.keys())}"
            }

        if not os.path.exists(target):
            return {"success": False, "message": f"Audio file not found: {target}"}

        sysname = platform.system()
        if sysname == "Linux":
            cmd = self._build_linux_play_cmd(target, volume)
        elif sysname == "Darwin":
            cmd = ["afplay", "-v", str(volume), target]
        else:
            return {"success": False, "message": f"Unsupported platform: {sysname}"}

        def _play():
            try:
                subprocess.run(cmd, check=True,
                               stdout=subprocess.DEVNULL,
                               stderr=subprocess.DEVNULL, timeout=120)
            except (subprocess.TimeoutExpired, Exception):
                pass

        if blocking:
            _play()
        else:
            threading.Thread(target=_play, daemon=True).start()

        return {
            "success": True,
            "message": f"Playing audio: {name} ({target})",
            "audio_name": name,
            "file_path": target,
            "volume": volume,
        }

    @staticmethod
    def _build_linux_play_cmd(target: str, volume: float) -> list:
        ext = os.path.splitext(target)[1].lower()
        if shutil.which("ffplay"):
            return ["ffplay", "-nodisp", "-autoexit",
                    "-volume", str(int(volume * 100)),
                    "-loglevel", "quiet", target]
        if ext == ".wav" and shutil.which("aplay"):
            return ["aplay", "-q", target]
        if shutil.which("paplay"):
            return ["paplay", "--volume", str(int(volume * 65536)), target]
        raise RuntimeError("No audio player found (tried ffplay, aplay, paplay)")

    TOOLS_DEF = [
        {
            "tool_name": "start_patrol",
            "description": "启动巡检任务，让小车按指定路线巡检",
            "parameters": {
                "route": {
                    "type": "array",
                    "items": {"type": "string"},
                    "required": True,
                    "description": "巡检点名称数组，如 ['A', 'B', 'C']"
                },
                "user_text": {
                    "type": "string",
                    "required": False,
                    "description": "原始用户输入文本"
                }
            }
        },
        {
            "tool_name": "get_robot_status",
            "description": "查询小车当前任务状态",
            "parameters": {}
        },
        {
            "tool_name": "stop_robot",
            "description": "立即停车，进入安全停止状态",
            "parameters": {
                "reason": {
                    "type": "string",
                    "required": False,
                    "description": "停车原因"
                }
            }
        },
        {
            "tool_name": "cancel_task",
            "description": "取消当前巡检任务并停车",
            "parameters": {
                "reason": {
                    "type": "string",
                    "required": False,
                    "description": "取消原因"
                }
            }
        },
        {
            "tool_name": "reset_task",
            "description": "复位任务状态，使小车可以接收新任务",
            "parameters": {
                "reason": {
                    "type": "string",
                    "required": False,
                    "description": "复位原因"
                }
            }
        },
        {
            "tool_name": "query_vision",
            "description": "查询最近的视觉检测结果（摄像头看到了什么目标）",
            "parameters": {}
        },
        {
            "tool_name": "query_navigation",
            "description": "查询当前导航状态、位置和进度",
            "parameters": {}
        },
        {
            "tool_name": "check_safety",
            "description": "查询障碍物状态和安全风险等级",
            "parameters": {}
        },
        {
            "tool_name": "play_audio",
            "description": "通过小车音箱播放音频。常用音频名称：welcome(欢迎)、start_patrol(开始巡检)、complete(完成)、alert(告警)、beep(提示音)、stop(停止)、danger(危险)、info(信息)、error(错误)、bye(再见)。也可指定自定义文件路径。",
            "parameters": {
                "name": {
                    "type": "string",
                    "required": False,
                    "description": "预定义音频名称：welcome/start_patrol/complete/alert/beep/stop/danger/info/error/bye"
                },
                "file_path": {
                    "type": "string",
                    "required": False,
                    "description": "自定义音频文件绝对路径（优先于 name）"
                },
                "volume": {
                    "type": "number",
                    "required": False,
                    "description": "音量 0.0-1.0，默认 1.0"
                }
            }
        }
    ]