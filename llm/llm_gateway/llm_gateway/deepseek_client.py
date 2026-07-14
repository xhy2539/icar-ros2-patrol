"""
DeepSeek API客户端
==================
功能：
  - 封装DeepSeek API调用，支持真实API请求
  - parse_command(): 将自然语言解析为结构化JSON命令
  - parse_tool_call(): 将自然语言解析为工具调用格式
  - generate_report(): 根据任务日志生成巡检报告

配置：
  - DEEPSEEK_API_KEY: API密钥（必须设置环境变量或.env文件）
  - DEEPSEEK_BASE_URL: API基础地址（默认https://api.deepseek.com）
  - DEEPSEEK_MODEL: 模型名称（默认deepseek-chat）

环境变量设置方式：
  1. 终端设置：export DEEPSEEK_API_KEY="your_key"
  2. 创建.env文件，内容：DEEPSEEK_API_KEY="your_key"

依赖：
  - requests: HTTP请求
  - python-dotenv: 环境变量加载
"""
import os
import json
import requests
from typing import Optional, Dict, Any, List

try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass

DEEPSEEK_API_KEY = os.environ.get("DEEPSEEK_API_KEY")
DEEPSEEK_BASE_URL = os.environ.get("DEEPSEEK_BASE_URL", "https://api.deepseek.com")
DEEPSEEK_MODEL = os.environ.get("DEEPSEEK_MODEL", "deepseek-chat")

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

任务控制类：
1. start_patrol(route, user_text) - 启动巡检任务，route为巡检点数组如["A","B","C"]
2. get_robot_status() - 查询小车当前任务状态
3. stop_robot(reason) - 立即停车，进入安全停止状态
4. cancel_task(reason) - 取消当前巡检任务并停车
5. reset_task(reason) - 复位任务状态，使小车可以接收新任务

音频播放类：
6. play_audio(name, file_path, volume) - 通过音箱播放音频
   - name: 音频名称。支持预定义名称，也支持 audio/ 目录下任意文件名（不含扩展名）。默认 beep。
   - file_path: 自定义音频文件绝对路径（可选，优先于 name）
   - volume: 音量 0.0-1.0（可选，默认 1.0）
7. download_audio(query, name) - 从 YouTube 搜索并下载音频到 audio/ 目录
   - query: 搜索关键词（如 'bird song'、'警笛声'），必填
   - name: 保存文件名（可选，默认由 query 生成）
   ⚠ 当 play_audio 本地找不到时，先用 download_audio 下载，再 play_audio 播放。

信息查询类（不需要参数）：
8. query_vision() - 查询最近的视觉检测结果（看到了什么）
9. query_navigation() - 查询当前导航状态和位置
10. check_safety() - 查询障碍物状态和安全风险

目标跟踪类：
11. start_tracking(target_classes, user_text) - 启动视觉目标跟踪，默认跟踪 person
12. stop_tracking(reason) - 停止目标跟踪并输出零速度
13. move_robot(direction, duration_sec, speed) - 受限低速短时移动
   - direction 仅可为 forward/backward/left/right/turn_left/turn_right
   - duration_sec 必须为 0.2~3.0 秒；speed 必须为 0.05~0.18 m/s
   - 运动始终经过 velocity_mux、避障与急停，不能用于连续或高速控制

复杂任务类：
14. execute_plan(steps) - 按顺序执行安全白名单工具；start_patrol 步骤必须等待任务 COMPLETED 后才接续下一步
   - steps: [{"tool_name":"start_patrol","arguments":{"route":["A","B"]},"wait_for":"task_completed"},{"tool_name":"play_audio","arguments":{"name":"complete"}}]
   - 只允许巡检、状态查询、视觉/导航/安全查询、音频和目标跟踪工具，禁止直接速度控制

【输出格式】
必须输出纯JSON，格式如下：{
  "tool_name": "工具名称",
  "arguments": {"参数名": "参数值"}
}

【调用规则】
1. 用户要求"巡检/去某几个点"：调用 start_patrol；网关会在执行前校验任务状态
2. 用户要求"停下/紧急停止/别动"：立即调用 stop_robot
3. 用户要求"取消任务/不要做了"：调用 cancel_task
4. 用户要求"重新开始/恢复接收任务"：调用 reset_task（需人工确认安全）
5. 用户询问"状态/在做什么"：调用 get_robot_status
6. 用户询问"看到什么"/"摄像头"/"检测"/"画面" → query_vision
7. 用户询问"在哪"/"到了吗"/"导航" → query_navigation
8. 用户询问"安全"/"障碍物"/"前面" → check_safety
9. 用户要求播放音频/提示音/语音 → play_audio
   - "欢迎/你好"→welcome, "开始/出发"→start_patrol, "完成/结束"→complete
   - "警告/注意"→alert, "嘀/提示音"→beep, "停止"→stop
   - "危险"→danger, "通知"→info, "错误/失败"→error, "再见"→bye
   - ⚠ 用户说"播放xxx"时，直接把xxx原文作为 name 传入！如"播放碎玉轩小曲"→name="碎玉轩小曲"，"播放鸟叫声"→name="鸟叫声"
10. 用户要求"跟踪/跟随/追踪某人" → start_tracking，默认 target_classes=["person"]
11. 用户要求"停止跟踪/取消跟随" → stop_tracking
12. 用户要求短时低速“前进/后退/左移/右移/左转/右转” → move_robot；不得超过 3 秒
13. 用户包含"然后/完成后/接着/最后"等多个动作 → execute_plan；巡检步骤设置 wait_for="task_completed"

【Few-shot 示例】
用户："巡检 A、B、C 三个点"
输出：{"tool_name":"start_patrol","arguments":{"route":["A","B","C"],"user_text":"巡检 A、B、C 三个点"}}

用户："停下"
输出：{"tool_name":"stop_robot","arguments":{"reason":"user requested emergency stop"}}

用户："前面有什么？"
输出：{"tool_name":"query_vision","arguments":{}}

用户："播放欢迎语音"
输出：{"tool_name":"play_audio","arguments":{"name":"welcome"}}

用户："警告一下"
输出：{"tool_name":"play_audio","arguments":{"name":"alert"}}

用户："放一段鸟叫声"
输出：{"tool_name":"play_audio","arguments":{"name":"bird"}}
→ 如果本地没有 bird 音频，则先调用 download_audio(query="鸟叫声", name="bird")，再 play_audio(name="bird")

用户："播放碎玉轩小曲"
输出：{"tool_name":"play_audio","arguments":{"name":"碎玉轩小曲"}}

用户："下载一段警笛声"
输出：{"tool_name":"download_audio","arguments":{"query":"警笛声","name":"siren"}}

用户："当前状态是什么"
输出：{"tool_name":"get_robot_status","arguments":{}}

用户："跟踪前面的人"
输出：{"tool_name":"start_tracking","arguments":{"target_classes":["person"]}}

用户："停止跟踪"
输出：{"tool_name":"stop_tracking","arguments":{"reason":"user stopped tracking"}}

用户："巡检A和B点，完成后播放完成提示音，然后查询视觉"
输出：{"tool_name":"execute_plan","arguments":{"steps":[{"tool_name":"start_patrol","arguments":{"route":["A","B"],"user_text":"巡检A和B点"},"wait_for":"task_completed"},{"tool_name":"play_audio","arguments":{"name":"complete"}},{"tool_name":"query_vision","arguments":{}}]}}

【严格规则】
1. 只输出纯JSON，不要有任何额外文字、注释或Markdown标记
2. 如果无法确定调用哪个工具，调用 get_robot_status 查询状态
3. 数组参数必须使用数组格式，如 ["A", "B", "C"]
4. 查询类工具（query_vision/query_navigation/check_safety）不需要参数
5. 不要调用不存在的工具
"""


class DeepSeekClient:
    def __init__(self, api_key: Optional[str] = None, base_url: Optional[str] = None, model: Optional[str] = None):
        self.api_key = api_key or DEEPSEEK_API_KEY
        self.base_url = base_url or DEEPSEEK_BASE_URL
        self.model = model or DEEPSEEK_MODEL
        self.available = bool(self.api_key)
        self.headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json"
        } if self.available else {}

    def _build_messages(self, user_input: str) -> List[Dict[str, Any]]:
        return [
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": user_input}
        ]

    def parse_command(self, user_input: str) -> str:
        if not self.available:
            raise RuntimeError("请设置环境变量 DEEPSEEK_API_KEY")
        url = f"{self.base_url}/chat/completions"

        payload = {
            "model": self.model,
            "messages": self._build_messages(user_input),
            "temperature": 0.1,
            "max_tokens": 1024,
            "stop": ["\n\n"]
        }

        try:
            response = requests.post(url, headers=self.headers, json=payload, timeout=30)
            response.raise_for_status()
            data = response.json()

            if "choices" in data and len(data["choices"]) > 0:
                content = data["choices"][0]["message"]["content"].strip()
                return content

            raise ValueError("No response from DeepSeek API")

        except requests.exceptions.RequestException as e:
            raise RuntimeError(f"DeepSeek API request failed: {str(e)}")
        except json.JSONDecodeError as e:
            raise RuntimeError(f"Failed to parse DeepSeek API response: {str(e)}")

    def parse_tool_call(self, user_input: str) -> str:
        if not self.available:
            raise RuntimeError("请设置环境变量 DEEPSEEK_API_KEY")
        url = f"{self.base_url}/chat/completions"

        payload = {
            "model": self.model,
            "messages": [
                {"role": "system", "content": SYSTEM_PROMPT_TOOLS},
                {"role": "user", "content": user_input}
            ],
            "temperature": 0.1,
            "max_tokens": 512,
            "stop": ["\n\n"]
        }

        try:
            response = requests.post(url, headers=self.headers, json=payload, timeout=30)
            response.raise_for_status()
            data = response.json()

            if "choices" in data and len(data["choices"]) > 0:
                content = data["choices"][0]["message"]["content"].strip()
                return content

            raise ValueError("No response from DeepSeek API")

        except requests.exceptions.RequestException as e:
            raise RuntimeError(f"DeepSeek API request failed: {str(e)}")
        except json.JSONDecodeError as e:
            raise RuntimeError(f"Failed to parse DeepSeek API response: {str(e)}")

    def generate_report(self, task_log: str) -> str:
        if not self.available:
            raise RuntimeError("请设置环境变量 DEEPSEEK_API_KEY")
        report_prompt = f"""根据以下任务日志，生成一份结构化的巡检报告：

【任务日志】
{task_log}

【报告格式要求】
1. 使用自然语言描述巡检过程
2. 包含时间线、关键事件、异常记录
3. 总结巡检结果和建议
4. 输出纯文本，不需要JSON格式
"""

        url = f"{self.base_url}/chat/completions"

        payload = {
            "model": self.model,
            "messages": [
                {"role": "system", "content": "你是一个专业的巡检报告生成助手。请根据任务日志生成详细的巡检报告。"},
                {"role": "user", "content": report_prompt}
            ],
            "temperature": 0.3,
            "max_tokens": 2048
        }

        try:
            response = requests.post(url, headers=self.headers, json=payload, timeout=60)
            response.raise_for_status()
            data = response.json()

            if "choices" in data and len(data["choices"]) > 0:
                content = data["choices"][0]["message"]["content"].strip()
                return content

            raise ValueError("No response from DeepSeek API")

        except requests.exceptions.RequestException as e:
            raise RuntimeError(f"DeepSeek API request failed: {str(e)}")
        except json.JSONDecodeError as e:
            raise RuntimeError(f"Failed to parse DeepSeek API response: {str(e)}")
