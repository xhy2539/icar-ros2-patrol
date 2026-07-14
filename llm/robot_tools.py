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
import time
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
        self.tracking_command_publisher = None
        self.llm_motion_publisher = None
        self.buzzer_publisher = None
        self._motion_lock = threading.Lock()
        self._motion_cancel = None
        self._init_ros2()

    def _init_ros2(self):
        if self.node is None:
            return

        try:
            from icar_interfaces.srv import TaskControl
            from icar_interfaces.msg import TaskRequest
            from rclpy.qos import QoSProfile, ReliabilityPolicy
            from geometry_msgs.msg import Twist
            from std_msgs.msg import Bool, String

            qos = QoSProfile(depth=10, reliability=ReliabilityPolicy.RELIABLE)

            self.task_control_client = self.node.create_client(
                TaskControl, '/task/control'
            )

            self.task_request_publisher = self.node.create_publisher(
                TaskRequest, '/task/request', qos
            )

            self.tracking_command_publisher = self.node.create_publisher(
                String, '/vision/target_tracking/command', qos
            )
            self.llm_motion_publisher = self.node.create_publisher(
                Twist, '/cmd_vel_llm', qos
            )

            self.buzzer_publisher = self.node.create_publisher(
                Bool, '/Buzzer', qos
            )

            self.node.get_logger().info("Robot tools initialized")

        except ImportError as e:
            if self.node:
                self.node.get_logger().warn(f"icar_interfaces not available: {e}")

    def call_task_control(self, action: str, reason: str, payload_json: str = "{}") -> dict:
        if self.task_control_client is None:
            return {"success": False, "message": "ROS2 node not initialized, cannot call /task/control"}

        from icar_interfaces.srv import TaskControl

        req = TaskControl.Request()
        req.action = action
        req.reason = reason
        req.payload_json = payload_json

        if not self.task_control_client.wait_for_service(timeout_sec=2.0):
            return {"success": False, "message": "Service /task/control not available"}

        future = self.task_control_client.call_async(req)
        completed = threading.Event()
        future.add_done_callback(lambda _future: completed.set())
        if not completed.wait(timeout=3.0):
            return {"success": False, "message": "/task/control response timed out"}

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
        self._cancel_motion()
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

    def start_tracking(
        self, target_classes: Optional[List[str]] = None, user_text: str = ""
    ) -> dict:
        """Enable safe visual tracking through the tracker command topic."""
        if self.tracking_command_publisher is None:
            return {
                "success": False,
                "message": "ROS2 node not initialized, cannot start tracking",
            }
        from std_msgs.msg import String

        classes = [str(item) for item in (target_classes or ["person"]) if str(item)]
        message = String()
        message.data = json.dumps(
            {
                "action": "start",
                "target_classes": classes or ["person"],
                "source": "llm",
                "user_text": user_text,
            },
            ensure_ascii=False,
        )
        self.tracking_command_publisher.publish(message)
        return {
            "success": True,
            "message": f"Tracking started: {classes or ['person']}",
            "target_classes": classes or ["person"],
        }

    def stop_tracking(self, reason: str = "user stopped tracking") -> dict:
        """Disable visual tracking; the tracker publishes an immediate zero Twist."""
        if self.tracking_command_publisher is None:
            return {
                "success": False,
                "message": "ROS2 node not initialized, cannot stop tracking",
            }
        from std_msgs.msg import String

        message = String()
        message.data = json.dumps(
            {"action": "stop", "source": "llm", "reason": reason},
            ensure_ascii=False,
        )
        self.tracking_command_publisher.publish(message)
        return {"success": True, "message": f"Tracking stopped: {reason}"}

    def move_robot(
        self, direction: str, duration_sec: float = 0.0, speed: float = 0.2,
        distance_m: float = 0.0,
    ) -> dict:
        """Perform one short, low-speed movement via velocity_mux.

        Either duration_sec or distance_m can be specified. If distance_m is
        given, duration_sec is computed automatically from distance / speed.
        """
        if self.llm_motion_publisher is None:
            return {"success": False, "message": "ROS2 node not initialized, cannot move"}
        vectors = {
            "forward": (1.0, 0.0, 0.0),
            "backward": (-1.0, 0.0, 0.0),
            "left": (0.0, 1.0, 0.0),
            "right": (0.0, -1.0, 0.0),
            "turn_left": (0.0, 0.0, 1.0),
            "turn_right": (0.0, 0.0, -1.0),
        }
        direction = str(direction).strip().lower()
        if direction not in vectors:
            return {"success": False, "message": f"unsupported move direction: {direction}"}
        velocity = max(0.05, min(float(speed), 0.25))
        if float(distance_m) > 0.0:
            duration = max(0.2, min(float(distance_m) / velocity, 10.0))
        else:
            duration = max(0.2, min(float(duration_sec), 5.0))
        self._cancel_motion()
        cancelled = threading.Event()
        with self._motion_lock:
            self._motion_cancel = cancelled

        def publish_motion():
            from geometry_msgs.msg import Twist
            x, y, z = vectors[direction]
            until = time.monotonic() + duration
            while not cancelled.is_set() and time.monotonic() < until:
                message = Twist()
                message.linear.x = x * velocity
                message.linear.y = y * velocity
                message.angular.z = z * min(velocity * 4.0, 0.6)
                self.llm_motion_publisher.publish(message)
                time.sleep(0.1)
            self.llm_motion_publisher.publish(Twist())

        threading.Thread(target=publish_motion, daemon=True).start()
        return {
            "success": True,
            "message": f"moving {direction} for {duration:.1f}s at {velocity:.2f}",
            "direction": direction,
            "duration_sec": duration,
            "speed": velocity,
        }

    def _cancel_motion(self) -> None:
        with self._motion_lock:
            if self._motion_cancel is not None:
                self._motion_cancel.set()
                self._motion_cancel = None
        if self.llm_motion_publisher is not None:
            from geometry_msgs.msg import Twist
            self.llm_motion_publisher.publish(Twist())

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
        """查询障碍物和积水等最新安全风险。"""
        if self.node:
            obstacle = getattr(self.node, '_latest_obstacle', None)
            alarm = getattr(self.node, '_latest_safety_alarm', None)
            if obstacle or alarm:
                data = dict(obstacle or {})
                data["alarm"] = alarm or {}
                return {
                    "success": True,
                    "message": "safety status",
                    "data": data,
                }
        return {"success": False, "message": "no safety data available", "data": {}}

    # ── 音频播放 ──────────────────────────────────────────────

    @classmethod
    def list_available_audio(cls) -> List[str]:
        """列出所有可播放的音频名称（预定义 + 目录下自动发现的）。"""
        names = set(AUDIO_REGISTRY.keys())
        if os.path.isdir(AUDIO_DIR):
            for f in os.listdir(AUDIO_DIR):
                base, ext = os.path.splitext(f)
                if ext.lower() in ('.wav', '.mp3', '.m4a', '.opus', '.ogg', '.flac'):
                    names.add(base)
        return sorted(names)

    @classmethod
    def _resolve_audio_path(cls, name: str, file_path: str = "") -> str:
        """将 name 或 file_path 解析为文件绝对路径。返回空字符串表示找不到。"""
        if file_path:
            return file_path if os.path.exists(file_path) else ""

        # 1) 预定义注册表
        if name in AUDIO_REGISTRY:
            target = os.path.join(AUDIO_DIR, AUDIO_REGISTRY[name])
            if os.path.exists(target):
                return target

        # 2) 自动扫描 AUDIO_DIR 下的 name.* 文件（精确匹配）
        if os.path.isdir(AUDIO_DIR):
            for ext in ('.wav', '.mp3', '.m4a', '.opus', '.ogg', '.flac',
                        '.WAV', '.MP3', '.M4A'):
                target = os.path.join(AUDIO_DIR, name + ext)
                if os.path.exists(target):
                    return target

        # 3) 模糊匹配：name 是文件名的子串，或文件名是 name 的子串
        if os.path.isdir(AUDIO_DIR):
            for f in sorted(os.listdir(AUDIO_DIR)):
                base, ext = os.path.splitext(f)
                if ext.lower() in ('.wav', '.mp3', '.m4a', '.opus', '.ogg', '.flac'):
                    # 双向子串匹配
                    if name.lower() in base.lower() or base.lower() in name.lower():
                        return os.path.join(AUDIO_DIR, f)

        return ""

    def play_audio(self, name: str = "beep", file_path: str = "",
                   volume: float = 1.0, blocking: bool = False) -> dict:
        """通过音箱播放音频文件（不依赖 ROS2）。

        音频来源（按优先级）：
        1. file_path 直接指定文件路径
        2. name 匹配 AUDIO_REGISTRY 预定义名称
        3. name 匹配 audio/ 目录下的 .wav/.mp3 文件（自动发现）

        只需把 .wav/.mp3 文件放入 audio/ 目录，LLM 即可用文件名（不含扩展名）播放。
        """
        target = self._resolve_audio_path(name, file_path)

        if not target:
            if name in AUDIO_REGISTRY and self.buzzer_publisher is not None:
                return self._play_buzzer_fallback(name, blocking=blocking)
            available = self.list_available_audio()
            return {
                "success": False,
                "message": f"Audio not found: '{name}'. "
                           f"Available ({len(available)}): {available}"
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

        # 杀掉已有播放，保证同时只播一个
        self._stop_all_audio()

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

    def _play_buzzer_fallback(self, name: str, blocking: bool = False) -> dict:
        """Use the chassis buzzer when a predefined voice asset is absent."""
        from std_msgs.msg import Bool

        pulse_counts = {
            "danger": 3,
            "alert": 3,
            "error": 3,
            "stop": 2,
            "complete": 2,
        }
        count = pulse_counts.get(name, 1)

        def _play():
            try:
                for _ in range(count):
                    self.buzzer_publisher.publish(Bool(data=True))
                    time.sleep(0.16)
                    self.buzzer_publisher.publish(Bool(data=False))
                    time.sleep(0.12)
            finally:
                self.buzzer_publisher.publish(Bool(data=False))

        if blocking:
            _play()
        else:
            threading.Thread(target=_play, daemon=True).start()
        return {
            "success": True,
            "message": f"Playing buzzer fallback: {name}",
            "audio_name": name,
            "fallback": "chassis_buzzer",
        }

    @staticmethod
    def _stop_all_audio():
        """杀掉所有正在播放的 ffplay/afplay，保证同时只播一个。"""
        for proc_name in ("ffplay", "afplay", "aplay", "paplay"):
            try:
                subprocess.run(["pkill", "-9", proc_name],
                               stdout=subprocess.DEVNULL,
                               stderr=subprocess.DEVNULL, timeout=2)
            except Exception:
                pass

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

    # ── 网络音频搜索下载 ──────────────────────────────────────

    def download_audio(self, query: str = "", url: str = "", name: str = "",
                       blocking: bool = True) -> dict:
        """搜索并下载音频到 audio/ 目录。

        Parameters
        ----------
        query: YouTube 搜索关键词（如 "bird song"），YouTube 不通时无效。
        url:   直接下载 URL（B站/freesound/任意视频），优先于 query。
        name:  保存的文件名（不含扩展名）。
        blocking: 是否阻塞等待下载完成。
        """
        download_src = url.strip() if url else ""
        search_query = query.strip()

        if not download_src and not search_query:
            return {"success": False, "message": "query or url is required"}

        # yt-dlp 下载目标：URL直接下载，关键词走B站搜索（国内可用）
        if download_src:
            yt_input = download_src
        else:
            yt_input = f"bilisearch1:{search_query}"

        safe_name = name.strip() if name.strip() else (
            search_query if search_query else "downloaded")
        # 文件名只保留字母数字和常用字符
        import re
        safe_name = re.sub(r'[^a-zA-Z0-9一-鿿_-]', '_', safe_name)[:50]
        if not safe_name:
            safe_name = "downloaded"

        output_template = os.path.join(AUDIO_DIR, f"{safe_name}.%(ext)s")

        try:
            import yt_dlp
        except ImportError:
            return {"success": False,
                    "message": "yt-dlp not installed. Run: pip3 install yt-dlp"}

        ydl_opts = {
            'format': 'bestaudio/best',
            'outtmpl': output_template,
            'postprocessors': [{
                'key': 'FFmpegExtractAudio',
                'preferredcodec': 'mp3',
                'preferredquality': '128',
            }],
            'quiet': True,
            'no_warnings': True,
            'noplaylist': True,
            'max_downloads': 1,
            'socket_timeout': 15,
            'extractor_retries': 1,
            'fragment_retries': 1,
            'retries': 1,
            'http_headers': {
                'User-Agent': 'Mozilla/5.0 (X11; Linux aarch64) AppleWebKit/537.36',
                'Referer': 'https://www.bilibili.com/',
            },
        }

        def _download():
            try:
                with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                    ydl.download([yt_input])
            except Exception:
                pass  # 网络问题等，由结果文件是否存在来判断

        if blocking:
            _download()
        else:
            threading.Thread(target=_download, daemon=True).start()
            return {
                "success": True,
                "message": f"Download started: query='{query}', name='{safe_name}'",
                "name": safe_name,
                "query": query,
            }

        # 检查下载结果
        for ext in ('.mp3', '.wav', '.m4a', '.opus', '.webm'):
            target = os.path.join(AUDIO_DIR, safe_name + ext)
            if os.path.exists(target):
                size_kb = os.path.getsize(target) / 1024
                return {
                    "success": True,
                    "message": f"Downloaded: {safe_name}{ext} ({size_kb:.0f}KB)",
                    "name": safe_name,
                    "file_path": target,
                    "query": query,
                }

        # yt-dlp 可能给文件加了后缀（如 "name.f140.mp3"），扫描一下
        if os.path.isdir(AUDIO_DIR):
            prefix = safe_name + "."
            for f in sorted(os.listdir(AUDIO_DIR),
                            key=lambda x: os.path.getmtime(
                                os.path.join(AUDIO_DIR, x)), reverse=True):
                if f.startswith(prefix) or f.startswith(safe_name):
                    target = os.path.join(AUDIO_DIR, f)
                    if os.path.getsize(target) > 1000:  # >1KB, skip empty
                        return {
                            "success": True,
                            "message": f"Downloaded: {f} ({os.path.getsize(target)/1024:.0f}KB)",
                            "name": safe_name,
                            "file_path": target,
                            "query": query,
                        }

        return {
            "success": False,
            "message": f"Download failed: no audio file found for query='{query}'. "
                       f"Check internet or try a different query."
        }

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
            "description": "通过小车音箱播放音频。常用预定义名称：welcome(欢迎)、start_patrol(开始巡检)、complete(完成)、alert(告警)、beep(提示音)、stop(停止)、danger(危险)、info(信息)、error(错误)、bye(再见)。也可使用 audio/ 目录下任意音频文件名（不含扩展名），或通过 file_path 指定绝对路径。",
            "parameters": {
                "name": {
                    "type": "string",
                    "required": False,
                    "description": "音频名称。支持预定义名称，也支持 audio/ 目录下任意文件名（不含扩展名），如 bird、music。默认 beep。"
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
        },
        {
            "tool_name": "download_audio",
            "description": "从网络搜索或下载音频文件到 audio/ 目录。支持 YouTube 搜索(query)或直接 URL 下载(url,如B站/freesound)。下载后自动可用于 play_audio。",
            "parameters": {
                "query": {
                    "type": "string",
                    "required": False,
                    "description": "YouTube搜索关键词（YouTube不通时无效）"
                },
                "url": {
                    "type": "string",
                    "required": False,
                    "description": "直接下载URL（B站视频/freesound/任意音频链接），优先于query"
                },
                "name": {
                    "type": "string",
                    "required": False,
                    "description": "保存文件名（不含扩展名），默认由 query 生成"
                }
            }
        },
        {
            "tool_name": "start_tracking",
            "description": "启动视觉目标跟踪；默认跟踪 person，速度必须经过安全速度仲裁",
            "parameters": {
                "target_classes": {
                    "type": "array",
                    "items": {"type": "string"},
                    "required": False,
                    "description": "目标类别数组，默认 ['person']"
                },
                "user_text": {
                    "type": "string",
                    "required": False,
                    "description": "原始用户指令"
                }
            }
        },
        {
            "tool_name": "stop_tracking",
            "description": "停止视觉目标跟踪并输出零速度",
            "parameters": {
                "reason": {
                    "type": "string",
                    "required": False,
                    "description": "停止原因"
                }
            }
        }
    ]
