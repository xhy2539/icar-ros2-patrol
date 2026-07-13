#!/usr/bin/env python3
"""ROS2 LLM gateway — 增强版。

Services:
  - /llm/parse_task:     DeepSeek API 优先，规则兜底
                         (支持 patrol 任务 + info 信息查询)
  - /llm/generate_report: DeepSeek API 优先，模板兜底

Subscriptions (缓存最新值):
  - /task/log             → 日志缓存（用于报告）
  - /task/status          → 当前任务状态
  - /nav_status           → 导航进度
  - /obstacle_status      → 障碍物/安全
  - /vision/detections    → 视觉检测结果

安全约束：不发布 /cmd_vel，不绕过 task_manager_node。
"""

import json
import re
import threading
from collections import defaultdict

import rclpy
from rclpy.node import Node
from rclpy.qos import QoSProfile, ReliabilityPolicy

from icar_interfaces.msg import (
    TaskLog, TaskStatus, NavStatus, ObstacleStatus,
    DetectionArray,
)
from icar_interfaces.srv import GenerateReport, ParseTask

from .complex_task import ComplexTaskRunner, PlanStep
from .tool_intent import is_reset_confirmation, parse_tool_intent

# ---------------------------------------------------------------------------
# 可选依赖 — RobotTools（工具调用模式）
# ---------------------------------------------------------------------------
_RobotTools = None
_ROBOT_TOOLS_AVAILABLE = False

try:
    import sys as _sys
    import os as _os
    # 从安装空间反查源空间: install/llm_gateway/... -> src/llm/
    _here = _os.path.realpath(__file__)
    _src_llm = ""
    _d = _os.path.dirname(_here)
    while _d and _d != "/":
        _candidate = _os.path.join(_d, "src", "llm")
        if _os.path.isdir(_candidate):
            _src_llm = _candidate
            break
        _d = _os.path.dirname(_d)
    if _src_llm and _src_llm not in _sys.path:
        _sys.path.insert(0, _src_llm)
    from robot_tools import RobotTools as _RT
    _RobotTools = _RT
    _ROBOT_TOOLS_AVAILABLE = True
    # 同时导入独立 deepseek_client（供 parse_tool_call 使用）
    try:
        from deepseek_client import DeepSeekClient as _ToolClient
        _TOOL_CLIENT_AVAILABLE = True
    except Exception:
        _ToolClient = None
        _TOOL_CLIENT_AVAILABLE = False
except Exception:
    pass

# ---------------------------------------------------------------------------
# 可选依赖 — DeepSeek
# ---------------------------------------------------------------------------
_DEEPSEEK_AVAILABLE = False
DeepSeekClient = None
extract_json_from_response = None

try:
    from .deepseek_client import DeepSeekClient as _DeepSeekClient
    DeepSeekClient = _DeepSeekClient
    _DEEPSEEK_AVAILABLE = True
except ImportError:
    pass

try:
    from .json_protocol import extract_json_from_response as _extract
    extract_json_from_response = _extract
except ImportError:
    pass

if extract_json_from_response is None:
    def extract_json_from_response(text: str) -> str:
        start = text.find("{")
        end = text.rfind("}") + 1
        if start == -1 or end == 0:
            raise ValueError("No JSON found in response")
        return text[start:end]


# ---------------------------------------------------------------------------
# 常量
# ---------------------------------------------------------------------------
DEFAULT_ACTIONS = ["navigate", "avoid_obstacle", "detect_object", "collect_sensor"]
ALLOWED_ACTIONS = set(DEFAULT_ACTIONS)
KNOWN_POINTS = ("A", "B", "C", "D", "E", "F")

# 信息查询关键词（用于规则检测）
INFO_KEYWORDS = {
    "vision": ("看到", "摄像头", "检测到", "画面", "有没有人",
               "前面有", "有什么"),
    "navigation": ("在哪", "位置", "到了吗", "导航", "还有多远",
                   "到哪", "哪个点", "多远"),
    "safety": ("安全吗", "障碍物", "有障碍", "挡住", "危险", "会不会撞"),
    "status": ("状态", "进度", "任务", "在做什么", "完成", "怎么样"),
}


# ---------------------------------------------------------------------------
# 节点
# ---------------------------------------------------------------------------
class LlmGatewayNode(Node):
    def __init__(self):
        super().__init__("llm_gateway_node")

        # 参数
        self.declare_parameter("provider", "auto")
        self.declare_parameter("default_route", ["A", "B", "C"])
        self.declare_parameter("max_logs_per_task", 200)
        self.declare_parameter("tool_mode", False)

        self._provider_cfg = str(self.get_parameter("provider").value)
        self.default_route = list(self.get_parameter("default_route").value)
        self.max_logs_per_task = int(self.get_parameter("max_logs_per_task").value)
        self._tool_mode = bool(self.get_parameter("tool_mode").value)

        # DeepSeek 客户端（延迟初始化）
        self._client = None
        self._api_ok = False

        # RobotTools（工具调用模式）
        self._robot_tools = None
        if self._tool_mode:
            if _ROBOT_TOOLS_AVAILABLE:
                self._robot_tools = _RobotTools(self)
                self.get_logger().info("RobotTools loaded for tool_mode")
            else:
                self.get_logger().warn("tool_mode=true but RobotTools import failed")

        # ── 数据缓存 ──
        self.logs_by_task = defaultdict(list)

        self._latest_task_status = None
        self._latest_nav_status = None
        self._latest_obstacle = None
        self._latest_detections = None
        self._plan_runner = ComplexTaskRunner()
        self._plan_lock = threading.RLock()
        self._plan_context = {}

        # ── QoS ──
        reliable_qos = QoSProfile(depth=50, reliability=ReliabilityPolicy.RELIABLE)
        best_effort_qos = QoSProfile(depth=10, reliability=ReliabilityPolicy.BEST_EFFORT)

        # ── 订阅 ──
        self.task_log_sub = self.create_subscription(
            TaskLog, "/task/log", self._on_task_log, reliable_qos)

        self.task_status_sub = self.create_subscription(
            TaskStatus, "/task/status", self._on_task_status, reliable_qos)

        self.nav_status_sub = self.create_subscription(
            NavStatus, "/nav_status", self._on_nav_status, reliable_qos)

        self.obstacle_sub = self.create_subscription(
            ObstacleStatus, "/obstacle_status", self._on_obstacle_status, reliable_qos)

        self.vision_sub = self.create_subscription(
            DetectionArray, "/vision/detections", self._on_detections, best_effort_qos)

        # ── 服务 ──
        self.parse_srv = self.create_service(
            ParseTask, "/llm/parse_task", self._on_parse_task)
        self.report_srv = self.create_service(
            GenerateReport, "/llm/generate_report", self._on_generate_report)

        # ── 工具调用（可选）──────────────────────────────────────
        self._tool_sub = None
        self._response_pub = None
        if self._tool_mode:
            from std_msgs.msg import String
            self._tool_sub = self.create_subscription(
                String, "/llm/user_command", self._on_tool_command, reliable_qos)
            self._response_pub = self.create_publisher(
                String, "/llm/response", reliable_qos)

        # 启动信息
        effective = self._resolve_provider()
        extra = []
        if self._tool_mode:
            extra.append("tool_mode=on")
        self.get_logger().info(
            f"llm_gateway_node ready, provider={effective}, "
            f"api_available={self._api_ok}, "
            f"services=[/llm/parse_task, /llm/generate_report], "
            f"subscriptions=5 topics"
            + (", tool_mode=on, /llm/user_command" if self._tool_mode else "")
        )

    # ── provider 决策 ──────────────────────────────────────────

    def _resolve_provider(self) -> str:
        if self._provider_cfg == "rule":
            return "rule"
        if self._provider_cfg == "deepseek":
            self._ensure_client()
            if self._api_ok:
                return "deepseek"
            self.get_logger().warn(
                "provider=deepseek but API unavailable, falling back to rule")
            return "rule"
        self._ensure_client()
        if self._api_ok:
            return "deepseek"
        return "rule"

    def _ensure_client(self):
        if self._client is not None:
            return
        if not _DEEPSEEK_AVAILABLE:
            self._api_ok = False
            return
        try:
            self._client = DeepSeekClient()
            self._api_ok = self._client.available
        except Exception:
            self._api_ok = False

    @property
    def _use_api(self) -> bool:
        return self._api_ok and self._client is not None \
            and self._resolve_provider() == "deepseek"

    # ═══════════════════════════════════════════════════════════
    # Topic 回调：缓存最新值
    # ═══════════════════════════════════════════════════════════

    def _on_task_log(self, msg: TaskLog):
        record = {
            "task_id": msg.task_id,
            "timestamp": {"sec": msg.timestamp.sec, "nanosec": msg.timestamp.nanosec},
            "event_type": msg.event_type,
            "severity": msg.severity,
            "data": self._loads_json(msg.data_json),
        }
        bucket = self.logs_by_task[msg.task_id]
        bucket.append(record)
        if len(bucket) > self.max_logs_per_task:
            del bucket[: len(bucket) - self.max_logs_per_task]

        # 持久化到 JSONL 文件
        try:
            import os as _os
            _log_dir = "/home/jetson/icar-ros2-patrol/logs"
            _os.makedirs(_log_dir, exist_ok=True)
            _log_file = _os.path.join(_log_dir, f"{msg.task_id}.jsonl")
            with open(_log_file, "a") as _f:
                _f.write(json.dumps(record, ensure_ascii=False) + "\n")
        except Exception:
            pass

    def _on_task_status(self, msg: TaskStatus):
        self._latest_task_status = {
            "task_id": msg.task_id,
            "status": msg.status,
            "current_step": msg.current_step,
            "total_steps": msg.total_steps,
            "message": msg.message,
        }
        with self._plan_lock:
            was_active = self._plan_runner.active
            next_step = self._plan_runner.on_task_status(msg.status)
            snapshot = self._plan_runner.snapshot()
        if next_step is not None or (
            was_active and snapshot["status"] in {"COMPLETED", "FAILED"}
        ):
            threading.Thread(
                target=self._resume_complex_plan,
                args=(next_step,),
                daemon=True,
            ).start()

    def _on_nav_status(self, msg: NavStatus):
        self._latest_nav_status = {
            "status": msg.status,
            "progress": round(msg.progress, 3) if hasattr(msg, 'progress') else 0.0,
            "distance_remain": round(msg.distance_remain, 2),
            "message": msg.message,
        }

    def _on_obstacle_status(self, msg: ObstacleStatus):
        self._latest_obstacle = {
            "is_obstacle": msg.is_obstacle,
            "min_distance": round(msg.min_distance, 2),
            "direction": msg.direction,
            "risk_level": msg.risk_level,
            "action": msg.action,
        }

    def _on_detections(self, msg: DetectionArray):
        dets = []
        for d in msg.detections:
            dets.append({
                "class_name": d.class_name,
                "confidence": round(d.confidence, 3),
                "bbox": [d.x_min, d.y_min, d.x_max, d.y_max],
                "image_path": d.image_path,
            })
        self._latest_detections = dets

    # ═══════════════════════════════════════════════════════════
    # /llm/parse_task
    # ═══════════════════════════════════════════════════════════

    def _on_parse_task(self, request, response):
        text = request.input_text.strip()
        if not text:
            response.task_json = "{}"
            response.success = False
            response.error_msg = "input_text is empty"
            return response

        task = None
        used_provider = "rule"

        # 尝试 DeepSeek API
        if self._use_api:
            task = self._parse_via_api(text)

        # 如果 API 返回了 info 类型，走回答流程
        if task is not None and task.get("task_type") == "info":
            used_provider = "deepseek"
            answer = self._answer_info_query(
                task.get("question", text),
                task.get("query_type", "all"),
            )
            task["answer"] = answer
        elif task is not None and task.get("task_type") == "patrol":
            used_provider = "deepseek"
        else:
            # API 失败或无结果，回退到规则
            if task is None:
                task = self._parse_task_by_rule(text)  # 默认 patrol

        task.setdefault("params", {})
        task["params"]["provider"] = used_provider

        response.task_json = json.dumps(task, ensure_ascii=False)
        response.success = True
        response.error_msg = ""
        self.get_logger().info(
            f"parse_task (provider={used_provider}): '{text[:60]}' "
            f"-> type={task.get('task_type')}, "
            f"route={task.get('route')}, "
            f"query_type={task.get('query_type', '-')}"
        )
        return response

    def _parse_via_api(self, text: str):
        """调用 DeepSeek 解析，成功返回 dict，失败返回 None。"""
        try:
            raw = self._client.parse_patrol_task(text)
            if raw is None:
                return None
            json_str = extract_json_from_response(raw)
            result = json.loads(json_str)
            if "task_type" not in result:
                self.get_logger().warn(
                    f"API returned unexpected format: {json_str[:100]}")
                return None
            return result
        except Exception as e:
            self.get_logger().warn(
                f"DeepSeek parse failed, falling back to rule: {e}")
            return None

    # ── 信息查询回答 ───────────────────────────────────────────

    def _answer_info_query(self, question: str, query_type: str) -> str:
        """使用 DeepSeek + 缓存数据回答用户的信息查询。"""
        context = self._build_context()

        if self._use_api:
            try:
                answer = self._client.answer_query(question, context)
                if answer:
                    return answer
            except Exception as e:
                self.get_logger().warn(f"DeepSeek answer_query failed: {e}")

        # 回退：规则生成简短回答
        return self._rule_answer(question, query_type, context)

    def _build_context(self) -> dict:
        """从缓存数据构建上下文 dict，供 DeepSeek 使用。"""
        return {
            "task_status": self._latest_task_status or {},
            "nav_status": self._latest_nav_status or {},
            "obstacle_status": self._latest_obstacle or {},
            "detections": self._latest_detections or [],
        }

    def _rule_answer(self, question: str, query_type: str,
                     context: dict) -> str:
        """规则模板：当 DeepSeek 不可用时生成简短回答。"""
        parts = []

        if query_type in ("vision", "all"):
            detections = context.get("detections", [])
            if detections:
                names = [self._translate_class(d["class_name"]) for d in detections]
                parts.append(f"最近检测到: {'、'.join(names)}")
            elif query_type == "vision":
                parts.append("视觉模块暂无检测数据")

        if query_type in ("navigation", "all"):
            nav = context.get("nav_status", {})
            if nav:
                parts.append(
                    f"导航状态: {self._translate_status(nav.get('status', '?'))}，"
                    f"剩余距离 {nav.get('distance_remain', '?')}m — "
                    f"{nav.get('message', '')}"
                )
            else:
                parts.append("导航模块暂无数据")

        if query_type in ("safety", "all"):
            obs = context.get("obstacle_status", {})
            if obs:
                if obs.get("is_obstacle"):
                    parts.append(
                        f"⚠ 检测到障碍物，距离 {obs.get('min_distance', '?')}m，"
                        f"方位 {self._translate_status(obs.get('direction', '?'))}，"
                        f"风险等级: {self._translate_status(obs.get('risk_level', '?'))}"
                    )
                else:
                    parts.append("前方安全，未检测到障碍物")
            elif query_type == "safety":
                parts.append("障碍物检测暂无数据")

        if query_type in ("status", "all"):
            ts = context.get("task_status", {})
            if ts:
                parts.append(
                    f"任务状态: {self._translate_status(ts.get('status', '?'))}，"
                    f"步骤 {ts.get('current_step', 0)}/{ts.get('total_steps', 0)}"
                )
            elif query_type == "status":
                parts.append("任务状态暂无数据")

        return "\n".join(parts) if parts else f"关于「{question}」，暂无相关数据。"

    # ═══════════════════════════════════════════════════════════
    # 规则解析：patrol 任务（与旧版兼容，作为 DeepSeek 兜底）
    # ═══════════════════════════════════════════════════════════

    def _parse_task_by_rule(self, text):
        """规则解析：返回 patrol 或 info 任务 JSON。"""
        # 检测是否为信息查询
        info_type = self._detect_info_query(text)
        if info_type:
            return {
                "task_type": "info",
                "query_type": info_type,
                "question": text,
                "params": {"source": "llm_gateway", "raw_text": text},
            }

        # 巡检任务
        route = self._extract_route(text) or self.default_route
        actions = self._extract_actions(text)
        safety_rule = self._extract_safety_rule(text)
        params = {"source": "llm_gateway", "raw_text": text}
        if "语音" in text or "说" in text:
            params["input_mode"] = "voice"

        return {
            "task_type": "patrol",
            "route": route,
            "actions": actions,
            "safety_rule": safety_rule,
            "params": params,
        }

    def _detect_info_query(self, text: str) -> str:
        """检测是否为信息查询，返回 query_type 或空字符串。"""
        # 如果包含明确的巡检/行动指令，不是查询
        action_words = ("巡检", "巡逻", "去", "前往", "走一圈", "出发",
                        "启动", "开始", "停下", "停止", "取消", "复位")
        if any(w in text for w in action_words):
            return ""

        # 匹配信息查询关键词
        scores = {}
        for qtype, keywords in INFO_KEYWORDS.items():
            score = sum(1 for kw in keywords if kw in text)
            if score > 0:
                scores[qtype] = score

        if not scores:
            if text.endswith("？") or text.endswith("?") or \
               any(w in text for w in ("什么", "怎么", "多少", "吗", "呢", "哪")):
                return "all"
            return ""

        # 多领域查询 → all
        if len(scores) > 1:
            return "all"
        return max(scores, key=scores.get)

    def _extract_route(self, text):
        route = []
        upper_text = text.upper()
        for point in KNOWN_POINTS:
            patterns = (
                rf"(?<![A-Z]){point}(?![A-Z])",
                rf"{point}\s*点",
                rf"点\s*{point}",
            )
            if any(re.search(pattern, upper_text) for pattern in patterns):
                route.append(point)
        if route:
            return route
        cn_points = {"一": "A", "二": "B", "三": "C",
                     "四": "D", "五": "E", "六": "F"}
        for key, value in cn_points.items():
            if f"{key}号" in text or f"{key}点" in text:
                route.append(value)
        return route

    def _extract_actions(self, text):
        actions = ["navigate", "avoid_obstacle"]
        keyword_map = {
            "detect_object": ("检测", "识别", "目标", "视觉", "拍照"),
            "collect_sensor": ("采集", "传感器", "温度", "湿度", "烟雾", "环境"),
        }
        for action, keywords in keyword_map.items():
            if any(keyword in text for keyword in keywords):
                actions.append(action)
        if "巡检" in text or "一圈" in text:
            actions = DEFAULT_ACTIONS.copy()
        return [action for action in actions if action in ALLOWED_ACTIONS]

    @staticmethod
    def _extract_safety_rule(text):
        rules = []
        if "障碍" in text or "避障" in text:
            rules.append("遇到障碍物停止并等待处理")
        if "烟雾" in text or "报警" in text or "异常" in text:
            rules.append("检测到环境异常时停止并报警")
        if "停止" in text or "刹车" in text:
            rules.append("收到停止指令立即停止")
        return "；".join(rules) if rules else "遵循 task_manager 安全白名单"

    # ═══════════════════════════════════════════════════════════
    # /llm/generate_report
    # ═══════════════════════════════════════════════════════════

    def _on_generate_report(self, request, response):
        logs = []
        if request.logs_json.strip():
            parsed = self._loads_json(request.logs_json)
            if isinstance(parsed, list):
                logs = parsed
            elif isinstance(parsed, dict):
                logs = parsed.get("logs", [])
        elif request.task_id:
            logs = list(self.logs_by_task.get(request.task_id, []))
            # 内存没有则从历史文件加载
            if not logs:
                try:
                    import os as _os
                    _log_file = _os.path.join("/home/jetson/icar-ros2-patrol/logs",
                                               f"{request.task_id}.jsonl")
                    if _os.path.exists(_log_file):
                        with open(_log_file, "r") as _f:
                            for line in _f:
                                line = line.strip()
                                if line:
                                    logs.append(json.loads(line))
                except Exception:
                    pass

        if not logs:
            response.report_text = ""
            response.success = False
            response.error_msg = "no logs available"
            return response

        used_provider = "template"
        report_text = None

        if self._use_api:
            report_text = self._report_via_api(request.task_id, logs)
            if report_text is not None:
                used_provider = "deepseek"

        if report_text is None:
            report_text = self._build_report(request.task_id, logs)

        response.report_text = report_text
        response.success = True
        response.error_msg = ""
        self.get_logger().info(
            f"generate_report (provider={used_provider}): "
            f"task_id={request.task_id}, logs={len(logs)}"
        )
        return response

    def _report_via_api(self, task_id, logs):
        try:
            log_lines = []
            for record in logs:
                ts = record.get("timestamp", {})
                sec = ts.get("sec", 0)
                log_lines.append(
                    f"[{sec}] {record.get('event_type','?')} "
                    f"severity={record.get('severity','INFO')} "
                    f"data={json.dumps(record.get('data',{}), ensure_ascii=False)}"
                )
            log_text = "\n".join(log_lines)
            return self._client.generate_report(log_text)
        except Exception as e:
            self.get_logger().warn(
                f"DeepSeek report failed, falling back to template: {e}")
            return None

    # ── 模板报告生成 ───────────────────────────────────────────

    def _build_report(self, task_id, logs):
        checkpoints = []
        detections_per_point = {}     # {checkpoint: [class_names]}
        warnings = []
        errors = []
        current_point = "?"
        event_count = 0
        start_time = ""
        end_time = ""

        for record in logs:
            event_count += 1
            event_type = str(record.get("event_type", ""))
            severity = str(record.get("severity", "INFO"))
            data = record.get("data", {})
            if isinstance(data, str):
                data = self._loads_json(data)
            ts = record.get("timestamp", {})
            sec = ts.get("sec", 0)

            if event_type == "TASK_START" and not start_time:
                start_time = self._fmt_time(sec)
            if event_type in ("TASK_END", "COMPLETED") and not end_time:
                end_time = self._fmt_time(sec)

            if event_type in ("CHECKPOINT_REACHED", "NAV_END"):
                checkpoint = data.get("checkpoint") or data.get("target")
                if checkpoint:
                    cp = str(checkpoint)
                    checkpoints.append(cp)
                    current_point = cp
                    if cp not in detections_per_point:
                        detections_per_point[cp] = []
            if event_type == "VISION_DETECT":
                for det in data.get("detections", []):
                    name = det.get("class") or det.get("class_name") or "unknown"
                    name_cn = self._translate_class(name)
                    detections_per_point.setdefault(current_point, []).append(name_cn)
                    detections.append(name_cn)
            if event_type == "ANOMALY" or severity == "WARN":
                warnings.append(data)
            if severity == "ERROR":
                errors.append(data)

        # ── 构建护工友好报告 ──
        lines = []
        lines.append("══════════════════════════════════")
        lines.append("      巡 检 交 班 报 告")
        lines.append("══════════════════════════════════")
        lines.append("")

        # 时间
        if start_time:
            lines.append(f"巡检时间: {start_time}")
            if end_time:
                lines.append(f"结束时间: {end_time}")
            lines.append("")

        # 一句话总结
        has_problem = bool(errors) or bool(warnings)
        if errors:
            lines.append("【结论】本次巡检发现严重问题，需要立即处理！")
        elif warnings:
            lines.append("【结论】巡检基本正常，有少量注意事项。")
        else:
            lines.append("【结论】一切正常，无需额外处理。")
        lines.append("")

        # 巡视区域
        if checkpoints:
            lines.append(f"巡视区域（共{len(checkpoints)}处）: {' → '.join(checkpoints)}")
            lines.append("")

        # 各点详情
        for cp in checkpoints:
            lines.append(f"  {cp}点:")
            dets = detections_per_point.get(cp, [])
            if dets:
                lines.append(f"    看到: {'、'.join(dets)}")
            else:
                lines.append(f"    未见异常")
            lines.append("")

        # 注意事项
        if warnings:
            lines.append("【需要注意】")
            for w in warnings:
                wtype = w.get("type", "")
                if "obstacle" in str(w) or "障碍" in str(w):
                    lines.append(f"  - 走廊有障碍物，建议清理通道")
                elif "water" in str(w) or "积水" in str(w):
                    lines.append(f"  - 地面有积水，注意防滑，建议放置警示牌")
                else:
                    msg = w.get("message", str(w)[:80])
                    lines.append(f"  - {msg}")
            lines.append("")

        if errors:
            lines.append("【需要立即处理】")
            for e in errors:
                lines.append(f"  ⚠️ {e.get('message', str(e)[:100])}")
            lines.append("")

        # 交接建议
        lines.append("【交接建议】")
        if errors:
            lines.append("  请接班同事优先处理以上紧急事项。")
        elif warnings:
            lines.append("  请接班同事留意以上注意事项，其余正常。")
        else:
            lines.append("  一切正常，按常规流程接班即可。")
        lines.append("")
        lines.append(f"（本报告由智能巡检系统自动生成，共记录{event_count}条事件）")

        return "\n".join(lines)

    # ═══════════════════════════════════════════════════════════
    # 工具方法
    # ═══════════════════════════════════════════════════════════

    @staticmethod
    def _fmt_time(sec: int) -> str:
        """将 Unix 时间戳转为可读时间字符串。"""
        import datetime
        try:
            return datetime.datetime.fromtimestamp(sec).strftime("%Y-%m-%d %H:%M:%S")
        except (OSError, ValueError):
            return str(sec)

    @staticmethod
    def _translate_status(value: str) -> str:
        """将英文枚举值转成护工能看懂的中文。"""
        mapping = {
            # 任务状态
            "PENDING": "等待任务",
            "RUNNING": "任务已启动",
            "NAVIGATING": "正在导航",
            "CHECKPOINT": "已到达巡检点",
            "DETECTING": "正在视觉检测",
            "COLLECTING": "正在采集数据",
            "COMPLETED": "任务完成",
            "FAILED": "任务失败",
            "CANCELLED": "任务已取消",
            # 导航状态
            "IDLE": "空闲",
            "ARRIVED": "已到达",
            # 风险等级
            "safe": "安全",
            "warning": "注意",
            "danger": "危险",
            # 障碍物方位
            "front": "前方",
            "left": "左侧",
            "right": "右侧",
            "back": "后方",
            # 建议动作
            "none": "无需操作",
            "slow_down": "减速慢行",
            "stop": "立即停止",
            "turn": "转向避让",
        }
        return mapping.get(str(value), str(value))

    @staticmethod
    def _translate_class(name: str) -> str:
        """将英文类别名转成护工能看懂的中文。"""
        mapping = {
            "person": "行人",
            "people": "行人",
            "obstacle": "障碍物",
            "water": "积水",
            "puddle": "积水",
            "sign": "标识牌",
            "vehicle": "车辆",
            "traffic_light": "信号灯",
            "fallen_person": "跌倒的人（紧急！）",
            "fire": "火焰（紧急！）",
            "unknown": "未识别物体",
        }
        return mapping.get(name.lower(), name)

    @staticmethod
    def _infer_task_id(logs):
        for record in logs:
            task_id = record.get("task_id")
            if task_id:
                return str(task_id)
        return "unknown"

    @staticmethod
    def _loads_json(text):
        if isinstance(text, (dict, list)):
            return text
        if not text:
            return {}
        try:
            return json.loads(text)
        except json.JSONDecodeError:
            return {"raw": text}

    # ═══════════════════════════════════════════════════════════
    # 工具调用（tool_mode）
    # ═══════════════════════════════════════════════════════════

    def _on_tool_command(self, msg):
        """处理 /llm/user_command 消息，执行工具并发布到 /llm/response。"""
        # Cloud inference and task-control services may block.  A worker keeps
        # the ROS executor free to receive status and service responses.
        threading.Thread(
            target=self._process_tool_command,
            args=(msg.data,),
            daemon=True,
        ).start()

    def _process_tool_command(self, raw_command: str):
        request_id = ""
        source = "ros"
        user_input = raw_command.strip()
        if user_input.startswith("{"):
            try:
                envelope = json.loads(user_input)
                if isinstance(envelope, dict) and "input_text" in envelope:
                    request_id = str(envelope.get("request_id", ""))
                    source = str(envelope.get("source", "ros"))
                    user_input = str(envelope.get("input_text", "")).strip()
            except json.JSONDecodeError:
                pass
        if not user_input:
            return

        context = {
            "request_id": request_id,
            "input_text": user_input,
            "source": source,
        }
        self.get_logger().info(f"Tool command: {user_input[:60]}")
        try:
            result = self._execute_tool(user_input, context=context)
            self.get_logger().info(
                f"Tool result: {result.get('tool_name','?')} "
                f"success={result.get('success')} "
                f"msg={str(result.get('message',''))[:80]}"
            )
        except Exception as _exc:
            self.get_logger().error(f"Tool execution exception: {_exc}")
            result = {"success": False, "tool_name": "?", "message": str(_exc)}

        self._publish_tool_result(result, context)

    def _publish_tool_result(self, result: dict, context: dict) -> None:
        result = dict(result)
        result.setdefault("reply", self._tool_reply(result))
        result.update(context)

        if self._response_pub:
            from std_msgs.msg import String
            resp = String()
            resp.data = json.dumps(result, ensure_ascii=False)
            self._response_pub.publish(resp)

    def _execute_tool(self, user_input: str, context=None) -> dict:
        """LLM 解析 → 工具执行。"""
        if self._robot_tools is None:
            return {"success": False, "message": "tool_mode requires robot_tools"}

        # Deterministic commands are both the offline fallback and the fast path
        # for safety-critical intents such as emergency stop.
        tool_call = parse_tool_intent(user_input, self.default_route)
        provider = "rule"

        if tool_call is None and _TOOL_CLIENT_AVAILABLE and _ToolClient is not None:
            try:
                tool_client = _ToolClient()
                if not tool_client.available:
                    return {"success": False, "message": "无法识别该指令，且 LLM API 未配置"}
                self.get_logger().info("Calling DeepSeek parse_tool_call...")
                raw = tool_client.parse_tool_call(user_input)
                if raw:
                    json_str = extract_json_from_response(raw)
                    tool_call = json.loads(json_str)
                    provider = "deepseek"
                else:
                    return {"success": False, "message": "Tool API returned empty"}
            except Exception as e:
                return {"success": False, "message": f"Tool parse error: {e}"}
        elif tool_call is None and self._use_api and self._client is not None:
            try:
                raw = self._client.parse_tool_call(user_input)
                if raw is None:
                    return {"success": False, "message": "API unavailable"}
                json_str = extract_json_from_response(raw)
                tool_call = json.loads(json_str)
                provider = "deepseek"
            except Exception as e:
                return {"success": False, "message": f"Tool parse error: {e}"}
        elif tool_call is None:
            return {"success": False, "message": "无法识别该指令，请换一种更明确的说法"}

        tool_name = tool_call.get("tool_name", "")
        arguments = tool_call.get("arguments", {})
        if not isinstance(arguments, dict):
            return {
                "success": False,
                "tool_name": tool_name,
                "message": "tool arguments must be an object",
                "provider": provider,
            }

        if tool_name == "reset_task" and not is_reset_confirmation(user_input):
            return {
                "success": False,
                "tool_name": tool_name,
                "message": "解除急停需要明确说“确认复位”",
                "provider": provider,
            }

        if tool_name == "execute_plan":
            return self._start_complex_plan(
                arguments.get("steps", []),
                context=context or {},
                provider=provider,
            )

        result = self._execute_named_tool(tool_name, arguments)
        result["provider"] = provider
        return result

    def _execute_named_tool(self, tool_name: str, arguments: dict) -> dict:
        tool_map = {
            "start_patrol":       self._tool_start_patrol,
            "get_robot_status":   self._tool_get_status,
            "stop_robot":         self._tool_stop_robot,
            "cancel_task":        self._tool_cancel_task,
            "reset_task":         self._tool_reset_task,
            "query_vision":       self._tool_query_vision,
            "query_navigation":   self._tool_query_navigation,
            "check_safety":       self._tool_check_safety,
            "play_audio":         self._tool_play_audio,
            "download_audio":     self._tool_download_audio,
            "start_tracking":     self._tool_start_tracking,
            "stop_tracking":      self._tool_stop_tracking,
        }

        if tool_name not in tool_map:
            return {"success": False, "tool_name": tool_name,
                    "message": f"Unknown tool: {tool_name}"}

        try:
            result = tool_map[tool_name](**arguments)
            result["tool_name"] = tool_name
            return result
        except Exception as e:
            return {"success": False, "tool_name": tool_name,
                    "message": f"Tool execution failed: {e}"}

    def _start_complex_plan(self, raw_steps, context: dict, provider: str) -> dict:
        try:
            with self._plan_lock:
                first_step = self._plan_runner.start(raw_steps)
                self._plan_context = dict(context)
        except ValueError as exc:
            return {
                "success": False,
                "tool_name": "execute_plan",
                "provider": provider,
                "message": str(exc),
            }

        result = self._run_plan_steps(first_step)
        result["provider"] = provider
        return result

    def _run_plan_steps(self, step: PlanStep) -> dict:
        executed = []
        next_step = step
        while next_step is not None:
            step_result = self._execute_named_tool(
                next_step.tool_name,
                next_step.arguments,
            )
            executed.append({
                "tool_name": next_step.tool_name,
                "success": bool(step_result.get("success")),
                "message": str(step_result.get("message", "")),
            })
            with self._plan_lock:
                next_step = self._plan_runner.record_result(
                    bool(step_result.get("success")),
                    str(step_result.get("message", "")),
                )
                snapshot = self._plan_runner.snapshot()

        success = snapshot["status"] not in {"FAILED"}
        messages = {
            "WAITING": "复杂任务已启动，正在等待巡检完成后接续下一步",
            "COMPLETED": "复杂任务的全部步骤已执行完成",
            "FAILED": f"复杂任务执行失败：{snapshot['error']}",
        }
        return {
            "success": success,
            "tool_name": "execute_plan",
            "message": messages.get(snapshot["status"], "复杂任务正在执行"),
            "plan": snapshot,
            "executed": executed,
        }

    def _resume_complex_plan(self, next_step) -> None:
        if next_step is not None:
            result = self._run_plan_steps(next_step)
        else:
            with self._plan_lock:
                snapshot = self._plan_runner.snapshot()
            result = {
                "success": snapshot["status"] == "COMPLETED",
                "tool_name": "execute_plan",
                "message": (
                    "复杂任务的全部步骤已执行完成"
                    if snapshot["status"] == "COMPLETED"
                    else f"复杂任务执行失败：{snapshot['error']}"
                ),
                "plan": snapshot,
                "executed": [],
            }
        with self._plan_lock:
            context = dict(self._plan_context)
        self._publish_tool_result(result, context)

    def _tool_get_status(self) -> dict:
        if self._latest_task_status:
            return {"success": True, "message": "task status (live)",
                    "data": self._latest_task_status}
        return {"success": True, "message": "task status: PENDING",
                "data": {"status": "PENDING", "task_id": "", "current_step": 0, "total_steps": 0}}

    def _tool_stop_robot(self, reason: str = "user requested emergency stop") -> dict:
        return self._robot_tools.stop_robot(reason)

    def _tool_cancel_task(self, reason: str = "user cancelled patrol") -> dict:
        return self._robot_tools.cancel_task(reason)

    def _tool_reset_task(self, reason: str = "operator confirmed reset") -> dict:
        return self._robot_tools.reset_task(reason)

    def _tool_start_patrol(self, route: list, user_text: str = "") -> dict:
        status_result = self._robot_tools.get_robot_status()
        if not status_result.get("success"):
            return {
                "success": False,
                "message": "无法确认 task_manager 安全状态，拒绝启动巡检",
                "data": status_result,
            }
        status_data = self._loads_json(status_result.get("data_json", "{}"))
        status = str(status_data.get("status", status_result.get("status", "")))
        if status != "PENDING" or status_data.get("emergency_stop_active"):
            return {
                "success": False,
                "message": (
                    f"当前任务状态为 {status or 'UNKNOWN'}"
                    f"，急停={bool(status_data.get('emergency_stop_active'))}，"
                    "请先确认安全并复位"
                ),
                "data": status_data,
            }
        return self._robot_tools.start_patrol(route, user_text)

    def _tool_query_vision(self) -> dict:
        return self._robot_tools.query_vision()

    def _tool_query_navigation(self) -> dict:
        return self._robot_tools.query_navigation()

    def _tool_check_safety(self) -> dict:
        return self._robot_tools.check_safety()

    def _tool_play_audio(self, name: str = "beep", file_path: str = "",
                         volume: float = 1.0) -> dict:
        return self._robot_tools.play_audio(name=name, file_path=file_path, volume=volume)

    def _tool_download_audio(self, query: str, name: str = "") -> dict:
        return self._robot_tools.download_audio(query=query, name=name)

    def _tool_start_tracking(self, target_classes=None, user_text: str = "") -> dict:
        return self._robot_tools.start_tracking(
            target_classes=target_classes or ["person"], user_text=user_text
        )

    def _tool_stop_tracking(self, reason: str = "user stopped tracking") -> dict:
        return self._robot_tools.stop_tracking(reason=reason)

    @staticmethod
    def _tool_reply(result: dict) -> str:
        if not result.get("success"):
            return f"执行失败：{result.get('message', '未知错误')}"
        replies = {
            "start_patrol": "巡检任务已下发，小车将按安全任务流程执行。",
            "get_robot_status": "已查询小车当前状态。",
            "stop_robot": "已发送紧急停止请求。",
            "cancel_task": "已发送取消任务请求。",
            "reset_task": "任务状态已复位。",
            "query_vision": "已读取最近的视觉检测结果。",
            "query_navigation": "已读取当前导航状态。",
            "check_safety": "已读取当前障碍物与安全状态。",
            "play_audio": "音频播放指令已执行。",
            "download_audio": "音频下载指令已执行。",
            "start_tracking": "已启动目标跟踪，人工控制和安全急停仍保持更高优先级。",
            "stop_tracking": "已停止目标跟踪。",
            "execute_plan": "复杂任务计划已接收，将按步骤安全接续执行。",
        }
        return replies.get(
            str(result.get("tool_name", "")),
            str(result.get("message", "执行完成")),
        )


# ---------------------------------------------------------------------------
# 入口
# ---------------------------------------------------------------------------
def main(args=None):
    rclpy.init(args=args)
    node = LlmGatewayNode()
    try:
        rclpy.spin(node)
    except KeyboardInterrupt:
        node.get_logger().info("llm_gateway_node interrupted")
    finally:
        node.destroy_node()
        rclpy.shutdown()


if __name__ == "__main__":
    main()
