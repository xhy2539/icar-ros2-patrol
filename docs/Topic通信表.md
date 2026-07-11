# Topic 通信表

> **icar-ros2-patrol** ROS2 Topic 通信矩阵（当前导航模块已切到正式 Topic/消息协议，部分内部数据源仍为 mock 过渡态）

---

## Topic 总览

| 序号 | Topic 名称 | 消息类型 | 发布者 | 订阅者 | 优先级 | QoS | 频率 |
|------|------------|----------|--------|--------|--------|-----|------|
| 1 | `/cmd_vel` | `geometry_msgs/msg/Twist` | `app_control_node`, `obstacle_avoid_node`, `task_manager_node` | 底盘控制模块 | P0 | Reliable | 按需/20Hz |
| 2 | `/scan` | `sensor_msgs/msg/LaserScan` | 车端真实雷达链路 | `lidar_node`, `obstacle_avoid_node`, `slam_node`, `navigation_node` | P0 | Best Effort | 10-20Hz |
| 3 | `/odom` | `nav_msgs/msg/Odometry` | 底盘/里程计 | `slam_node`, `navigation_node` | P0 | Reliable | 20-50Hz |
| 4 | `/image` | `sensor_msgs/msg/Image` | `camera_node` | `vision_node`, `app_control_node`（展示） | P0 | Best Effort | 15-30Hz |
| 5 | `/depth` | `sensor_msgs/msg/Image` | `camera_node` | `vision_node` | P0 | Best Effort | 15-30Hz |
| 6 | `/map` | `nav_msgs/msg/OccupancyGrid` | `slam_node` | `navigation_node`, `app_control_node`（展示） | P0 | Reliable (Transient Local) | 按需 |
| 7 | `/pose` | `geometry_msgs/msg/PoseStamped` | `slam_node` | `navigation_node`, `app_control_node` | P0 | Reliable | 10-20Hz |
| 8 | `/goal_pose` | `geometry_msgs/msg/PoseStamped` | `app_control_node` / `task_manager_node` | `navigation_node` | P0 | Reliable | 按需 |
| 9 | `/nav_status` | 自定义 `NavStatus` | `navigation_node` | `task_manager_node`, `app_control_node` | P0 | Reliable | 1-5Hz |
| 10 | `/obstacle_status` | 自定义 `ObstacleStatus` | `obstacle_avoid_node` | `task_manager_node`, `app_control_node` | P0 | Reliable | 10Hz |
| 11 | `/vision/detections` | 自定义 `DetectionArray` | `vision_node` | `task_manager_node`, `app_control_node`, `llm_gateway_node`(P2) | P0 | Best Effort | 10-30Hz |
| 12 | `/sensor/env_data` | 自定义 `EnvData` | `sensor_node` | `task_manager_node`, `app_control_node`, `llm_gateway_node`(P2) | P0 | Reliable | 1Hz |
| 13 | `/sensor/alert` | 自定义 `SensorAlert` | `sensor_node` | `task_manager_node`, `app_control_node` | P1 | Reliable | 按需（异常触发） |
| 14 | `/task/request` | 自定义 `TaskRequest` | `app_control_node` | `task_manager_node` | P0 | Reliable | 按需 |
| 15 | `/task/status` | 自定义 `TaskStatus` | `task_manager_node` | `app_control_node` | P0 | Reliable | 按需（状态变化） |
| 16 | `/task/log` | 自定义 `TaskLog` | `task_manager_node` | `app_control_node`, `llm_gateway_node`(P2) | P1 | Reliable | 按需（事件触发） |
| 17 | `/vision/capture_command` | `std_msgs/msg/String` (JSON) | `app_control_node`, `task_manager_node` | `dataset_recorder_node` | P1 | Reliable | 按需 |
| 18 | `/vision/capture_status` | `std_msgs/msg/String` (JSON) | `dataset_recorder_node` | `app_control_node`, `task_manager_node` | P1 | Reliable | 按需 |
| 19 | `/vision/target_tracking/command` | `std_msgs/msg/String` (JSON) | `app_control_node`, `task_manager_node` | `target_tracker_node` | P1 | Reliable | 按需 |
| 20 | `/vision/target_cmd_vel` | `geometry_msgs/msg/Twist` | `target_tracker_node` | `task_manager_node`, `app_control_node` | P1 | Reliable | 按需/10Hz |
| 21 | `/vision/target_tracking/status` | `std_msgs/msg/String` (JSON) | `target_tracker_node` | `task_manager_node`, `app_control_node` | P1 | Reliable | 按需 |

---

## Topic 详细定义

### 1. /cmd_vel — 小车运动控制

```
消息类型: geometry_msgs/msg/Twist
发布者:   app_control_node, obstacle_avoid_node, task_manager_node
订阅者:   底盘控制模块
QoS:      Reliable
```

| 字段 | 类型 | 说明 |
|------|------|------|
| `linear.x` | float64 | 前进速度 (m/s)，正=前进，负=后退 |
| `angular.z` | float64 | 转向角速度 (rad/s)，正=左转，负=右转 |

> **注意**：obstacle_avoid_node 和 task_manager_node 可在紧急情况下 override 此 Topic 发布停止指令。

### 2. /scan — 激光雷达扫描数据

```
消息类型: sensor_msgs/msg/LaserScan
发布者:   车端真实雷达链路
订阅者:   lidar_node, obstacle_avoid_node, slam_node, navigation_node
QoS:      Best Effort
频率:     10-20 Hz
```

| 字段 | 类型 | 说明 |
|------|------|------|
| `ranges` | float32[] | 各角度距离值数组 |
| `angle_min` | float32 | 起始角度 |
| `angle_max` | float32 | 终止角度 |
| `angle_increment` | float32 | 角度增量 |
| `range_min` | float32 | 最小有效距离 |
| `range_max` | float32 | 最大有效距离 |

### 3. /odom — 里程计数据

```
消息类型: nav_msgs/msg/Odometry
发布者:   底盘/里程计模块
订阅者:   slam_node, navigation_node
QoS:      Reliable
频率:     20-50 Hz
```

| 字段 | 类型 | 说明 |
|------|------|------|
| `pose.pose.position` | Point | 机器人位置 (x, y, z) |
| `pose.pose.orientation` | Quaternion | 机器人姿态四元数 |
| `twist.twist.linear` | Vector3 | 当前线速度 |
| `twist.twist.angular` | Vector3 | 当前角速度 |

### 4. /image — RGB 图像

```
消息类型: sensor_msgs/msg/Image
发布者:   camera_node
订阅者:   vision_node, app_control_node
QoS:      Best Effort
频率:     15-30 Hz
```

| 字段 | 类型 | 说明 |
|------|------|------|
| `data` | uint8[] | 图像字节数据 |
| `width` | uint32 | 图像宽度 |
| `height` | uint32 | 图像高度 |
| `encoding` | string | 编码格式（通常 "rgb8"） |

### 5. /depth — 深度图像

```
消息类型: sensor_msgs/msg/Image
发布者:   camera_node
订阅者:   vision_node
QoS:      Best Effort
频率:     15-30 Hz
```

| 字段 | 类型 | 说明 |
|------|------|------|
| `data` | uint8[] | 深度数据（16UC1 编码） |
| `width` | uint32 | 图像宽度 |
| `height` | uint32 | 图像高度 |

### 6. /map — 栅格地图

```
消息类型: nav_msgs/msg/OccupancyGrid
发布者:   slam_node
订阅者:   navigation_node, app_control_node
QoS:      Reliable (Transient Local)
频率:     按需（地图更新时）
```

| 字段 | 类型 | 说明 |
|------|------|------|
| `info.width` | uint32 | 地图宽度 (像素) |
| `info.height` | uint32 | 地图高度 (像素) |
| `info.resolution` | float32 | 分辨率 (m/像素) |
| `info.origin` | Pose | 地图原点 |
| `data` | int8[] | 栅格: -1=未知, 0=空闲, 100=障碍物 |

### 7. /pose — 机器人位姿

```
消息类型: geometry_msgs/msg/PoseStamped
发布者:   slam_node
订阅者:   navigation_node, app_control_node
QoS:      Reliable
频率:     10-20 Hz
```

| 字段 | 类型 | 说明 |
|------|------|------|
| `header.frame_id` | string | 坐标系（通常 "map"） |
| `pose.position` | Point | 机器人位置 (x, y, z) |
| `pose.orientation` | Quaternion | 机器人姿态 |

### 8. /goal_pose — 导航目标点

```
消息类型: geometry_msgs/msg/PoseStamped
发布者:   app_control_node, task_manager_node
订阅者:   navigation_node
QoS:      Reliable
频率:     按需（设置目标点时）
```

| 字段 | 类型 | 说明 |
|------|------|------|
| `header.frame_id` | string | 坐标系（通常 "map"） |
| `pose.position` | Point | 目标位置 (x, y, z) |
| `pose.orientation` | Quaternion | 目标朝向 |

### 9. /nav_status — 导航状态反馈

```
消息类型: 自定义 NavStatus.msg
发布者:   navigation_node
订阅者:   task_manager_node, app_control_node
QoS:      Reliable
频率:     1-5 Hz
```

| 字段 | 类型 | 说明 |
|------|------|------|
| `status` | string | IDLE / NAVIGATING / ARRIVED / FAILED |
| `progress` | float32 | 导航进度 (0.0 ~ 1.0) |
| `distance_remain` | float32 | 剩余距离 (m) |
| `message` | string | 状态描述文本 |

> 当前状态：消息类型与字段已按正式接口对齐；导航结果仍可能来自 mock 过渡逻辑，待真实 `/map`、`/pose` 稳定后切换为真导航反馈。

### 10. /obstacle_status — 障碍物检测状态

```
消息类型: 自定义 ObstacleStatus.msg
发布者:   obstacle_avoid_node
订阅者:   task_manager_node, app_control_node
QoS:      Reliable
频率:     10 Hz
```

| 字段 | 类型 | 说明 |
|------|------|------|
| `is_obstacle` | bool | 是否存在障碍物 |
| `min_distance` | float32 | 最近障碍物距离 (m) |
| `direction` | string | 方位 (front/left/right/back) |
| `risk_level` | string | 风险等级 (safe/warning/danger) |
| `action` | string | 建议动作 (none/slow_down/stop/turn) |

> 当前状态：消息类型与字段已按正式接口对齐；`obstacle_avoid_node` 默认根据真实 `/scan` 前方扇区计算障碍状态，mock 场景仅保留为无雷达演示模式。

### 11. /vision/detections — 视觉检测结果

```
消息类型: 自定义 DetectionArray.msg
发布者:   vision_node
订阅者:   task_manager_node, app_control_node, llm_gateway_node (P2)
QoS:      Best Effort
频率:     10-30 Hz
```

| 字段 | 类型 | 说明 |
|------|------|------|
| `header` | std_msgs/Header | 时间戳 |
| `detections[i].class_name` | string | 目标类别 (person/obstacle/water/sign) |
| `detections[i].confidence` | float32 | 置信度 0.0-1.0 |
| `detections[i].bbox.x_min` | int32 | 边界框左上 x |
| `detections[i].bbox.y_min` | int32 | 边界框左上 y |
| `detections[i].bbox.x_max` | int32 | 边界框右下 x |
| `detections[i].bbox.y_max` | int32 | 边界框右下 y |
| `detections[i].image_path` | string | 截图保存路径 |

### 12. /sensor/env_data — 环境传感器数据

```
消息类型: 自定义 EnvData.msg
发布者:   sensor_node
订阅者:   task_manager_node, app_control_node, llm_gateway_node (P2)
QoS:      Reliable
频率:     1 Hz
```

| 字段 | 类型 | 说明 |
|------|------|------|
| `header` | std_msgs/Header | 时间戳 |
| `temperature` | float32 | 温度 (℃) |
| `humidity` | float32 | 湿度 (%) |
| `smoke` | float32 | 烟雾浓度 (ppm) |
| `pm25` | float32 | PM2.5 (μg/m³) |
| `light` | float32 | 光照强度 (lux) |
| `pressure` | float32 | 气压 (hPa) |

### 13. /sensor/alert — 传感器异常告警

```
消息类型: 自定义 SensorAlert.msg
发布者:   sensor_node
订阅者:   task_manager_node, app_control_node
QoS:      Reliable
频率:     按需（异常触发时）
```

| 字段 | 类型 | 说明 |
|------|------|------|
| `sensor_type` | string | 传感器类型 (smoke/temperature/pm25/humidity) |
| `current_value` | float32 | 当前值 |
| `threshold` | float32 | 阈值 |
| `severity` | string | 严重级别 (WARN/ERROR) |
| `message` | string | 告警描述 |

### 14. /task/request — 任务请求

```
消息类型: 自定义 TaskRequest.msg
发布者:   app_control_node
订阅者:   task_manager_node
QoS:      Reliable
频率:     按需
```

| 字段 | 类型 | 说明 |
|------|------|------|
| `task_type` | string | 任务类型 (manual_control/patrol/inspect) |
| `route` | string[] | 巡检路线点 (如 ["A","B","C"]) |
| `params` | string | 任务参数 JSON |

### 15. /task/status — 任务执行状态

```
消息类型: 自定义 TaskStatus.msg
发布者:   task_manager_node
订阅者:   app_control_node
QoS:      Reliable
频率:     按需（状态变化时）
```

| 字段 | 类型 | 说明 |
|------|------|------|
| `task_id` | string | 任务 ID |
| `status` | string | PENDING / RUNNING / NAVIGATING / CHECKPOINT / DETECTING / COLLECTING / COMPLETED / FAILED / CANCELLED |
| `current_step` | int32 | 当前步骤编号 |
| `total_steps` | int32 | 总步骤数 |
| `message` | string | 状态描述 |

### 16. /task/log — 任务日志记录

```
消息类型: 自定义 TaskLog.msg
发布者:   task_manager_node
订阅者:   app_control_node, llm_gateway_node (P2)
QoS:      Reliable
频率:     按需（巡检事件发生时）
```

| 字段 | 类型 | 说明 |
|------|------|------|
| `task_id` | string | 关联任务 ID |
| `timestamp` | builtin_interfaces/Time | 事件时间 |
| `event_type` | string | 事件类型: NAV_START / CHECKPOINT_REACHED / SENSOR_READING / VISION_DETECT / ANOMALY / NAV_END / TASK_END |
| `data_json` | string | 事件数据 JSON |
| `severity` | string | INFO / WARN / ERROR |

---

### 17. /vision/capture_command — 视觉截图/数据采集命令

```
消息类型: std_msgs/msg/String (JSON)
发布者:   app_control_node, task_manager_node
订阅者:   dataset_recorder_node
QoS:      Reliable
频率:     按需
```

示例：

```json
{"action": "capture_once", "tag": "checkpoint_A"}
{"action": "set_interval", "interval_sec": 3.0}
{"action": "stop"}
```

### 18. /vision/capture_status — 视觉截图/数据采集状态

```
消息类型: std_msgs/msg/String (JSON)
发布者:   dataset_recorder_node
订阅者:   app_control_node, task_manager_node
QoS:      Reliable
频率:     按需
```

示例：

```json
{
  "module": "vision",
  "event": "image_saved",
  "save_dir": "/tmp/icar_vision_dataset",
  "saved_count": 12,
  "data": {
    "path": "/tmp/icar_vision_dataset/vision_123_000000000_0011_checkpoint_A.jpg"
  }
}
```

---

### 19. /vision/target_tracking/command — 目标跟踪命令

```
消息类型: std_msgs/msg/String (JSON)
发布者:   app_control_node, task_manager_node
订阅者:   target_tracker_node
QoS:      Reliable
频率:     按需
```

示例：

```json
{"action": "start", "class_name": "person"}
{"action": "select_target", "class_name": "bottle"}
{"action": "stop"}
{"action": "set_params", "max_linear_speed": 0.12}
```

### 20. /vision/target_cmd_vel — 目标跟随速度建议

```
消息类型: geometry_msgs/msg/Twist
发布者:   target_tracker_node
订阅者:   task_manager_node, app_control_node
QoS:      Reliable
频率:     按需/10Hz
```

> 安全约束：该 Topic 是视觉模块输出的速度建议，默认不直接等同 `/cmd_vel`。是否转发到底盘由任务调度/安全模块统一决定。

### 21. /vision/target_tracking/status — 目标跟踪状态

```
消息类型: std_msgs/msg/String (JSON)
发布者:   target_tracker_node
订阅者:   task_manager_node, app_control_node
QoS:      Reliable
频率:     按需
```

示例：

```json
{
  "module": "vision",
  "event": "tracking",
  "data": {
    "target": {"class_name": "person", "bbox": [120, 80, 300, 420]},
    "control": {"linear_x": 0.08, "angular_z": -0.2}
  }
}
```

---

## QoS 说明

| QoS 模式 | 适用场景 |
|----------|----------|
| **Reliable** | 关键状态信息，不允许丢包（控制指令、状态、日志、告警） |
| **Best Effort** | 高频实时数据，允许丢帧（雷达扫描、图像、检测结果） |
| **Transient Local** | 后订阅者也能收到最后一条消息（/map 地图数据） |

---

## 通信拓扑图

```
                           ┌────────────────────┐
                           │   APP 控制台        │
                           │ (app_control_node)  │
                           └──┬───┬───┬───┬─────┘
                              │   │   │   │
                 /task/request│   │   │   │/cmd_vel
                              │   │   │   │
                              ▼   │   │   ▼
┌─────────┐  /scan   ┌──────────────┐   ┌──────────┐
│ lidar   │ ────────▶│ obstacle_    │   │  底盘    │
│ _node   │          │ avoid_node   │──▶│  控制    │
└────┬────┘          └──────┬───────┘   └──────────┘
     │                      │/obstacle_status
     │/scan                 ▼
     │              ┌───────────────────┐
     └─────────────▶│  task_manager     │◀──── /nav_status
                    │  _node            │
┌──────────┐       │                   │       ┌──────────┐
│ camera   │/image │                   │       │ navigat- │
│ _node    │──┐    └──▲───▲───▲───▲───▲┘       │ ion_node │
└──────────┘  │       │   │   │   │             └──────────┘
              │/depth │   │   │   │                   ▲
              ▼       │   │   │   │                   │
┌──────────┐         │   │   │   │             ┌──────────┐
│ vision   │─────────┘   │   │   │             │  slam    │
│ _node    │/vision      │   │   │             │ _node    │
└──────────┘/detections  │   │   │             └──────────┘
                         │   │   │                   ▲
┌──────────┐             │   │   │/task/status       │/scan,/odom
│ sensor   │─────────────┘   │   └──────────────────┘
│ _node    │/sensor/env_data │
│          │─────────────────┘
│          │/sensor/alert
└──────────┘

P2 (虚线):
  task_manager_node ──/task/log──▶ llm_gateway_node
  app_control_node ──自然语言────▶ llm_gateway_node (/llm/parse_task Service)
```

---

> **注意**：以上 Topic 通信表已与概要设计文档 V1.1 对齐。开发过程中根据实际需求调整消息字段。
