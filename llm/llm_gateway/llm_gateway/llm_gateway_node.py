#!/usr/bin/env python3
"""ROS2 LLM gateway — 合并版。

- /llm/parse_task:  DeepSeek API 优先，规则兜底
- /llm/generate_report: DeepSeek API 优先，模板兜底
- 订阅 /task/log 累积日志用于报告生成

安全约束：不发布 /cmd_vel，不绕过 task_manager_node。
"""

import json
import re
from collections import defaultdict

import rclpy
from rclpy.node import Node
from rclpy.qos import QoSProfile, ReliabilityPolicy

from icar_interfaces.msg import TaskLog
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
        """从 LLM 响应中提取首个 JSON 对象。"""
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


# ---------------------------------------------------------------------------
# 节点
# ---------------------------------------------------------------------------
class LlmGatewayNode(Node):
    def __init__(self):
        super().__init__("llm_gateway_node")

        # 参数
        self.declare_parameter("provider", "auto")       # auto | deepseek | rule
        self.declare_parameter("default_route", ["A", "B", "C"])
        self.declare_parameter("max_logs_per_task", 200)

        self._provider_cfg = str(self.get_parameter("provider").value)
        self.default_route = list(self.get_parameter("default_route").value)
        self.max_logs_per_task = int(self.get_parameter("max_logs_per_task").value)

        # DeepSeek 客户端（延迟初始化）
        self._client = None
        self._api_ok = False

        # 日志缓存
        self.logs_by_task = defaultdict(list)

        # 订阅
        qos = QoSProfile(depth=50, reliability=ReliabilityPolicy.RELIABLE)
        self.task_log_sub = self.create_subscription(
            TaskLog, "/task/log", self._on_task_log, qos
        )

        # 服务
        self.parse_srv = self.create_service(
            ParseTask, "/llm/parse_task", self._on_parse_task
        )
        self.report_srv = self.create_service(
            GenerateReport, "/llm/generate_report", self._on_generate_report
        )

        # 启动信息
        effective = self._resolve_provider()
        self.get_logger().info(
            f"llm_gateway_node ready, provider={effective}, "
            f"api_available={self._api_ok}, "
            f"services=[/llm/parse_task, /llm/generate_report]"
        )

    # ── provider 决策 ──────────────────────────────────────────

    def _resolve_provider(self) -> str:
        """返回实际使用的 provider 名称。"""
        if self._provider_cfg == "rule":
            return "rule"

        if self._provider_cfg == "deepseek":
            self._ensure_client()
            if self._api_ok:
                return "deepseek"
            self.get_logger().warn("provider=deepseek but API unavailable, falling back to rule")
            return "rule"

        # auto：有 API 就用，没有就规则
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

    # ── /task/log 订阅 ─────────────────────────────────────────

    def _on_task_log(self, msg: TaskLog):
        record = {
            "task_id": msg.task_id,
            "timestamp": {
                "sec": msg.timestamp.sec,
                "nanosec": msg.timestamp.nanosec,
            },
            "event_type": msg.event_type,
            "severity": msg.severity,
            "data": self._loads_json(msg.data_json),
        }
        bucket = self.logs_by_task[msg.task_id]
        bucket.append(record)
        if len(bucket) > self.max_logs_per_task:
            del bucket[: len(bucket) - self.max_logs_per_task]

    # ── /llm/parse_task ────────────────────────────────────────

    def _on_parse_task(self, request, response):
        text = request.input_text.strip()
        if not text:
            response.task_json = "{}"
            response.success = False
            response.error_msg = "input_text is empty"
            return response

        task = None
        used_provider = "rule"

        if self._use_api:
            task = self._parse_via_api(text)
            if task is not None:
                used_provider = "deepseek"

        if task is None:
            task = self._parse_task_by_rule(text)

        # 统一注入 provider 信息
        task.setdefault("params", {})
        task["params"]["provider"] = used_provider

        response.task_json = json.dumps(task, ensure_ascii=False)
        response.success = True
        response.error_msg = ""
        self.get_logger().info(
            f"parse_task (provider={used_provider}): '{text[:60]}...' -> "
            f"route={task.get('route')}, actions={task.get('actions')}"
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
            # 基本校验
            if "task_type" not in result and "route" not in result:
                self.get_logger().warn(f"API returned unexpected format: {json_str[:100]}")
                return None
            return result
        except Exception as e:
            self.get_logger().warn(f"DeepSeek parse failed, falling back to rule: {e}")
            return None

    # ── 规则解析（与旧版兼容）──────────────────────────────────

    def _parse_task_by_rule(self, text):
        route = self._extract_route(text) or self.default_route
        actions = self._extract_actions(text)
        safety_rule = self._extract_safety_rule(text)
        params = {
            "source": "llm_gateway",
            "raw_text": text,
        }
        if "语音" in text or "说" in text:
            params["input_mode"] = "voice"

        return {
            "task_type": "patrol",
            "route": route,
            "actions": actions,
            "safety_rule": safety_rule,
            "params": params,
        }

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

        cn_points = {"一": "A", "二": "B", "三": "C", "四": "D", "五": "E", "六": "F"}
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

    # ── /llm/generate_report ───────────────────────────────────

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
        """调用 DeepSeek 生成报告，成功返回文本，失败返回 None。"""
        try:
            # 将结构化日志扁平化为文本
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

            report = self._client.generate_report(log_text)
            return report
        except Exception as e:
            self.get_logger().warn(f"DeepSeek report failed, falling back to template: {e}")
            return None

    # ── 模板报告生成（与旧版兼容）──────────────────────────────

    def _build_report(self, task_id, logs):
        checkpoints = []
        detections = []
        warnings = []
        errors = []
        event_count = 0

        for record in logs:
            event_count += 1
            event_type = str(record.get("event_type", ""))
            severity = str(record.get("severity", "INFO"))
            data = record.get("data", {})
            if isinstance(data, str):
                data = self._loads_json(data)

            if event_type in ("CHECKPOINT_REACHED", "NAV_END"):
                checkpoint = data.get("checkpoint") or data.get("target")
                if checkpoint:
                    checkpoints.append(str(checkpoint))
            if event_type == "VISION_DETECT":
                for det in data.get("detections", []):
                    name = det.get("class") or det.get("class_name") or "unknown"
                    detections.append(str(name))
            if event_type == "ANOMALY" or severity == "WARN":
                warnings.append(data)
            if severity == "ERROR":
                errors.append(data)

        route_text = " -> ".join(checkpoints) if checkpoints else "未记录到点事件"
        detection_text = "、".join(sorted(set(detections))) if detections else "无目标记录"
        task_text = task_id or self._infer_task_id(logs)
        result = "异常结束" if errors else "完成/未发现致命错误"

        return (
            f"巡检报告 task_id={task_text}\n"
            f"- 巡检结果: {result}\n"
            f"- 巡检路线: {route_text}\n"
            f"- 视觉结果: {detection_text}\n"
            f"- 告警数量: {len(warnings)}\n"
            f"- 错误数量: {len(errors)}\n"
            f"- 日志事件数: {event_count}"
        )

    # ── 工具方法 ──────────────────────────────────────────────

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
