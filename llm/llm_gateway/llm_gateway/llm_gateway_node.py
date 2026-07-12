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
  - /sensor/env_data      → 环境传感器
  - /sensor/alert         → 异常告警
  - /vision/detections    → 视觉检测结果

安全约束：不发布 /cmd_vel，不绕过 task_manager_node。
"""

import json
import re
from collections import defaultdict

import rclpy
from rclpy.node import Node
from rclpy.qos import QoSProfile, ReliabilityPolicy

from icar_interfaces.msg import (
    TaskLog, TaskStatus, NavStatus, ObstacleStatus,
    DetectionArray, EnvData, SensorAlert,
)
from icar_interfaces.srv import GenerateReport, ParseTask

# ---------------------------------------------------------------------------
# 可选依赖
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
    "environment": ("温度", "湿度", "烟雾", "PM2.5", "pm2.5", "环境", "空气",
                    "光照", "气压", "多少度", "热不热", "冷不冷"),
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

        self._provider_cfg = str(self.get_parameter("provider").value)
        self.default_route = list(self.get_parameter("default_route").value)
        self.max_logs_per_task = int(self.get_parameter("max_logs_per_task").value)

        # DeepSeek 客户端（延迟初始化）
        self._client = None
        self._api_ok = False

        # ── 数据缓存 ──
        self.logs_by_task = defaultdict(list)

        self._latest_task_status = None   # dict: {task_id, status, current_step, total_steps, message}
        self._latest_nav_status = None    # dict: {status, progress, distance_remain, message}
        self._latest_obstacle = None      # dict: {is_obstacle, min_distance, direction, risk_level, action}
        self._latest_sensor = None        # dict: {temperature, humidity, smoke, pm25, light, pressure}
        self._latest_detections = None    # list of dict: [{class_name, confidence, bbox, image_path}, ...]
        self._latest_alerts = []          # list of dict: [{sensor_type, current_value, threshold, severity, message}, ...]
        self._max_alerts = 20

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

        self.sensor_sub = self.create_subscription(
            EnvData, "/sensor/env_data", self._on_env_data, reliable_qos)

        self.alert_sub = self.create_subscription(
            SensorAlert, "/sensor/alert", self._on_sensor_alert, reliable_qos)

        self.vision_sub = self.create_subscription(
            DetectionArray, "/vision/detections", self._on_detections, best_effort_qos)

        # ── 服务 ──
        self.parse_srv = self.create_service(
            ParseTask, "/llm/parse_task", self._on_parse_task)
        self.report_srv = self.create_service(
            GenerateReport, "/llm/generate_report", self._on_generate_report)

        # 启动信息
        effective = self._resolve_provider()
        self.get_logger().info(
            f"llm_gateway_node ready, provider={effective}, "
            f"api_available={self._api_ok}, "
            f"services=[/llm/parse_task, /llm/generate_report], "
            f"subscriptions=7 topics"
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

    def _on_task_status(self, msg: TaskStatus):
        self._latest_task_status = {
            "task_id": msg.task_id,
            "status": msg.status,
            "current_step": msg.current_step,
            "total_steps": msg.total_steps,
            "message": msg.message,
        }

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

    def _on_env_data(self, msg: EnvData):
        self._latest_sensor = {
            "temperature": round(msg.temperature, 1),
            "humidity": round(msg.humidity, 1),
            "smoke": round(msg.smoke, 1),
            "pm25": round(msg.pm25, 1),
            "light": round(msg.light, 1),
            "pressure": round(msg.pressure, 1),
        }

    def _on_sensor_alert(self, msg: SensorAlert):
        alert = {
            "sensor_type": msg.sensor_type,
            "current_value": round(msg.current_value, 2),
            "threshold": round(msg.threshold, 2),
            "severity": msg.severity,
            "message": msg.message,
        }
        self._latest_alerts.append(alert)
        if len(self._latest_alerts) > self._max_alerts:
            self._latest_alerts = self._latest_alerts[-self._max_alerts:]

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
            "sensor": self._latest_sensor or {},
            "sensor_alerts": self._latest_alerts[-5:] if self._latest_alerts else [],
            "detections": self._latest_detections or [],
        }

    def _rule_answer(self, question: str, query_type: str,
                     context: dict) -> str:
        """规则模板：当 DeepSeek 不可用时生成简短回答。"""
        parts = []

        if query_type in ("environment", "all"):
            sensor = context.get("sensor", {})
            if sensor:
                parts.append(
                    f"当前环境：温度 {sensor.get('temperature', '?')}℃，"
                    f"湿度 {sensor.get('humidity', '?')}%，"
                    f"烟雾 {sensor.get('smoke', '?')}ppm，"
                    f"PM2.5 {sensor.get('pm25', '?')}μg/m³"
                )
            else:
                parts.append("环境传感器暂无数据")

        if query_type in ("vision", "all"):
            detections = context.get("detections", [])
            if detections:
                names = [d["class_name"] for d in detections]
                parts.append(f"最近检测到: {'、'.join(names)}")
            elif query_type == "vision":
                parts.append("视觉模块暂无检测数据")

        if query_type in ("navigation", "all"):
            nav = context.get("nav_status", {})
            if nav:
                parts.append(
                    f"导航状态: {nav.get('status', '?')}，"
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
                        f"方位 {obs.get('direction', '?')}，"
                        f"风险 {obs.get('risk_level', '?')}"
                    )
                else:
                    parts.append("前方安全，未检测到障碍物")
            elif query_type == "safety":
                parts.append("障碍物检测暂无数据")

        if query_type in ("status", "all"):
            ts = context.get("task_status", {})
            if ts:
                parts.append(
                    f"任务状态: {ts.get('status', '?')}，"
                    f"步骤 {ts.get('current_step', 0)}/{ts.get('total_steps', 0)}"
                )
            elif query_type == "status":
                parts.append("任务状态暂无数据")

        alerts = context.get("sensor_alerts", [])
        if alerts and query_type in ("environment", "safety", "status", "all"):
            alert_msgs = [a.get("message", "") for a in alerts[-3:]]
            parts.append(f"最近告警: {'; '.join(alert_msgs)}")

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
                if "temperature" in str(w) or "温度" in str(w):
                    lines.append(f"  - 温度偏高，建议检查该区域通风和空调")
                elif "smoke" in str(w) or "烟雾" in str(w):
                    lines.append(f"  - ⚠️ 检测到烟雾，请立即到现场查看！")
                elif "obstacle" in str(w) or "障碍" in str(w):
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
            "smoke": "烟雾（紧急！）",
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
