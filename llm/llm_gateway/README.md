# llm_gateway — ROS2 LLM 网关（合并版）

DeepSeek API 优先，规则兜底。无网络/无 API Key 时自动降级为规则解析。

## 启动

```bash
ros2 run llm_gateway llm_gateway_node
```

## 参数

| 参数 | 默认值 | 说明 |
|------|--------|------|
| `provider` | `auto` | `auto` (有 API 就用) / `deepseek` (强制 API) / `rule` (强制规则) |
| `default_route` | `["A","B","C"]` | 用户未指定路线时的默认巡检点 |
| `max_logs_per_task` | `200` | 每个任务缓存日志条数上限 |

## 提供的 ROS2 Service

| Service | 类型 | 说明 |
|---------|------|------|
| `/llm/parse_task` | `icar_interfaces/srv/ParseTask` | 自然语言 → 巡检任务 JSON |
| `/llm/generate_report` | `icar_interfaces/srv/GenerateReport` | 任务日志 → 巡检报告文本 |

## 订阅的 Topic

| Topic | 类型 | 说明 |
|-------|------|------|
| `/task/log` | `icar_interfaces/msg/TaskLog` | 累积任务日志用于报告生成 |

## 输出格式示例

### /llm/parse_task 返回

```json
{
  "task_type": "patrol",
  "route": ["A", "B", "C"],
  "actions": ["navigate", "avoid_obstacle", "detect_object", "collect_sensor"],
  "safety_rule": "遇到障碍物停止并等待处理",
  "params": {
    "source": "llm_gateway",
    "provider": "deepseek",
    "raw_text": "巡检实验室一圈，经过A/B/C点"
  }
}
```

## 环境变量（使用 DeepSeek API 时）

```bash
export DEEPSEEK_API_KEY="your_key"
export DEEPSEEK_BASE_URL="https://api.deepseek.com"   # 可选
export DEEPSEEK_MODEL="deepseek-chat"                  # 可选
```

## 架构

```
voice_command_router ──/llm/parse_task──▶ llm_gateway_node
                                               │
task_manager ────/task/log────────────────────▶│
                                               │
                     /llm/generate_report ◀────┤
```

- **安全约束**：LLM 网关不发布 `/cmd_vel`，所有底盘控制经过 `task_manager_node`。
- **API 不可用时**：自动降级为中文关键词规则解析，确保集成测试可运行。
- **语音模块**通过 `/llm/parse_task` 获取解析结果，自行发布 `/task/request` 给 task_manager。
