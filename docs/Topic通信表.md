# Topic 通信表

> **icar-ros2-patrol** ROS2 Topic 通信矩阵

---

## Topic 总览

| 序号 | Topic 名称 | 消息类型 | 发布者 | 订阅者 | 优先级 | QoS | 说明 |
|------|------------|----------|--------|--------|--------|-----|------|
| 1 | `/cmd_vel` | `geometry_msgs/msg/Twist` | `app_control_node`, `obstacle_avoid_node` | 底盘驱动节点 | P0 | Reliable | 小车运动速度指令 |
| 2 | `/scan` | `sensor_msgs/msg/LaserScan` | `lidar_node` | `obstacle_avoid_node`, `slam_node`, `navigation_node` | P0 | Best Effort | 激光雷达扫描数据 |
| 3 | `/odom` | `nav_msgs/msg/Odometry` | 底盘驱动/里程计 | `slam_node`, `navigation_node` | P0 | Reliable | 里程计数据 |
| 4 | `/map` | `nav_msgs/msg/OccupancyGrid` | `slam_node` | `navigation_node`, `app_control_node` | P1 | Reliable | SLAM 构建的栅格地图 |
| 5 | `/goal_pose` | `geometry_msgs/msg/PoseStamped` | `navigation_node` | 底盘驱动节点 | P1 | Reliable | 导航目标位姿 |
| 6 | `/nav_status` | 自定义 `NavStatus` | `navigation_node` | `app_control_node`, `task_manager_node` | P1 | Reliable | 导航状态反馈 |
| 7 | `/obstacle_status` | 自定义 `ObstacleStatus` | `obstacle_avoid_node` | `task_manager_node`, `app_control_node` | P0 | Reliable | 障碍物检测状态 |
| 8 | `/vision/detections` | 自定义 `DetectionArray` | `vision_node` | `task_manager_node` | P1 | Best Effort | 视觉检测结果 |
| 9 | `/sensor/env_data` | 自定义 `EnvData` | `sensor_node` | `task_manager_node` | P1 | Reliable | 环境传感器数据 |
| 10 | `/task/status` | 自定义 `TaskStatus` | `task_manager_node` | `app_control_node` | P0 | Reliable | 任务执行状态 |
| 11 | `/task/log` | 自定义 `TaskLog` | `task_manager_node` | `app_control_node`, `llm_gateway_node` (P2) | P2 | Reliable | 任务日志记录 |

---

## Topic 详细定义

### 1. /cmd_vel

```
消息类型: geometry_msgs/msg/Twist
发布者:   app_control_node, obstacle_avoid_node
订阅者:   底盘驱动节点
QoS:      Reliable
频率:     按需 (APP操作时) / 20Hz (避障干预时)
```

| 字段 | 类型 | 说明 |
|------|------|------|
| `linear.x` | float64 | 前进速度 (m/s)，正=前进，负=后退 |
| `linear.y` | float64 | 横向速度 (保留) |
| `linear.z` | float64 | 垂直速度 (保留) |
| `angular.x` | float64 | (保留) |
| `angular.y` | float64 | (保留) |
| `angular.z` | float64 | 转向角速度 (rad/s)，正=左转，负=右转 |

### 2. /scan

```
消息类型: sensor_msgs/msg/LaserScan
发布者:   lidar_node
订阅者:   obstacle_avoid_node, slam_node, navigation_node
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

### 3. /odom

```
消息类型: nav_msgs/msg/Odometry
发布者:   底盘驱动/里程计节点
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

### 4. /map

```
消息类型: nav_msgs/msg/OccupancyGrid
发布者:   slam_node
订阅者:   navigation_node, app_control_node
QoS:      Reliable (Transient Local)
频率:     按需 (地图更新时)
```

| 字段 | 类型 | 说明 |
|------|------|------|
| `info.width` | uint32 | 地图宽度 (像素) |
| `info.height` | uint32 | 地图高度 (像素) |
| `info.resolution` | float32 | 分辨率 (m/像素) |
| `data` | int8[] | 栅格数据: -1=未知, 0=空闲, 100=障碍物 |

### 5. /goal_pose

```
消息类型: geometry_msgs/msg/PoseStamped
发布者:   navigation_node
订阅者:   底盘驱动节点
QoS:      Reliable
频率:     按需 (设置目标点时)
```

| 字段 | 类型 | 说明 |
|------|------|------|
| `header.frame_id` | string | 坐标系 (通常 "map") |
| `pose.position` | Point | 目标位置 (x, y, z) |
| `pose.orientation` | Quaternion | 目标朝向 |

### 6. /nav_status

```
消息类型: 自定义 NavStatus.msg
发布者:   navigation_node
订阅者:   app_control_node, task_manager_node
QoS:      Reliable
频率:     1-5 Hz
```

| 字段 | 类型 | 说明 |
|------|------|------|
| `status` | string | 状态: IDLE / NAVIGATING / ARRIVED / FAILED |
| `progress` | float32 | 导航进度 (0.0 ~ 1.0) |
| `distance_remain` | float32 | 剩余距离 (m) |
| `message` | string | 状态描述文本 |

### 7. /obstacle_status

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
| `direction` | string | 障碍物方位 (front/left/right/back) |

### 8. /vision/detections

```
消息类型: 自定义 DetectionArray.msg
发布者:   vision_node
订阅者:   task_manager_node
QoS:      Best Effort
频率:     10-30 Hz (取决于检测帧率)
```

| 字段 | 类型 | 说明 |
|------|------|------|
| `header` | std_msgs/Header | 时间戳 |
| `detections` | Detection[] | 检测目标数组 |
| `detections[i].class_name` | string | 目标类别 |
| `detections[i].confidence` | float32 | 置信度 |
| `detections[i].x_min/y_min/x_max/y_max` | int32 | 边界框 |

### 9. /sensor/env_data

```
消息类型: 自定义 EnvData.msg
发布者:   sensor_node
订阅者:   task_manager_node
QoS:      Reliable
频率:     1 Hz
```

| 字段 | 类型 | 说明 |
|------|------|------|
| `temperature` | float32 | 温度 (℃) |
| `humidity` | float32 | 湿度 (%) |
| `smoke` | float32 | 烟雾浓度 (ppm) |
| `pm25` | float32 | PM2.5 (μg/m³) |
| `light` | float32 | 光照强度 (lux) |
| `pressure` | float32 | 气压 (hPa) |

### 10. /task/status

```
消息类型: 自定义 TaskStatus.msg
发布者:   task_manager_node
订阅者:   app_control_node
QoS:      Reliable
频率:     按需 (任务状态变化时)
```

| 字段 | 类型 | 说明 |
|------|------|------|
| `task_id` | string | 任务 ID |
| `status` | string | 状态: PENDING / RUNNING / COMPLETED / FAILED / CANCELLED |
| `current_step` | int32 | 当前步骤编号 |
| `total_steps` | int32 | 总步骤数 |
| `message` | string | 状态描述 |

### 11. /task/log

```
消息类型: 自定义 TaskLog.msg
发布者:   task_manager_node
订阅者:   app_control_node, llm_gateway_node (P2)
QoS:      Reliable
频率:     按需 (巡检事件发生时)
```

| 字段 | 类型 | 说明 |
|------|------|------|
| `task_id` | string | 关联任务 ID |
| `timestamp` | builtin_interfaces/Time | 事件时间 |
| `event_type` | string | 事件类型: SENSOR_READING / VISION_DETECT / NAV_EVENT / ERROR |
| `data_json` | string | 事件数据 JSON |
| `severity` | string | 严重级别: INFO / WARN / ERROR |

---

## QoS 说明

| QoS 模式 | 适用场景 |
|----------|----------|
| **Reliable** | 关键状态信息，不允许丢包（控制指令、状态、日志） |
| **Best Effort** | 高频实时数据，允许丢帧（雷达扫描、视频检测结果） |
| **Transient Local** | 后订阅者也能收到最后一条消息（/map 地图数据） |

---

## 通信拓扑图

```
lidar_node ──/scan──▶ obstacle_avoid_node ──/obstacle_status──▶ task_manager_node
    │                      │                                         │
    │                      └──/cmd_vel──▶ 底盘                        │
    │                                                                 │
    ├──/scan──▶ slam_node ──/map──▶ navigation_node                   │
    │                                   │                             │
    │                                   ├──/goal_pose──▶ 底盘         │
    │                                   └──/nav_status──▶ task_manager_node
    │                                                                 │
    └──/scan──▶ navigation_node (路径规划)                             │
                                                                      │
vision_node ──/vision/detections──▶ task_manager_node                 │
sensor_node ──/sensor/env_data───▶ task_manager_node                  │
                                                                      │
task_manager_node ──/task/status──▶ app_control_node                  │
task_manager_node ──/task/log─────▶ app_control_node                  │
                                 ──▶ llm_gateway_node (P2)            │
                                                                      │
app_control_node ──/cmd_vel──▶ 底盘驱动                                │
```

---

> **注意**：以上 Topic 通信表为初版设计，开发过程中根据实际 ROS2 框架选型和模块需求调整消息定义和 QoS 配置。
