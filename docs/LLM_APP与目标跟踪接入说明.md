# LLM App 指挥与目标跟踪接入说明

日期：2026-07-13

## 已接通的链路

```text
Flutter 智能任务页
  -> WebSocket /ws/control
  -> app_bridge_node
  -> /llm/user_command
  -> llm_gateway_node (tool_mode=true)
  -> task_manager / 视觉跟踪 / 状态查询工具
  -> /llm/response
  -> app_bridge_node
  -> Flutter 执行结果卡片
```

App 请求格式：

```json
{
  "action": "llm_command",
  "request_id": "app_xxx",
  "input_text": "巡检 A、B、C 三个点"
}
```

响应格式：

```json
{
  "topic": "llm_response",
  "request_id": "app_xxx",
  "success": true,
  "tool_name": "start_patrol",
  "provider": "rule",
  "reply": "巡检任务已下发，小车将按安全任务流程执行。"
}
```

`request_id` 用于并发请求时把响应对应回正确的聊天气泡。

## 当前可执行工具

- `start_patrol`：向 `/task/request` 下发巡检任务。
- `get_robot_status`：查询任务状态。
- `stop_robot`：调用 `/task/control`，并锁存 `/safety_stop=true`。
- `cancel_task`：取消任务、停车并保持安全停止。
- `reset_task`：在终态或待机急停状态下复位，并解除安全停止；必须明确说“确认复位”。
- `query_vision`：读取最近的视觉检测。
- `query_navigation`：读取导航状态。
- `check_safety`：读取障碍物与风险状态。
- `start_tracking`：发布视觉跟踪启动命令。
- `stop_tracking`：停止跟踪并输出零速度。
- `play_audio`、`download_audio`：音频工具。

明确指令优先使用本地规则，断网也可执行。未命中规则时，配置了
`DEEPSEEK_API_KEY` 才会调用 DeepSeek；紧急停止不会等待云端模型。

此外，`app_bridge_node` 会直接识别“立即停下、急停、别动”等明确措辞，先发布
零速度并锁存 `/safety_stop=true`，之后才把请求交给 LLM。急停状态下
`task_manager_node` 拒绝所有新任务，必须“确认复位”后才能继续。

## 目标跟踪安全链路

```text
target_tracker_node
  -> /vision/target_cmd_vel
  -> velocity_mux
  -> /cmd_vel
```

速度优先级为：安全停止 > App 人工控制 > 目标跟踪 > 手柄/导航（以
`velocity_mux_node.py` 当前顺序为准）。跟踪消息超时后仲裁器自动丢弃该速度源；
目标丢失时跟踪节点发布零速度。

注意：启用跟踪会让真车移动。联调前应架空车轮或留出空场地，并确保 App
停止按钮、实体底盘复位和 `/safety_stop` 均可用。

## 启动与部署

`scripts/icar_startup.sh` 会按 Git revision 同步并编译：

- `icar_interfaces`
- `app_control`
- `task_manager`
- `llm_gateway`

`scripts/start_car_app_stack.sh` 会启动：

1. `velocity_mux_node`
2. `app_bridge_node`
3. Web 网关

`scripts/icar_startup.sh` 随后在 `icar_ros2` 容器中单独启动
`task_manager_node`、`obstacle_avoid_node --mode real` 和
`llm_gateway_node tool_mode:=true`，避免两个容器重复运行同名控制节点。

未配置 API Key 时，巡检、停车、查询和目标跟踪等明确指令仍可通过本地规则工作。

## 非运动验收

```bash
python3 -m unittest discover -s task_manager/tests -p 'test_*.py'
flutter analyze
flutter test
bash -n scripts/icar_startup.sh scripts/start_car_app_stack.sh
```

真车运动验收必须单独进行，且不要把“Topic 存在”当作成功标准；至少检查：

- `/vision/target_cmd_vel` 有 1 个订阅者（`velocity_mux`）。
- `/llm/user_command` 有 LLM 网关订阅者。
- `/llm/response` 有 App bridge 订阅者。
- `/task/control` 服务存在。
- 发送停止后 `/safety_stop` 为 `true`，复位前跟踪和导航均不能驱动车轮。
