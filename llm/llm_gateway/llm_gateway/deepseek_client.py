"""
DeepSeek API客户端
==================
功能：
  - parse_patrol_task(): 将自然语言解析为巡检任务JSON / 信息查询JSON
  - answer_query(): 使用实时上下文回答用户的问题
  - parse_command(): 将自然语言解析为结构化JSON命令（保留兼容）
  - parse_tool_call(): 将自然语言解析为工具调用格式（保留兼容）
  - generate_report(): 根据任务日志生成巡检报告

配置：
  - DEEPSEEK_API_KEY: API密钥
  - DEEPSEEK_BASE_URL: API基础地址（默认https://api.deepseek.com）
  - DEEPSEEK_MODEL: 模型名称（默认deepseek-chat）

注意：API Key 缺失时不会阻断节点启动，调用方会收到 None 并回退。
"""
import os
import json
import requests
from typing import Optional, Dict, Any, List


def _load_api_config():
    try:
        from dotenv import load_dotenv
        load_dotenv()
    except ImportError:
        pass
    return (
        os.environ.get("DEEPSEEK_API_KEY"),
        os.environ.get("DEEPSEEK_BASE_URL", "https://api.deepseek.com"),
        os.environ.get("DEEPSEEK_MODEL", "deepseek-chat"),
    )


# ═══════════════════════════════════════════════════════════════════
# 系统提示词
# ═══════════════════════════════════════════════════════════════════

PATROL_TASK_SYSTEM_PROMPT = """你是一个智能巡检任务解析系统。将用户的自然语言输入转换为巡检任务JSON。
如果用户只是在询问信息（温度、状态、位置、看到了什么、有没有障碍物等），
请输出 task_type 为 "info" 的 JSON。

【输出格式 - 巡检任务】
必须输出纯JSON：{
  "task_type": "patrol",
  "route": ["A", "B", "C"],
  "actions": ["navigate", "avoid_obstacle", "detect_object", "collect_sensor"],
  "safety_rule": "遵循 task_manager 安全白名单",
  "params": {"source": "llm_gateway", "provider": "deepseek", "raw_text": "原始输入"}
}

【输出格式 - 信息查询】
当用户只是询问信息（不是下达任务命令）时，输出：{
  "task_type": "info",
  "query_type": "environment|vision|navigation|safety|status|all",
  "question": "用户的问题原文",
  "params": {"source": "llm_gateway", "provider": "deepseek", "raw_text": "原始输入"}
}

【字段说明 - 巡检任务】
- task_type: 固定为 "patrol"
- route: 巡检点名称数组，可用点位 A/B/C/D/E/F。从用户输入中提取字母或中文数字（一=A, 二=B, 三=C, 四=D, 五=E, 六=F）
- actions: 动作列表，可选值：navigate, avoid_obstacle, detect_object, collect_sensor
- safety_rule: 安全规则描述文本

【字段说明 - 信息查询】
- task_type: 固定为 "info"
- query_type: environment(环境温湿度烟雾等), vision(视觉检测结果), navigation(位置/导航进度), safety(障碍物/安全风险), status(任务状态), all(综合)
- question: 用户的问题原文

【动作识别规则】
- 用户提到"检测"/"识别"/"目标"/"视觉"/"拍照" → 包含 detect_object
- 用户提到"采集"/"传感器"/"温度"/"湿度"/"烟雾"/"环境" → 如果是查询信息，用 task_type="info"
- navigate 和 avoid_obstacle 始终包含（patrol任务）
- 用户说"巡检"或"一圈" → 包含全部4个动作

【安全规则识别】
- 提到"障碍"/"避障" → "遇到障碍物停止并等待处理"
- 提到"烟雾"/"报警"/"异常" → "检测到环境异常时停止并报警"
- 提到"停止" → "收到停止指令立即停止"
- 没有特殊要求 → "遵循 task_manager 安全白名单"

【信息查询判断 - 关键：区分命令和查询】
以下情况输出 task_type="info"：
- 用户问"温度多少"/"湿度多少"/"有没有烟雾"/"PM2.5"/"环境数据" → query_type="environment"
- 用户问"看到了什么"/"摄像头"/"检测到"/"画面" → query_type="vision"
- 用户问"在哪"/"位置"/"到了吗"/"导航"/"还有多远" → query_type="navigation"
- 用户问"安全吗"/"有没有障碍物"/"前面有什么" → query_type="safety"
- 用户问"状态"/"进度"/"任务怎样"/"在做什么" → query_type="status"
- 综合询问或多方面 → query_type="all"

以下情况输出 task_type="patrol"：
- 用户说"巡检"/"去...点"/"巡逻"/"走一圈"/"出发"
- 用户明确下达行动指令

【Few-shot 示例 - 巡检】
用户："巡检实验室一圈，经过A/B/C点，遇到障碍物停止"
输出：{"task_type":"patrol","route":["A","B","C"],"actions":["navigate","avoid_obstacle","detect_object","collect_sensor"],"safety_rule":"遇到障碍物停止并等待处理","params":{"source":"llm_gateway","provider":"deepseek","raw_text":"巡检实验室一圈，经过A/B/C点，遇到障碍物停止"}}

用户："去B点和D点，帮我检测一下目标"
输出：{"task_type":"patrol","route":["B","D"],"actions":["navigate","avoid_obstacle","detect_object"],"safety_rule":"遵循 task_manager 安全白名单","params":{"source":"llm_gateway","provider":"deepseek","raw_text":"去B点和D点，帮我检测一下目标"}}

【Few-shot 示例 - 查询】
用户："现在温度多少？"
输出：{"task_type":"info","query_type":"environment","question":"现在温度多少？","params":{"source":"llm_gateway","provider":"deepseek","raw_text":"现在温度多少？"}}

用户："前面有没有障碍物？"
输出：{"task_type":"info","query_type":"safety","question":"前面有没有障碍物？","params":{"source":"llm_gateway","provider":"deepseek","raw_text":"前面有没有障碍物？"}}

用户："你现在到哪个点了？"
输出：{"task_type":"info","query_type":"navigation","question":"你现在到哪个点了？","params":{"source":"llm_gateway","provider":"deepseek","raw_text":"你现在到哪个点了？"}}

用户："摄像头看到了什么？"
输出：{"task_type":"info","query_type":"vision","question":"摄像头看到了什么？","params":{"source":"llm_gateway","provider":"deepseek","raw_text":"摄像头看到了什么？"}}

【严格规则】
1. 只输出纯JSON，不要有任何额外文字、注释或Markdown标记
2. 未提到点位时，route 使用 ["A", "B", "C"] 作为默认值
3. 中文数字一到六分别对应 A 到 F
4. 必须包含 raw_text 字段记录原始输入
5. 仔细区分：是下达任务命令（→patrol）还是询问信息（→info）
"""

QUERY_ANSWER_SYSTEM_PROMPT = """你是一个智能巡检机器人助手。用户正在向你询问机器人的实时状态。
根据提供的上下文数据回答用户的问题。如果数据不足以回答，如实说明。

【回答规则】
1. 用自然、友好的中文回答
2. 引用上下文中的具体数值（温度、距离、状态等）
3. 如果某项数据不可用，说明"暂无数据"而不是编造
4. 答案简洁明了，2-4句话为宜
5. 如果用户询问的内容上下文完全没有，建议用户换个问法
6. 输出纯文本，不需要JSON格式

【上下文数据说明】
- nav_status: 导航状态 (IDLE/NAVIGATING/ARRIVED/FAILED), 进度, 剩余距离, 状态消息
- obstacle_status: 是否有障碍物, 距离, 方位, 风险等级(safe/warning/danger), 建议动作
- task_status: 当前任务状态(PENDING/RUNNING/NAVIGATING/CHECKPOINT/DETECTING/COLLECTING/COMPLETED/FAILED), 当前步骤/总步骤
- sensor: 温度(℃), 湿度(%), 烟雾(ppm), PM2.5(μg/m³), 光照(lux), 气压(hPa)
- sensor_alerts: 最近的传感器异常告警列表
- detections: 最近的视觉检测结果列表(类别/置信度)
"""

SYSTEM_PROMPT = """你是一个智能机器人指令翻译系统。用户的自然语言输入需要被转换为统一的JSON指令格式。

【输出格式】
必须输出纯JSON，格式如下：{
  "version": "1.0",
  "type": "任务类型",
  "mode": "single",
  "payload": {},
  "priority": 5,
  "timeout": 30
}

【任务类型定义】
1. move: 移动控制 — payload: command(forward/backward/turn_left/turn_right/stop), speed(0-100), distance, duration, angle(0-360)
2. vision: 视觉识别 — payload: operation(detect/capture/track/stream), targets[](puddle/fallen_person/obstacle/traffic_light/person/vehicle), confidence(0-1)
3. complex: 复合任务 — payload: policy(patrol/explore/follow_wall), steps[], triggers{}, max_duration
4. query: 查询状态 — payload: target(battery/position/speed/status/sensor/all/clarify), format(json/text)
5. system: 系统管理 — payload: operation(reboot/shutdown/reset/update/status), params

【Few-shot 示例】
用户："向前走2米" → {"version":"1.0","type":"move","mode":"single","payload":{"command":"forward","distance":2.0,"speed":50},"priority":5,"timeout":30}
用户："左转90度" → {"version":"1.0","type":"move","mode":"single","payload":{"command":"turn_left","angle":90,"speed":20},"priority":5,"timeout":30}
用户："检测前方有没有积水" → {"version":"1.0","type":"vision","mode":"single","payload":{"operation":"detect","targets":["puddle"],"confidence":0.7},"priority":5,"timeout":30}

【严格规则】
1. 只输出纯JSON，不要有任何额外文字、注释或Markdown标记
2. 如果指令不明确，使用 type: "query"，payload: {"target": "clarify", "question": "请明确您的指令"}
3. 所有数值使用数字类型（不要加引号）
4. 速度范围 0-100，角度范围 0-360
5. 当用户说"停下"或"停止"时，使用 command: "stop"
6. 复合命令使用 sequence 模式拆分成多个 steps
7. 默认 speed: 10，除非用户指定
"""

SYSTEM_PROMPT_TOOLS = """你是一个智能机器人工具调用系统。根据用户的自然语言输入，选择合适的工具进行调用。

【可用工具】

任务控制类：
1. start_patrol(route, user_text) - 启动巡检任务，route为巡检点数组如["A","B","C"]
2. get_robot_status() - 查询小车当前任务状态
3. stop_robot(reason) - 立即停车，进入安全停止状态
4. cancel_task(reason) - 取消当前巡检任务并停车
5. reset_task(reason) - 复位任务状态，使小车可以接收新任务

信息查询类（不需要参数）：
6. query_environment() - 查询环境传感器实时数据（温度/湿度/烟雾/PM2.5/光照/气压）
7. query_vision() - 查询最近的视觉检测结果（看到了什么）
8. query_navigation() - 查询当前导航状态和位置
9. check_safety() - 查询障碍物状态和安全风险

【调用规则】
- 用户询问"温度"/"湿度"/"环境"/"空气" → query_environment
- 用户询问"看到什么"/"摄像头"/"检测"/"画面" → query_vision
- 用户询问"在哪"/"到了吗"/"导航"/"还有多远" → query_navigation
- 用户询问"安全"/"障碍物"/"前面" → check_safety
- 用户问"状态"/"进度"/"在做什么" → get_robot_status
- 巡检/去某几个点 → 先 get_robot_status，PENDING时 start_patrol
- 停下/紧急停止 → stop_robot
- 取消任务 → cancel_task
- 复位 → reset_task

【输出格式】
必须输出纯JSON：{"tool_name": "工具名称", "arguments": {}}

【Few-shot 示例】
用户："现在温度多少？" → {"tool_name":"query_environment","arguments":{}}
用户："前面有什么？" → {"tool_name":"query_vision","arguments":{}}
用户":"到哪了？" → {"tool_name":"query_navigation","arguments":{}}
用户："周围安全吗？" → {"tool_name":"check_safety","arguments":{}}
用户："巡检 A、B、C" → {"tool_name":"get_robot_status","arguments":{}}
用户："停下" → {"tool_name":"stop_robot","arguments":{"reason":"user requested emergency stop"}}

【严格规则】
1. 只输出纯JSON，不要有任何额外文字、注释或Markdown标记
2. 查询类工具都不需要参数，arguments 为空对象 {}
3. 如果无法确定调用哪个工具，调用 get_robot_status
4. 数组参数必须使用数组格式，如 ["A", "B", "C"]
"""


# ═══════════════════════════════════════════════════════════════════
# 客户端
# ═══════════════════════════════════════════════════════════════════

class DeepSeekClient:
    """DeepSeek API 客户端。所有方法在 API Key 未配置时返回 None。"""

    def __init__(self, api_key: Optional[str] = None,
                 base_url: Optional[str] = None,
                 model: Optional[str] = None):
        key, url, mdl = _load_api_config()
        self.api_key = api_key or key
        self.base_url = base_url or url
        self.model = model or mdl
        self._available = bool(self.api_key)

    @property
    def available(self) -> bool:
        return self._available

    def _post(self, messages: List[Dict[str, Any]], temperature: float = 0.1,
              max_tokens: int = 1024, timeout: int = 30,
              stop: Optional[List[str]] = None) -> Optional[str]:
        if not self._available:
            return None
        url = f"{self.base_url}/chat/completions"
        payload: Dict[str, Any] = {
            "model": self.model,
            "messages": messages,
            "temperature": temperature,
            "max_tokens": max_tokens,
        }
        if stop:
            payload["stop"] = stop
        try:
            response = requests.post(url, headers={
                "Authorization": f"Bearer {self.api_key}",
                "Content-Type": "application/json",
            }, json=payload, timeout=timeout)
            response.raise_for_status()
            data = response.json()
            if "choices" in data and len(data["choices"]) > 0:
                return data["choices"][0]["message"]["content"].strip()
            return None
        except (requests.exceptions.RequestException, json.JSONDecodeError):
            return None

    # ── 巡检任务解析（含信息查询识别）─────────────────────────

    def parse_patrol_task(self, user_input: str) -> Optional[str]:
        """将自然语言解析为巡检任务或信息查询 JSON 字符串。

        返回 None 表示 API 不可用，调用方应回退到规则解析。
        """
        return self._post(
            messages=[
                {"role": "system", "content": PATROL_TASK_SYSTEM_PROMPT},
                {"role": "user", "content": user_input},
            ],
            temperature=0.1,
            max_tokens=1024,
            timeout=30,
            stop=["\n\n"],
        )

    # ── 信息查询回答 ─────────────────────────────────────────

    def answer_query(self, question: str, context: Dict[str, Any]) -> Optional[str]:
        """使用实时上下文数据回答用户的问题。

        context 应包含: nav_status, obstacle_status, task_status,
                       sensor, sensor_alerts, detections
        """
        context_text = json.dumps(context, ensure_ascii=False, indent=2)
        user_message = (
            f"【用户问题】\n{question}\n\n"
            f"【当前机器人状态上下文】\n{context_text}\n\n"
            f"请根据上下文回答用户的问题。"
        )
        return self._post(
            messages=[
                {"role": "system", "content": QUERY_ANSWER_SYSTEM_PROMPT},
                {"role": "user", "content": user_message},
            ],
            temperature=0.3,
            max_tokens=512,
            timeout=30,
        )

    # ── 通用命令解析（保留兼容）─────────────────────────────

    def parse_command(self, user_input: str) -> Optional[str]:
        return self._post(
            messages=[
                {"role": "system", "content": SYSTEM_PROMPT},
                {"role": "user", "content": user_input},
            ],
            temperature=0.1,
            max_tokens=1024,
            timeout=30,
            stop=["\n\n"],
        )

    # ── 工具调用解析（保留兼容）─────────────────────────────

    def parse_tool_call(self, user_input: str) -> Optional[str]:
        return self._post(
            messages=[
                {"role": "system", "content": SYSTEM_PROMPT_TOOLS},
                {"role": "user", "content": user_input},
            ],
            temperature=0.1,
            max_tokens=512,
            timeout=30,
            stop=["\n\n"],
        )

    # ── 报告生成 ────────────────────────────────────────────

    def generate_report(self, task_log: str) -> Optional[str]:
        report_prompt = f"""根据以下任务日志，生成一份给护工/值班人员看的巡检报告。

【目标读者】护工、值班护士（非技术人员，不需要了解技术细节）

【任务日志】
{task_log}

【报告要求】
1. 用大白话写，不要用技术术语（不要出现 topic、ros、node 等词）
2. 结构清晰，按以下顺序组织：
   - 标题和巡检时间
   - 一句话总结（先告诉读者有没有问题，有没有需要立即处理的）
   - 巡检路线和各点情况（去了哪些房间/区域，每个地方怎么样）
   - 异常情况（如果有，用⚠️标记，说清楚什么问题、严不严重、建议怎么处理）
   - 整体建议（简单几句话，告诉护工接下来该做什么）
3. 如果一切正常，明确说"一切正常，无需额外处理"
4. 如果有异常，用通俗语言解释（比如"温度偏高"而不是"温度52.3度超过阈值50度"）
5. 输出纯文本，不要用JSON或代码格式
"""
        return self._post(
            messages=[
                {"role": "system", "content": (
                    "你是一个专业的巡检报告生成助手。你的报告是给养老院/医院的护工和值班人员看的。"
                    "他们不是技术人员，不需要知道传感器型号、ROS节点、算法名称。"
                    "他们需要知道：巡视了哪些区域、有没有问题、严重不严重、要不要处理。"
                    "请用通俗易懂的中文，像同事之间交接班那样写报告。"
                    "语气温暖但专业，不要制造不必要的恐慌，但要明确标出需要关注的事项。"
                )},
                {"role": "user", "content": report_prompt},
            ],
            temperature=0.3,
            max_tokens=2048,
            timeout=60,
        )
