# LLM 车端接口交接文档

本文档给负责 LLM 模块的同学使用。车端已经提供安全的任务入口，LLM 侧只需要把这些 ROS2 Topic/Service 包装成工具调用，不要直接发布 `/cmd_vel`。

## 接入边界

LLM 侧负责：

- 将用户自然语言解析成结构化任务。
- 根据任务意图调用车端接口。
- 订阅状态、日志、传感器和视觉结果，用于回复用户或生成报告。

车端负责：

- 接收结构化任务并执行巡检状态机。
- 统一处理停车、取消、复位和状态查询。
- 在障碍物、传感器异常、人工停止时发布安全停车。

禁止 LLM 侧直接做的事：

- 不直接发布 `/cmd_vel`。
- 不绕过 `task_manager_node` 直接控制底盘。
- 不自行判断安全阈值覆盖车端安全模块。

## 推荐暴露给 LLM 的 Tools

### 1. `start_patrol`

用途：启动巡检任务。

ROS2 映射：

- Topic: `/task/request`
- Type: `icar_interfaces/msg/TaskRequest`
- Publisher: `llm_gateway_node`
- Subscriber: `task_manager_node`

Tool 参数：

```json
{
  "task_type": "patrol",
  "route": ["A", "B", "C"],
  "params": {
    "source": "llm",
    "user_text": "巡检 A、B、C 三个点"
  }
}
```

ROS2 消息字段：

- `task_type`: 建议固定为 `patrol` 或 `inspect`。
- `route`: 巡检点名称数组，如 `["A", "B", "C"]`。
- `params`: JSON 字符串，建议包含 `source=llm` 和原始用户输入。

注意：

- 当前 `task_manager_node` 只在 `PENDING` 状态接受新任务。
- 若当前任务正在执行，LLM 应先调用 `get_robot_status`，必要时再调用 `cancel_task`。

### 2. `get_robot_status`

用途：查询当前任务状态。

ROS2 映射：

- Service: `/task/control`
- Type: `icar_interfaces/srv/TaskControl`
- Server: `task_manager_node`
- Client: `llm_gateway_node`

请求：

```json
{
  "action": "get_status",
  "reason": "user asked current robot status",
  "payload_json": "{}"
}
```

响应：

```json
{
  "success": true,
  "message": "status returned",
  "task_id": "task_xxxxxxxx",
  "status": "NAVIGATING",
  "data_json": "{\"task_id\":\"task_xxxxxxxx\",\"status\":\"NAVIGATING\",\"route\":[\"A\",\"B\"],\"current_step\":1,\"total_steps\":2,\"emergency_stop_active\":false}"
}
```

状态枚举：

- `PENDING`: 等待任务。
- `RUNNING`: 任务已接收。
- `NAVIGATING`: 正在导航到巡检点。
- `CHECKPOINT`: 到达巡检点。
- `DETECTING`: 正在视觉检测。
- `COLLECTING`: 正在采集传感器数据。
- `COMPLETED`: 任务完成。
- `FAILED`: 任务失败。
- `CANCELLED`: 任务取消。

### 3. `stop_robot`

用途：立即停车，进入安全停止状态。适用于用户说“停下”“紧急停止”“别动”等。

ROS2 映射：

- Service: `/task/control`
- Type: `icar_interfaces/srv/TaskControl`

请求：

```json
{
  "action": "stop",
  "reason": "user requested emergency stop",
  "payload_json": "{\"source\":\"llm\"}"
}
```

行为：

- `task_manager_node` 发布一次零速度 `/cmd_vel`。
- `emergency_stop_active` 置为 `true`。
- 状态机暂停继续动作，等待 `reset_task`。

### 4. `cancel_task`

用途：取消当前巡检任务，并停车。适用于用户说“取消这次巡检”“任务不要做了”。

ROS2 映射：

- Service: `/task/control`
- Type: `icar_interfaces/srv/TaskControl`

请求：

```json
{
  "action": "cancel",
  "reason": "user cancelled patrol",
  "payload_json": "{\"source\":\"llm\"}"
}
```

行为：

- 若当前状态是 `RUNNING/NAVIGATING/CHECKPOINT/DETECTING/COLLECTING`，切换到 `CANCELLED`。
- 同时发布零速度 `/cmd_vel`。
- 若当前没有运行任务，返回 `success=false`。

### 5. `reset_task`

用途：在 `FAILED/CANCELLED/COMPLETED` 后复位任务状态，使小车可以接收新任务。

ROS2 映射：

- Service: `/task/control`
- Type: `icar_interfaces/srv/TaskControl`

请求：

```json
{
  "action": "reset",
  "reason": "operator confirmed reset",
  "payload_json": "{\"source\":\"llm\"}"
}
```

行为：

- 状态切回 `PENDING`。
- 清除 `emergency_stop_active`。
- 之后可以重新发布 `/task/request`。

## LLM 可订阅的信息

LLM 侧可以订阅以下 Topic 做状态理解和报告生成：

| Topic | 类型 | 用途 |
| --- | --- | --- |
| `/task/status` | `icar_interfaces/msg/TaskStatus` | 当前任务状态 |
| `/task/log` | `icar_interfaces/msg/TaskLog` | 巡检过程、异常、检测、传感器记录 |
| `/obstacle_status` | `icar_interfaces/msg/ObstacleStatus` | 前方障碍物风险 |
| `/sensor/env_data` | `icar_interfaces/msg/EnvData` | 环境传感器实时数据 |
| `/sensor/alert` | `icar_interfaces/msg/SensorAlert` | 环境异常告警 |
| `/vision/detections` | `icar_interfaces/msg/DetectionArray` | 视觉检测结果 |

## Service 定义

```srv
# icar_interfaces/srv/TaskControl.srv
string action
string reason
string payload_json
---
bool success
string message
string task_id
string status
string data_json
```

支持的 `action`：

- `get_status` 或 `status`
- `stop` 或 `emergency_stop`
- `cancel`
- `reset`

## ROS2 调用示例

查询状态：

```bash
ros2 service call /task/control icar_interfaces/srv/TaskControl "{action: get_status, reason: llm_status_query, payload_json: '{}'}"
```

紧急停车：

```bash
ros2 service call /task/control icar_interfaces/srv/TaskControl "{action: stop, reason: user_stop, payload_json: '{\"source\":\"llm\"}'}"
```

取消任务：

```bash
ros2 service call /task/control icar_interfaces/srv/TaskControl "{action: cancel, reason: user_cancel, payload_json: '{\"source\":\"llm\"}'}"
```

下发巡检任务：

```bash
ros2 topic pub --once /task/request icar_interfaces/msg/TaskRequest "{task_type: patrol, route: [A, B, C], params: '{\"source\":\"llm\"}'}"
```

## 建议给 LLM 的调用规则

- 用户要求“巡检/去某几个点”：先调用 `get_robot_status`，状态为 `PENDING` 时再调用 `start_patrol`。
- 用户要求“停下/紧急停止”：立即调用 `stop_robot`。
- 用户要求“取消任务”：调用 `cancel_task`。
- 用户要求“重新开始/恢复接收任务”：只有在人工确认安全后调用 `reset_task`。
- 任务执行中如果 `/obstacle_status` 为 `danger`，LLM 只负责告知用户，不要尝试绕过安全停车。

## 当前限制

- 本接口负责让 LLM 安全接入任务调度，不负责 LLM 模型、提示词和工具调用框架。
- 真车能否完整巡检还依赖真实 SLAM、导航、底盘控制链路是否接通。
- 第一版只提供任务级控制，不提供连续手动驾驶 tool。
