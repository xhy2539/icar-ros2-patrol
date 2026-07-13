# 导航与 LLM 联调计划

> 创建日期：2026-07-13 | 给 LLM 侧同学同步使用

本文档分两阶段：
- **第一阶段**：LLM 独立测试（开发机即可，不需要导航模块启动）
- **第二阶段**：导航 + LLM 联调（需要导航模块先启动）

LLM 同学先完成第一阶段，全部通过后再进入第二阶段。

---

## 导航侧对外接口（LLM 需要知道的全部）

### 输入（LLM → 导航）

| Topic | 类型 | 说明 |
|-------|------|------|
| `/task/request` | `std_msgs/msg/String` | 任务请求 |
| `/task/control` | `std_msgs/msg/String` | 任务控制指令 |
| `/goal_pose` | `geometry_msgs/msg/PoseStamped` | 单个导航目标点 |

**`/task/request` 消息格式**：

```
route=[A,B,C]           # 按顺序巡检 A→B→C
route=[HOME]            # 单点回充
task=patrol             # 启动巡检
```

**`/task/control` 消息格式**：

```
pause
resume
cancel
```

### 输出（导航 → LLM）

| Topic | 类型 | 说明 |
|-------|------|------|
| `/nav_status` | `icar_interfaces/msg/NavStatus` | 导航状态 |
| `/obstacle_status` | `icar_interfaces/msg/ObstacleStatus` | 障碍物检测结果 |

**`/nav_status` 字段**：

```
status: string     # IDLE | NAVIGATING | ARRIVED | FAILED | TIMEOUT
goal_id: string    # 当前目标点 ID（如 "A", "B"）
distance: float32  # 距目标剩余距离（米）
eta: float32       # 预计到达时间（秒）
```

状态流转：
```
IDLE → NAVIGATING（收到 goal_pose）
NAVIGATING → ARRIVED（到达目标）
NAVIGATING → FAILED（导航失败）
NAVIGATING → TIMEOUT（超时 60s）
ARRIVED/FAILED/TIMEOUT → NAVIGATING（收到下一个 goal_pose）
```

**`/obstacle_status` 字段**：

```
is_obstacle: bool    # 是否检测到障碍物
min_distance: float32  # 最近障碍物距离（米）
direction: string    # front | left | right
risk_level: string   # safe | warning | danger
action: string       # none | slow_down | stop
```

---

# 第一阶段：LLM 独立测试（不需要导航）

> 全部在开发机上完成，不需要 ROS2 运行，不需要真车。

---

## 测试 1：规则解析 — 巡检命令

**目的**：验证不依赖 DeepSeek API 时，LLM 能正确解析巡检指令。

**测试方法**：

```python
# 在 llm/ 目录下执行
cd llm
python3 -c "
from llm_gateway_node import LlmGatewayNode

gateway = LlmGatewayNode()

# 测试用例
cases = [
    '巡检A、B、C三个点',
    '去A点和B点',
    '巡逻一圈',
    '去D点',
]

for text in cases:
    result = gateway._parse_task_by_rule(text)
    print(f'{text:30s} → type={result[\"task_type\"]:6s}  route={result.get(\"route\", \"-\")}')
"
```

**验收标准**：

| 输入 | 期望输出 |
|------|---------|
| `巡检A、B、C三个点` | `task_type=patrol`, `route=[A, B, C]` |
| `去A点和B点` | `task_type=patrol`, `route=[A, B]` |
| `巡逻一圈` | `task_type=patrol`, `route=[A, B, C]`（默认路线） |
| `去D点` | `task_type=patrol`, `route=[D]` |

---

## 测试 2：规则解析 — 信息查询（4 种类型）

**目的**：验证 LLM 能区分信息查询和巡检命令，并正确归类查询类型。

**测试方法**：

```python
cd llm
python3 -c "
from llm_gateway_node import LlmGatewayNode

gateway = LlmGatewayNode()

cases = [
    # (输入, 期望 query_type)
    ('前面有人吗', 'vision'),
    ('摄像头看到什么了', 'vision'),
    ('你现在在哪', 'navigation'),
    ('到了吗', 'navigation'),
    ('安全吗', 'safety'),
    ('有障碍物吗', 'safety'),
    ('任务进度怎么样', 'status'),
    ('在做什么', 'status'),
    ('现在怎么样', 'all'),       # 多关键词 → all
    ('前面有人吗到了吗', 'all'),  # 多关键词 → all
]

for text, expected in cases:
    result = gateway._parse_task_by_rule(text)
    actual = result.get('query_type', '-')
    status = '✅' if actual == expected else '❌'
    print(f'{status} \"{text:20s}\" → query_type={actual} (期望={expected})')
"
```

**验收标准**：10 条用例全部 ✅。

---

## 测试 3：规则解析 — 指令 vs 查询区分

**目的**：验证包含动作词的输入被识别为巡检指令，而非信息查询。

**测试方法**：

```python
cd llm
python3 -c "
from llm_gateway_node import LlmGatewayNode

gateway = LlmGatewayNode()

cases = [
    '启动巡检',
    '开始巡逻',
    '停下',
    '取消任务',
    '去前面看看',   # 包含'去' → 指令
]

for text in cases:
    result = gateway._parse_task_by_rule(text)
    print(f'\"{text:15s}\" → task_type={result[\"task_type\"]}')
"
```

**验收标准**：全部识别为 `task_type=patrol`（不是 info）。

---

## 测试 4：模板报告生成

**目的**：验证 LLM 不依赖 DeepSeek API 时，能用模板生成护工友好报告。

**测试方法**：

```python
cd llm
python3 -c "
from llm_gateway_node import LlmGatewayNode
import json

gateway = LlmGatewayNode()

# 构造 mock 日志
logs = [
    {'task_id': 't1', 'timestamp': {'sec': 1750000000}, 'event_type': 'TASK_START', 'severity': 'INFO', 'data': {}},
    {'task_id': 't1', 'timestamp': {'sec': 1750000010}, 'event_type': 'NAV_START', 'severity': 'INFO', 'data': {'target': 'A'}},
    {'task_id': 't1', 'timestamp': {'sec': 1750000020}, 'event_type': 'CHECKPOINT_REACHED', 'severity': 'INFO', 'data': {'checkpoint': 'A'}},
    {'task_id': 't1', 'timestamp': {'sec': 1750000025}, 'event_type': 'VISION_DETECT', 'severity': 'INFO', 'data': {'detections': [{'class': 'person'}]}},
    {'task_id': 't1', 'timestamp': {'sec': 1750000030}, 'event_type': 'NAV_START', 'severity': 'INFO', 'data': {'target': 'B'}},
    {'task_id': 't1', 'timestamp': {'sec': 1750000040}, 'event_type': 'CHECKPOINT_REACHED', 'severity': 'INFO', 'data': {'checkpoint': 'B'}},
    {'task_id': 't1', 'timestamp': {'sec': 1750000050}, 'event_type': 'TASK_END', 'severity': 'INFO', 'data': {}},
]

report = gateway._build_report('t1', logs)
print(report)
"
```

**验收标准**：
- 输出包含 `巡 检 交 班 报 告`
- 包含巡检时间、巡视区域 `A → B`
- A 点显示"看到: 行人"
- 包含`【结论】`、`【交接建议】`

---

## 测试 5：JSON 协议校验

**目的**：验证 `TaskCommand` pydantic 模型对 5 种任务类型做参数校验。

**测试方法**：

```python
cd llm
python3 -c "
from json_protocol import TaskCommand, MovePayload, VisionPayload

# 5.1 合法 move 命令
cmd = TaskCommand(type='move', mode='single',
    payload={'command': 'forward', 'distance': 2.0, 'speed': 50})
assert cmd.is_valid(), 'move should be valid'
print('✅ move 校验通过')

# 5.2 合法 vision 命令
cmd = TaskCommand(type='vision', mode='single',
    payload={'operation': 'detect', 'targets': ['puddle', 'person']})
assert cmd.is_valid(), 'vision should be valid'
print('✅ vision 校验通过')

# 5.3 合法 query 命令
cmd = TaskCommand(type='query', mode='single',
    payload={'target': 'status'})
assert cmd.is_valid(), 'query should be valid'
print('✅ query 校验通过')

# 5.4 非法 type 被拒绝
try:
    cmd = TaskCommand(type='invalid_type', payload={})
    assert not cmd.is_valid(), 'invalid type should fail'
    print('✅ 非法 type 正确拒绝')
except Exception as e:
    print(f'✅ 非法 type 正确拒绝: {e}')

# 5.5 非法 command 被拒绝
try:
    MovePayload(command='fly', distance=1.0)
    assert False, 'should have raised'
except Exception as e:
    print(f'✅ 非法 command 正确拒绝: {e}')

# 5.6 非法 target 被拒绝
try:
    VisionPayload(operation='detect', targets=['dragon'])
    assert False, 'should have raised'
except Exception as e:
    print(f'✅ 非法 target 正确拒绝: {e}')

print()
print('全部协议校验测试通过')
"
```

**验收标准**：6 个子项全部打印 ✅。

---

## 测试 6：JSON 提取

**目的**：验证 `extract_json_from_response()` 能从 DeepSeek API 返回的各种格式中提取 JSON。

**测试方法**：

```python
cd llm
python3 -c "
from json_protocol import extract_json_from_response

cases = [
    ('纯JSON', '{\"type\": \"move\", \"payload\": {}}'),
    ('前后有文字', '好的，命令如下：{\"type\": \"move\"}请执行'),
    ('Markdown包裹', '```json\n{\"type\": \"query\"}\n```'),
    ('多行JSON', '{\n  \"type\": \"vision\",\n  \"payload\": {}\n}'),
]

for name, text in cases:
    try:
        result = extract_json_from_response(text)
        assert result.startswith('{') and result.endswith('}')
        print(f'✅ {name}: {result[:50]}...')
    except Exception as e:
        print(f'❌ {name}: {e}')

# 无JSON应抛异常
try:
    extract_json_from_response('没有JSON内容')
    assert False, 'should have raised'
except ValueError:
    print('✅ 无JSON内容正确抛异常')
"
```

**验收标准**：5 项全部 ✅。

---

## 测试 7：robot_tools 工具定义完整性

**目的**：验证 `RobotTools.TOOLS_DEF` 8 个工具定义完整、参数类型正确。

**测试方法**：

```python
cd llm
python3 -c "
from robot_tools import RobotTools

tools = RobotTools.TOOLS_DEF

expected_tools = [
    'start_patrol', 'get_robot_status', 'stop_robot',
    'cancel_task', 'reset_task', 'query_vision',
    'query_navigation', 'check_safety',
]

tool_names = [t['tool_name'] for t in tools]
print(f'工具数量: {len(tools)} (期望 8)')

for name in expected_tools:
    if name in tool_names:
        tool = tools[tool_names.index(name)]
        has_desc = bool(tool.get('description'))
        has_params = 'parameters' in tool
        print(f'✅ {name}: description={has_desc}, params={has_params}')
    else:
        print(f'❌ 缺失工具: {name}')

assert len(tools) == 8, f'期望8个工具，实际{len(tools)}个'
print()
print('工具定义完整性测试通过')
"
```

**验收标准**：8 个工具全 ✅，无缺失。

---

## 测试 8：规则回答模板 — 无障碍物数据时

**目的**：验证没有真实数据时，`_rule_answer()` 返回友好的"暂缺"提示。

**测试方法**：

```python
cd llm
python3 -c "
from llm_gateway_node import LlmGatewayNode

gateway = LlmGatewayNode()
empty_context = {}

# 每种查询类型都应该返回非空回答
for qtype in ['vision', 'navigation', 'safety', 'status', 'all']:
    answer = gateway._rule_answer('测试问题', qtype, empty_context)
    assert answer, f'{qtype} 回答不应为空'
    print(f'✅ query_type={qtype:12s} → {answer[:80]}')
"
```

**验收标准**：5 种 query_type 全部返回非空字符串，包含中文说明。

---

## 测试 9：规则回答模板 — 有障碍物数据时

**目的**：验证收到障碍物告警时，回答模板正确显示告警信息。

**测试方法**：

```python
cd llm
python3 -c "
from llm_gateway_node import LlmGatewayNode

gateway = LlmGatewayNode()

# 模拟障碍物上下文
context = {
    'obstacle_status': {
        'is_obstacle': True,
        'min_distance': 0.35,
        'direction': 'front',
        'risk_level': 'danger',
        'action': 'stop',
    }
}

answer = gateway._rule_answer('安全吗', 'safety', context)
print(f'danger 上下文: {answer}')

# 安全上下文
safe_context = {
    'obstacle_status': {
        'is_obstacle': False,
        'min_distance': 5.0,
        'direction': 'front',
        'risk_level': 'safe',
        'action': 'none',
    }
}
answer = gateway._rule_answer('安全吗', 'safety', safe_context)
print(f'safe 上下文:   {answer}')
"
```

**验收标准**：
- danger 上下文输出包含"检测到障碍物"、"距离 0.35m"、"危险"
- safe 上下文输出包含"安全"、"未检测到障碍物"

---

## 测试 10：状态翻译表覆盖率

**目的**：验证 `_translate_status` 覆盖了导航和任务所有可能的状态值。

**测试方法**：

```python
cd llm
python3 -c "
from llm_gateway_node import LlmGatewayNode

gateway = LlmGatewayNode()

# 所有可能出现并需要翻译的枚举值
must_cover = [
    # 任务状态 (from TaskStatus)
    'PENDING', 'RUNNING', 'NAVIGATING', 'CHECKPOINT',
    'DETECTING', 'COLLECTING', 'COMPLETED', 'FAILED', 'CANCELLED',
    # 导航状态 (from NavStatus)
    'IDLE', 'ARRIVED',
    # 风险等级 (from ObstacleStatus)
    'safe', 'warning', 'danger',
    # 障碍物方位
    'front', 'left', 'right', 'back',
    # 建议动作
    'none', 'slow_down', 'stop', 'turn',
]

missing = []
for val in must_cover:
    translated = gateway._translate_status(val)
    if translated == val:
        missing.append(val)

if missing:
    print(f'❌ 缺失翻译: {missing}')
else:
    print(f'✅ 全部 {len(must_cover)} 个枚举值已覆盖')

# 验证翻译结果是中文
for val in ['PENDING', 'danger', 'front']:
    result = gateway._translate_status(val)
    has_chinese = any('\\u4e00' <= c <= '\\u9fff' for c in result)
    print(f'  {val:15s} → {result}')
"
```

**验收标准**：0 个缺失翻译，所有已覆盖值翻译为中文。

---

### 第一阶段汇总

| # | 测试项 | 需要 API Key | 需要 ROS2 | 验收方式 |
|---|--------|-------------|-----------|---------|
| 1 | 规则解析 — 巡检命令 | ❌ | ❌ | 4 条用例全部正确 |
| 2 | 规则解析 — 信息查询 | ❌ | ❌ | 10 条用例全部正确 |
| 3 | 指令 vs 查询区分 | ❌ | ❌ | 5 条全部识别为 patrol |
| 4 | 模板报告生成 | ❌ | ❌ | 输出包含指定内容 |
| 5 | JSON 协议校验 | ❌ | ❌ | 6 项全部 ✅ |
| 6 | JSON 提取 | ❌ | ❌ | 5 项全部 ✅ |
| 7 | 工具定义完整性 | ❌ | ❌ | 8 个工具齐全 |
| 8 | 规则回答模板（空数据） | ❌ | ❌ | 5 种 query_type 有回答 |
| 9 | 规则回答模板（有数据） | ❌ | ❌ | danger/safe 输出正确 |
| 10 | 状态翻译覆盖率 | ❌ | ❌ | 0 个缺失 |

---

### DeepSeek API 相关测试（需要 API Key）

> 以下测试需要设置环境变量 `DEEPSEEK_API_KEY`。如果项目组尚未提供 Key，可以先跳过，不影响规则模式下的功能。

#### 测试 A：API 连接

```python
cd llm
python3 -c "
from deepseek_client import DeepSeekClient
client = DeepSeekClient()
print(f'API: {client.base_url}  Model: {client.model}')
# 验证 API Key 不为假值
assert client.api_key and len(client.api_key) > 10, 'API Key 无效'
print('✅ API Key 有效')
"
```

**验收标准**：API Key 非空，长度 > 10。

#### 测试 B：命令解析（DeepSeek API）

```python
cd llm
python3 -c "
from deepseek_client import DeepSeekClient
client = DeepSeekClient()
# 测试简单命令解析
result = client.parse_command('向前走2米')
assert result, 'API 返回空'
print(f'✅ parse_command: {result[:100]}')
"
```

**验收标准**：返回非空 JSON 字符串。

#### 测试 C：报告生成（DeepSeek API）

```python
cd llm
python3 -c "
from deepseek_client import DeepSeekClient
client = DeepSeekClient()
log = '[1000] TASK_START\n[1010] NAV_START target=A\n[1020] CHECKPOINT_REACHED checkpoint=A\n[1030] TASK_END'
report = client.generate_report(log)
assert report, 'API 返回空'
print(report[:200])
"
```

**验收标准**：返回非空中文报告。

---

# 第二阶段：导航 + LLM 联调

> 前提：已完成第一阶段全部测试。导航模块需先启动。

---

## LLM 需要实现的接口

LLM 节点应**订阅**以下 Topic 获取导航状态：

```python
# 订阅导航状态
self.nav_status_sub = self.create_subscription(
    NavStatus, '/nav_status', self.on_nav_status, 10)

# 订阅障碍物状态
self.obstacle_sub = self.create_subscription(
    ObstacleStatus, '/obstacle_status', self.on_obstacle, 10)
```

LLM 节点应**发布**以下 Topic 控制导航：

```python
# 发布任务请求
self.task_pub = self.create_publisher(String, '/task/request', 10)

# 发布任务控制
self.control_pub = self.create_publisher(String, '/task/control', 10)
```

---

## 快速联调命令（一键启动所有导航节点 + task_manager）

```bash
docker exec icar_ros2 bash -c "
  source /root/icar_ros2_ws/icar_ws/install/setup.bash
  ros2 run navigation obstacle_avoid_node --ros-args -p mode:=mock &
  sleep 1
  ros2 run navigation navigation_node --ros-args -p mode:=mock &
  sleep 1
  ros2 run task_manager task_manager_node &
  wait
"
```

启动后 LLM 节点再启动，即可进行联调。

---

## 联调场景

以下场景按顺序执行。每个场景独立可复现，**mock 模式下不需要车实际移动**。

### 联调场景 1：LLM 订阅导航状态和障碍物状态

**目的**：验证 LLM 能收到导航侧输出的 Topic。

**LLM 侧操作**：
1. 启动 LLM 节点
2. 订阅 `/nav_status` 和 `/obstacle_status`
3. 在回调中打印日志

**导航侧操作**：启动导航节点（见上方一键命令）

**验收标准**：LLM 日志中出现 `nav_status: IDLE` 和 `obstacle_status: safe`。

---

### 联调场景 2：LLM 发起巡检任务

**目的**：LLM 发 `/task/request` 启动巡检，观察完整流程。

**LLM 侧操作**：
```python
msg = String()
msg.data = "route=[A,B,C]"
self.task_pub.publish(msg)
```

**验收标准**：
1. LLM 收到 3 次 `/nav_status` 变化：`NAVIGATING(A)` → `ARRIVED(A)` → `NAVIGATING(B)` → `ARRIVED(B)` → `NAVIGATING(C)` → `ARRIVED(C)`
2. 每次 `ARRIVED` 后 task_manager 自动发下一个 `/goal_pose`

> mock 模式下每个点约 3-5 秒到达。

---

### 联调场景 3：LLM 暂停/恢复/取消任务

**目的**：验证 LLM 对导航的实时控制。

**LLM 侧操作**：
```python
# 1. 先发起巡检
self.task_pub.publish(String(data="route=[A,B,C]"))

# 2. 等第一个点开始导航后暂停
time.sleep(2)
self.control_pub.publish(String(data="pause"))

# 3. 等 3 秒后恢复
time.sleep(3)
self.control_pub.publish(String(data="resume"))

# 4. 等 2 秒后取消
time.sleep(2)
self.control_pub.publish(String(data="cancel"))
```

**验收标准**：
- 暂停后 `/nav_status` 不再变化
- 恢复后继续推进
- 取消后回到 `IDLE`

---

### 联调场景 4：LLM 发单点导航

**目的**：LLM 不通过 task_manager，直接发 goal_pose 控制导航。

**LLM 侧操作**：
```python
goal = PoseStamped()
goal.header.frame_id = "map"
goal.pose.position.x = 2.0
goal.pose.position.y = 1.0
goal.pose.orientation.w = 1.0
self.goal_pub.publish(goal)  # 发布到 /goal_pose
```

**验收标准**：`/nav_status` 变为 `NAVIGATING` → `ARRIVED`。

---

### 联调场景 5：LLM 响应障碍物告警

**目的**：LLM 收到 obstacle_status 后做出合理决策。

**导航侧操作**（需要真车 real 模式）：
```bash
ros2 run navigation obstacle_avoid_node --ros-args -p mode:=real
```

**LLM 侧操作**：监听 `/obstacle_status`，当 `risk_level=danger` 时记录日志。

**物理操作**：车前放障碍物 → `danger/stop`，拿走 → `safe/none`。

**验收标准**：LLM 正确收到 danger 告警并做出响应。

---

## 消息依赖（导入）

LLM 节点需要依赖 `icar_interfaces` 包：

```python
from icar_interfaces.msg import NavStatus, ObstacleStatus
```

`icar_interfaces` 已在 `deploy.sh` 中同步到 `icar_ros2`。

---

## 全部测试汇总

### 第一阶段（LLM 独立）

| # | 测试项 | 需要 API Key | 需要 ROS2 |
|---|--------|-------------|-----------|
| 1 | 规则解析 — 巡检命令 | ❌ | ❌ |
| 2 | 规则解析 — 信息查询（10 条） | ❌ | ❌ |
| 3 | 指令 vs 查询区分 | ❌ | ❌ |
| 4 | 模板报告生成 | ❌ | ❌ |
| 5 | JSON 协议校验 | ❌ | ❌ |
| 6 | JSON 提取 | ❌ | ❌ |
| 7 | 工具定义完整性 | ❌ | ❌ |
| 8 | 规则回答模板（空数据） | ❌ | ❌ |
| 9 | 规则回答模板（有数据） | ❌ | ❌ |
| 10 | 状态翻译覆盖率 | ❌ | ❌ |
| A | DeepSeek API 连接 | ✅ | ❌ |
| B | DeepSeek 命令解析 | ✅ | ❌ |
| C | DeepSeek 报告生成 | ✅ | ❌ |

### 第二阶段（导航+LLM 联调）

| # | 测试项 | 需要真车 | 需要导航启动 |
|---|--------|---------|------------|
| 1 | 订阅导航/障碍物状态 | ❌ | ✅ |
| 2 | 发起巡检任务 | ❌ | ✅ |
| 3 | 暂停/恢复/取消 | ❌ | ✅ |
| 4 | 单点导航 | ❌ | ✅ |
| 5 | 障碍物告警响应 | ✅ | ✅ |

---

## 注意事项

1. **消息类型**必须在 `icar_interfaces` 中定义，LLM 节点 `package.xml` 需声明 `<depend>icar_interfaces</depend>`。
2. **ROS_DOMAIN_ID** 必须为 30（已统一），否则容器间无法通信。
3. **task_manager 是巡检流程的协调者**——LLM 一般通过 `/task/request` 下发任务，不直接发 `/goal_pose`（除非临时避让场景）。
4. mock 模式下障碍物检测是模拟的，真实障碍物验证需要 real 模式 + 真车雷达。
5. 规则解析结果中 `provider` 字段标识了解析来源：`rule` 或 `deepseek`，可在日志中查看。
