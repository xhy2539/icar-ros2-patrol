# 节点与 Topic 汇总

> 11 个节点，16 个 Topic，通过 task_manager 串联成巡检闭环。

---

## 节点总览

| # | 节点名 | 包名 | 负责人 | 优先级 | 一句话 |
|---|--------|------|--------|:--:|------|
| 1 | `lidar_node` | navigation | 曹莹 | P0 | 驱动思岚A1，发布 360° 扫描数据 |
| 2 | `obstacle_avoid_node` | navigation | 曹莹 | P0 | 分析 /scan，障碍物太近时停止/避让 |
| 3 | `slam_node` | navigation | 曹莹 | P0 | 建图 + 定位 |
| 4 | `navigation_node` | navigation | 曹莹 | P0 | 接收目标点，规划路径，导航前往 |
| 5 | `camera_node` | vision | 韦雪 | P0 | 驱动深度相机，发布图像 |
| 6 | `vision_node` | vision | 韦雪 | P0 | YOLO 目标检测 + 截图保存 |
| 7 | `sensor_node` | sensor | 王璐 | P0 | 采集 5 种环境传感器 + 异常告警 |
| 8 | `app_control_node` | app_control | 李雨晨 | P0 | APP/网页 ↔ ROS2 桥梁 |
| 9 | `task_manager_node` | task_manager | 熊浩宇 | P0 | 巡检状态机、任务日志、模块协调、紧急停止 |
| 10 | 底盘控制模块 | 平台预置 | — | P0 | AT32 麦轮底盘，接收 /cmd_vel |
| 11 | `llm_gateway_node` | llm_gateway | 熊浩宇 | P2 | 自然语言→任务 JSON，巡检报告生成 |

---

## Topic 总览

| # | Topic | 消息类型 | 谁发 | 谁收 | QoS | 频率 |
|---|-------|----------|------|------|-----|------|
| 1 | `/cmd_vel` | `geometry_msgs/Twist` | app_control, obstacle_avoid, task_manager | 底盘 | Reliable | 按需/20Hz |
| 2 | `/scan` | `sensor_msgs/LaserScan` | lidar_node | obstacle_avoid, slam, navigation | Best Effort | 10-20Hz |
| 3 | `/odom` | `nav_msgs/Odometry` | 底盘 | slam, navigation | Reliable | 20-50Hz |
| 4 | `/image` | `sensor_msgs/Image` | camera_node | vision, app | Best Effort | 15-30Hz |
| 5 | `/depth` | `sensor_msgs/Image` | camera_node | vision | Best Effort | 15-30Hz |
| 6 | `/map` | `nav_msgs/OccupancyGrid` | slam_node | navigation, app | Reliable (TL) | 按需 |
| 7 | `/pose` | `geometry_msgs/PoseStamped` | slam_node | navigation, app | Reliable | 10-20Hz |
| 8 | `/goal_pose` | `geometry_msgs/PoseStamped` | app_control, task_manager | navigation | Reliable | 按需 |
| 9 | `/nav_status` | `icar_interfaces/NavStatus` | navigation | task_manager, app | Reliable | 1-5Hz |
| 10 | `/obstacle_status` | `icar_interfaces/ObstacleStatus` | obstacle_avoid | task_manager, app | Reliable | 10Hz |
| 11 | `/vision/detections` | `icar_interfaces/DetectionArray` | vision | task_manager, app | Best Effort | 10-30Hz |
| 12 | `/sensor/env_data` | `icar_interfaces/EnvData` | sensor | task_manager, app | Reliable | 1Hz |
| 13 | `/sensor/alert` | `icar_interfaces/SensorAlert` | sensor | task_manager, app | Reliable | 按需 |
| 14 | `/task/request` | `icar_interfaces/TaskRequest` | app_control | task_manager | Reliable | 按需 |
| 15 | `/task/status` | `icar_interfaces/TaskStatus` | task_manager | app_control | Reliable | 按需 |
| 16 | `/task/log` | `icar_interfaces/TaskLog` | task_manager | app_control, llm_gateway | Reliable | 按需 |

---

## 按人分配

| 组员 | 节点数 | 发布的 Topic | 订阅的 Topic |
|------|:--:|------|------|
| **曹莹** | 4 | /scan, /nav_status, /obstacle_status, /map, /pose | /odom, /goal_pose, /cmd_vel |
| **韦雪** | 2 | /image, /depth, /vision/detections | — |
| **王璐** | 1 | /sensor/env_data, /sensor/alert | — |
| **李雨晨** | 1 | /cmd_vel, /task/request, /goal_pose | /task/status, /task/log, /sensor/env_data, /vision/detections, /nav_status, /map, /pose |
| **熊浩宇** | 2 | /task/status, /task/log, /cmd_vel(紧急) | /task/request, /nav_status, /obstacle_status, /vision/detections, /sensor/env_data, /sensor/alert |

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
  app_control_node ──自然语言───▶ llm_gateway_node (/llm/parse_task)
```

---

## 节点启动顺序

```
Phase 1 (驱动层):
  1. lidar_node
  2. camera_node
  3. sensor_node

Phase 2 (感知层):
  4. obstacle_avoid_node  (依赖 /scan)
  5. slam_node            (依赖 /scan, /odom)
  6. vision_node          (依赖 /image)

Phase 3 (决策层):
  7. navigation_node      (依赖 /map, /pose)
  8. task_manager_node    (依赖各模块 Topic)

Phase 4 (应用层):
  9. app_control_node     (最后启动)

Phase 5 (增强层, P2):
  10. llm_gateway_node    (P0/P1 稳定后启动)
```

---

## 自定义消息一览

| 消息文件 | 对应 Topic | 核心字段 |
|----------|-----------|----------|
| `NavStatus.msg` | /nav_status | status, progress, distance_remain, message |
| `ObstacleStatus.msg` | /obstacle_status | is_obstacle, min_distance, direction, risk_level, action |
| `Detection.msg` | (嵌套用) | class_name, confidence, bbox, image_path |
| `DetectionArray.msg` | /vision/detections | header, Detection[] detections |
| `EnvData.msg` | /sensor/env_data | temperature, humidity, smoke, pm25, light, pressure |
| `SensorAlert.msg` | /sensor/alert | sensor_type, current_value, threshold, severity, message |
| `TaskRequest.msg` | /task/request | task_type, route[], params |
| `TaskStatus.msg` | /task/status | task_id, status, current_step, total_steps, message |
| `TaskLog.msg` | /task/log | task_id, timestamp, event_type, data_json, severity |

---

> 所有消息定义在 [../icar_interfaces/](../icar_interfaces/) 目录下，字段不可随意改动。
