# Flutter APP 本地改动说明（dev 分支，未提交）

## 改动总览

| 文件 | 改动类型 | 说明 |
|------|---------|------|
| `lib/services/car_tcp_service.dart` | 增强 | WebSocket 通信层：新增 7 个 ROS2 状态流 + 路由 + 订阅 |
| `lib/services/car_controller.dart` | 增强 | 状态管理：对接车端双向桥，JSON 指令格式 |
| `lib/pages/control_page.dart` | 增强 | 遥控页面：心跳保活 + 松手即停 |
| `lib/pages/sensor_page.dart` | 增强 | 传感器页面：对接真实传感器数据 |
| `lib/pages/status_page.dart` | 增强 | 状态页面：对接真实导航/障碍物数据 |
| `lib/main.dart` | 修改 | 入口：IP 迁移 + 兼容升级 |

---

## 1. `lib/services/car_tcp_service.dart` — WebSocket 通信层

### 新增 7 个 ROS2 状态流

```dart
final _obstacleController = StreamController<Map<String, dynamic>>.broadcast();
final _navStatusController = StreamController<Map<String, dynamic>>.broadcast();
final _taskStatusController = StreamController<Map<String, dynamic>>.broadcast();
final _taskLogController = StreamController<Map<String, dynamic>>.broadcast();
final _sensorEnvController = StreamController<Map<String, dynamic>>.broadcast();
final _sensorAlertController = StreamController<Map<String, dynamic>>.broadcast();
final _trackingStatusController = StreamController<Map<String, dynamic>>.broadcast();
```

### 新增 `_routeJsonMessage` 路由分支

```dart
case 'obstacle_status':    _obstacleController.add(json);
case 'nav_status':          _navStatusController.add(json);
case 'task_status':         _taskStatusController.add(json);
case 'task_log':            _taskLogController.add(json);
case 'sensor_env_data':     _sensorEnvController.add(json);
case 'sensor_alert':        _sensorAlertController.add(json);
case 'tracking_status':     _trackingStatusController.add(json);
case 'subscription':
case 'command_ack':         onLog?.call('← $json');  // 仅打日志
case 'error':               onError?.call(...);       // 触发错误回调
```

### 新增 `subscribeBridgeTopics()`

连接成功后批量订阅 9 个 topic（视频仍走独立 MJPEG HTTP 流）：

```dart
void subscribeBridgeTopics() {
  for (final topic in const [
    'obstacle_status', 'nav_status', 'task_status', 'task_log',
    'sensor_env_data', 'sensor_alert', 'tracking_status',
    'detections', 'capture_status',
  ]) {
    subscribeTopic(topic);
  }
}
```

### 其他

- 默认 IP `192.168.137.218` → `192.168.137.117`
- `dispose()` 补全 7 个新 Controller 的 close

---

## 2. `lib/services/car_controller.dart` — 状态管理

### 连接后自动订阅

```dart
// 之前（已注释）
// _service.subscribeVisionTopics();

// 现在
_service.subscribeBridgeTopics();
```

### 指令格式改为 JSON

```dart
// 之前：纯文本
_service.send(cmd);

// 现在：JSON 带速度（车端会做二次限幅，stop 不受速度影响）
_service.sendJson({'command': cmd, 'speed': _speed});
```

### 新增 6 个 ROS2 状态缓存

```dart
Map<String, dynamic>? _latestObstacleStatus;
Map<String, dynamic>? _latestNavStatus;
Map<String, dynamic>? _latestTaskStatus;
Map<String, dynamic>? _latestSensorEnv;
Map<String, dynamic>? _latestSensorAlert;
Map<String, dynamic>? _latestTrackingStatus;
final List<Map<String, dynamic>> _taskLogs = [];
```

### 新增回调方法

- `_updateBridgeState(kind, data)` — 统一处理 bridge 推送的状态更新
- `_onTaskLog(data)` — 缓存最近 200 条任务日志
- `_onSensorAlert(data)` — 传感器告警写入消息日志

### 其他

- 默认 IP `192.168.137.218` → `192.168.137.117`

---

## 3. `lib/pages/control_page.dart` — 遥控页面

### 心跳保活机制

车端 `app_bridge_node` 有 350ms 命令超时看门狗（超时自动停止），因此按住按钮时需持续发送指令：

```dart
// 按下：启动 100ms 周期心跳
_motionHeartbeat = Timer.periodic(const Duration(milliseconds: 100), (_) {
  if (_activeDirection.isNotEmpty && _ctrl.isConnected) {
    _ctrl.sendCommand(_activeDirection);
  }
});

// 松开：停止心跳 + 发送 stop
_motionHeartbeat?.cancel();
_ctrl.sendCommand('stop');
```

- 新增 `dart:async` import
- `dispose()` 中取消心跳

---

## 4. `lib/pages/sensor_page.dart` — 传感器页面

### 对接真实传感器数据

- 监听 `CarController`，优先使用 `latestSensorEnv` 真实数据
- 真实数据可用时跳过随机模拟
- 传感器告警时动态更新阈值显示
- 新增 `import '../services/car_controller.dart'`

---

## 5. `lib/pages/status_page.dart` — 状态页面

### 对接真实导航/障碍物数据

- 从 `latestNavStatus` 取：导航状态、进度条、剩余距离
- 从 `latestObstacleStatus` 取：障碍物信息（风险等级/距离）
- 移除手动切换导航模式的按钮，改为显示真实状态
- 速度显示改为基于 `currentDirection` 和 `speed` 计算
- 新增 `import '../services/car_controller.dart'`

---

## 6. `lib/main.dart` — 入口

### IP 自动迁移

```dart
// 升级 APK 时自动将旧 IP 迁移到新 IP
final carHost = savedHost == null || savedHost == '192.168.137.218'
    ? '192.168.137.117'
    : savedHost;
```

- 引导文字中的 IP 同步更新

---

## APP ↔ 车端协议约定

### APP → 车端

| 功能 | 格式 |
|------|------|
| 运动控制 | `{"command":"forward","speed":0.5}` |
| 停止 | `{"command":"stop","speed":0.5}` |
| 订阅 topic | `{"subscribe":"obstacle_status"}` |
| LLM 解析 | `{"action":"parse_task","input_text":"..."}` |
| 任务下发 | `{"action":"task_request","task":{...}}` |
| 报告生成 | `{"action":"generate_report","task_id":"..."}` |
| 目标追踪 | `{"action":"tracking","command":"start","target_classes":["person"]}` |
| 截图 | `{"action":"capture_once","tag":"manual"}` |
| 导航目标 | `{"action":"goal_pose","x":1.0,"y":2.0,"yaw":0.0}` |

### 车端 → APP（JSON，含 `topic` 字段）

| topic | 说明 | 频率 |
|-------|------|------|
| `obstacle_status` | 障碍物检测（距离/方位/风险等级） | 按需 |
| `nav_status` | 导航状态（进度/剩余距离） | 按需 |
| `task_status` | 任务状态（当前步骤/总步骤） | 状态变化时 |
| `task_log` | 任务日志（事件类型/数据） | 事件触发 |
| `sensor_env_data` | 环境传感器（温湿度/烟雾/PM2.5/光照/气压） | 1 Hz |
| `sensor_alert` | 传感器告警 | 异常触发 |
| `detections` | 视觉检测结果（类别/置信度/边界框） | 10 Hz |
| `capture_status` | 截图状态 | 按需 |
| `tracking_status` | 目标追踪状态 | 按需 |
| `parse_task_result` | LLM 任务解析结果 | 请求响应 |
| `generate_report_result` | LLM 巡检报告 | 请求响应 |
| `command_ack` | 命令确认 | 请求响应 |
| `subscription` | 订阅确认 | 订阅时 |
| `error` | 错误消息 | 异常时 |

---

## 测试清单

- [ ] APP 连接小车 `ws://192.168.137.117:6500/ws/control`
- [ ] 按住前进按钮，小车持续前进；松手停车
- [ ] 左移/右移/左转/右转正常
- [ ] 传感器页面显示真实温湿度/烟雾/PM2.5
- [ ] 状态页面显示导航进度和障碍物信息
- [ ] LLM 语音解析可用（发送自然语言 → 返回结构化任务）
- [ ] 视频流正常显示（MJPEG HTTP）
- [ ] 断开连接后小车自动停止
