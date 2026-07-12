"""
DeepSeek API客户端
==================
功能：
  - 封装DeepSeek API调用，支持真实API请求
  - parse_patrol_task(): 将自然语言解析为巡检任务JSON
  - parse_command(): 将自然语言解析为结构化JSON命令
  - parse_tool_call(): 将自然语言解析为工具调用格式
  - generate_report(): 根据任务日志生成巡检报告

配置：
  - DEEPSEEK_API_KEY: API密钥（必须设置环境变量或.env文件）
  - DEEPSEEK_BASE_URL: API基础地址（默认https://api.deepseek.com）
  - DEEPSEEK_MODEL: 模型名称（默认deepseek-chat）

注意：API Key 缺失时不会阻断节点启动，调用方会收到 None 并回退到规则解析。
"""
import os
import json
import requests
from typing import Optional, Dict, Any, List


def _load_api_config():
    """延迟加载 API 配置，避免模块导入时因缺少 .env 崩溃。"""
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


PATROL_TASK_SYSTEM_PROMPT = """你是一个智能巡检任务解析系统。将用户的自然语言输入转换为巡检任务JSON。

【输出格式】
必须输出纯JSON，格式如下：{
  "task_type": "patrol",
  "route": ["A", "B", "C"],
  "actions": ["navigate", "avoid_obstacle", "detect_object", "collect_sensor"],
  "safety_rule": "遵循 task_manager 安全白名单",
  "params": {}
}

【字段说明】
- task_type: 固定为 "patrol"
- route: 巡检点名称数组，可用点位 A/B/C/D/E/F。从用户输入中提取字母或中文数字（一=A, 二=B, 三=C, 四=D, 五=E, 六=F）
- actions: 动作列表，可选值：navigate（导航移动）, avoid_obstacle（避障）, detect_object（视觉检测/目标识别）, collect_sensor（传感器采集）
- safety_rule: 安全规则描述文本
- params: 附加参数对象，必须包含 source="llm_gateway", provider="deepseek", raw_text=<原始输入>

【动作识别规则】
- 用户提到"检测"/"识别"/"目标"/"视觉"/"拍照" → 包含 detect_object
- 用户提到"采集"/"传感器"/"温度"/"湿度"/"烟雾"/"环境" → 包含 collect_sensor
- navigate 和 avoid_obstacle 始终包含
- 用户说"巡检"或"一圈" → 包含全部4个动作

【安全规则识别】
- 提到"障碍"/"避障" → "遇到障碍物停止并等待处理"
- 提到"烟雾"/"报警"/"异常" → "检测到环境异常时停止并报警"
- 提到"停止" → "收到停止指令立即停止"
- 没有特殊要求 → "遵循 task_manager 安全白名单"

【Few-shot 示例】
用户："巡检实验室一圈，经过A/B/C点，遇到障碍物停止"
输出：{"task_type":"patrol","route":["A","B","C"],"actions":["navigate","avoid_obstacle","detect_object","collect_sensor"],"safety_rule":"遇到障碍物停止并等待处理","params":{"source":"llm_gateway","provider":"deepseek","raw_text":"巡检实验室一圈，经过A/B/C点，遇到障碍物停止"}}

用户："去B点和D点，帮我检测一下目标"
输出：{"task_type":"patrol","route":["B","D"],"actions":["navigate","avoid_obstacle","detect_object"],"safety_rule":"遵循 task_manager 安全白名单","params":{"source":"llm_gateway","provider":"deepseek","raw_text":"去B点和D点，帮我检测一下目标"}}

用户："带我去一号点和三号点，采集环境数据"
输出：{"task_type":"patrol","route":["A","C"],"actions":["navigate","avoid_obstacle","collect_sensor"],"safety_rule":"遵循 task_manager 安全白名单","params":{"source":"llm_gateway","provider":"deepseek","raw_text":"带我去一号点和三号点，采集环境数据"}}

用户："在A点停一下，看看周围有没有异常"
输出：{"task_type":"patrol","route":["A"],"actions":["navigate","avoid_obstacle","detect_object"],"safety_rule":"检测到环境异常时停止并报警","params":{"source":"llm_gateway","provider":"deepseek","raw_text":"在A点停一下，看看周围有没有异常"}}

【严格规则】
1. 只输出纯JSON，不要有任何额外文字、注释或Markdown标记
2. 如果未提到任何点位，route 使用 ["A", "B", "C"] 作为默认值
3. 中文数字一到六分别对应 A 到 F
4. 必须包含 raw_text 字段记录原始输入
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
1. move: 移动控制
   - payload 参数: command(必填), speed(可选0-100), distance(可选), duration(可选), angle(可选)
   - command: forward, backward, turn_left, turn_right, stop

2. vision: 视觉识别
   - payload 参数: operation(必填), targets(必填数组), confidence(可选0.7), response(可选)
   - operation: detect, capture, track, stream
   - targets: puddle, fallen_person, obstacle, traffic_light, person, vehicle

3. complex: 复合任务
   - payload 参数: policy(可选), steps(可选), triggers(可选), max_duration(可选)
   - mode: single, sequence, parallel

4. query: 查询状态
   - payload 参数: target(必填), format(可选)
   - target: battery, position, speed, status, sensor, all

5. system: 系统管理
   - payload 参数: operation(必填), params(可选)
   - operation: reboot, shutdown, reset, update, status

【Few-shot 示例】
用户："向前走2米"
输出：{"version":"1.0","type":"move","mode":"single","payload":{"command":"forward","distance":2.0,"speed":50},"priority":5,"timeout":30}

用户："左转90度"
输出：{"version":"1.0","type":"move","mode":"single","payload":{"command":"turn_left","angle":90,"speed":20},"priority":5,"timeout":30}

用户："检测前方有没有积水和跌倒的人"
输出：{"version":"1.0","type":"vision","mode":"single","payload":{"operation":"detect","targets":["puddle","fallen_person"],"confidence":0.7},"priority":5,"timeout":30}

用户："以30%的速度后退3秒"
输出：{"version":"1.0","type":"move","mode":"single","payload":{"command":"backward","speed":30,"duration":3.0},"priority":5,"timeout":30}

用户："巡逻并检测障碍物，遇到就停下"
输出：{"version":"1.0","type":"complex","mode":"single","payload":{"policy":"patrol","triggers":{"on_obstacle":"stop"},"max_duration":600},"priority":5,"timeout":30}

用户："先前进5秒，然后左转，再检测积水"
输出：{"version":"1.0","type":"complex","mode":"sequence","payload":{"steps":[{"type":"move","payload":{"command":"forward","duration":5.0,"speed":50}},{"type":"move","payload":{"command":"turn_left","angle":90,"speed":20}},{"type":"vision","payload":{"operation":"detect","targets":["puddle"],"confidence":0.7}}]},"priority":5,"timeout":30}

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
1. start_patrol(route, user_text) - 启动巡检任务
   - route: 巡检点名称数组，如 ["A", "B", "C"]（必填）
   - user_text: 原始用户输入（可选）

2. get_robot_status() - 查询小车当前任务状态

3. stop_robot(reason) - 立即停车，进入安全停止状态
   - reason: 停车原因（可选）

4. cancel_task(reason) - 取消当前巡检任务并停车
   - reason: 取消原因（可选）

5. reset_task(reason) - 复位任务状态，使小车可以接收新任务
   - reason: 复位原因（可选）

【输出格式】
必须输出纯JSON，格式如下：{
  "tool_name": "工具名称",
  "arguments": {"参数名": "参数值"}
}

【调用规则】
1. 用户要求"巡检/去某几个点"：先调用 get_robot_status，状态为 PENDING 时再调用 start_patrol
2. 用户要求"停下/紧急停止/别动"：立即调用 stop_robot
3. 用户要求"取消任务/不要做了"：调用 cancel_task
4. 用户要求"重新开始/恢复接收任务"：调用 reset_task（需人工确认安全）
5. 用户询问"状态/在做什么"：调用 get_robot_status

【Few-shot 示例】
用户："巡检 A、B、C 三个点"
输出：{"tool_name":"get_robot_status","arguments":{}}

用户："停下"
输出：{"tool_name":"stop_robot","arguments":{"reason":"user requested emergency stop"}}

用户："取消这次巡检"
输出：{"tool_name":"cancel_task","arguments":{"reason":"user cancelled patrol"}}

用户："当前状态是什么"
输出：{"tool_name":"get_robot_status","arguments":{}}

用户："复位任务"
输出：{"tool_name":"reset_task","arguments":{"reason":"operator confirmed reset"}}

【严格规则】
1. 只输出纯JSON，不要有任何额外文字、注释或Markdown标记
2. 如果无法确定调用哪个工具，调用 get_robot_status 查询状态
3. 数组参数必须使用数组格式，如 ["A", "B", "C"]
4. 不要调用不存在的工具
"""


class DeepSeekClient:
    """DeepSeek API 客户端。

    所有方法在 API Key 未配置时返回 None，允许调用方回退到规则解析。
    """

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

    # ── 巡检任务解析（供 llm_gateway_node 使用）─────────────────

    def parse_patrol_task(self, user_input: str) -> Optional[str]:
        """将自然语言解析为巡检任务 JSON 字符串。

        返回 None 表示 API 不可用或调用失败，调用方应回退到规则解析。
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

    # ── 通用命令解析（保留兼容）─────────────────────────────────

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

    # ── 工具调用解析（保留兼容）─────────────────────────────────

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

    # ── 报告生成 ─────────────────────────────────────────────

    def generate_report(self, task_log: str) -> Optional[str]:
        """根据任务日志生成巡检报告。返回 None 表示 API 不可用。"""
        report_prompt = f"""根据以下任务日志，生成一份结构化的巡检报告：

【任务日志】
{task_log}

【报告格式要求】
1. 使用自然语言描述巡检过程
2. 包含时间线、关键事件、异常记录
3. 总结巡检结果和建议
4. 输出纯文本，不需要JSON格式
"""
        return self._post(
            messages=[
                {"role": "system", "content": "你是一个专业的巡检报告生成助手。请根据任务日志生成详细的巡检报告。"},
                {"role": "user", "content": report_prompt},
            ],
            temperature=0.3,
            max_tokens=2048,
            timeout=60,
        )
