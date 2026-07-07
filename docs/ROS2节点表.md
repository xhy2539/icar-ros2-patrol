# ROS2 节点表

> **icar-ros2-patrol** ROS2 节点清单

---

## 节点总览

| 序号 | 节点名称 | 所属模块 | 负责人 | 优先级 | 功能描述 |
|------|----------|----------|--------|--------|----------|
| 1 | `app_control_node` | app | 李雨晨 | P0 | APP/网页控制台与 ROS2 通信桥梁，负责发布控制指令、订阅状态信息 |
| 2 | `lidar_node` | navigation | 曹莹 | P0 | 激光雷达驱动节点，发布 `/scan` 数据 |
| 3 | `obstacle_avoid_node` | navigation | 曹莹 | P0 | 避障节点，订阅 `/scan`，检测障碍物并发布避障指令 |
| 4 | `slam_node` | navigation | 曹莹 | P1 | SLAM 建图节点，生成并发布 `/map` 栅格地图 |
| 5 | `navigation_node` | navigation | 曹莹 | P1 | 自主导航节点，路径规划与目标点导航 |
| 6 | `vision_node` | vision | 韦雪 | P1 | 视觉检测节点，摄像头驱动 + YOLO 目标检测 |
| 7 | `sensor_node` | sensor | 王璐 | P1 | 传感器数据采集节点，汇总多传感器数据 |
| 8 | `task_manager_node` | 架构 | 熊浩宇 | P0 | 任务调度核心节点，协调各模块、记录任务日志 |
| 9 | `llm_gateway_node` | llm | 熊浩宇 | P2 | LLM 网关节点（加分项），任务解析与报告生成 |

---

## 节点详细信息

### 1. app_control_node

| 属性 | 值 |
|------|-----|
| **节点名** | `app_control_node` |
| **包名** | `app_control` |
| **语言** | Python |
| **负责人** | 李雨晨 |
| **订阅 Topic** | `/map`, `/nav_status`, `/obstacle_status`, `/task/status`, `/task/log` |
| **发布 Topic** | `/cmd_vel` |
| **服务** | 无（P2 阶段可能有设置接口） |
| **功能** | 接收 APP 端指令转为 `/cmd_vel` 消息；展示地图、导航状态、传感器数据、任务日志 |
| **启动命令** | `ros2 run app_control app_control_node` |

### 2. lidar_node

| 属性 | 值 |
|------|-----|
| **节点名** | `lidar_node` |
| **包名** | `navigation` |
| **语言** | Python |
| **负责人** | 曹莹 |
| **订阅 Topic** | 无 |
| **发布 Topic** | `/scan` |
| **服务** | 无 |
| **功能** | 驱动激光雷达硬件，发布 `sensor_msgs/LaserScan` 消息 |
| **启动命令** | `ros2 run navigation lidar_node` |

### 3. obstacle_avoid_node

| 属性 | 值 |
|------|-----|
| **节点名** | `obstacle_avoid_node` |
| **包名** | `navigation` |
| **语言** | Python |
| **负责人** | 曹莹 |
| **订阅 Topic** | `/scan` |
| **发布 Topic** | `/cmd_vel`（覆盖）, `/obstacle_status` |
| **功能** | 分析激光雷达数据，检测障碍物距离；当距离 < 阈值时发布停止/避让指令 |
| **启动命令** | `ros2 run navigation obstacle_avoid_node` |

### 4. slam_node

| 属性 | 值 |
|------|-----|
| **节点名** | `slam_node` |
| **包名** | `navigation` |
| **语言** | Python (可调用 slam_toolbox) |
| **负责人** | 曹莹 |
| **订阅 Topic** | `/scan`, `/odom` |
| **发布 Topic** | `/map` |
| **功能** | 基于激光雷达和里程计数据构建栅格地图；支持地图保存/加载 |
| **启动命令** | `ros2 run navigation slam_node` |

### 5. navigation_node

| 属性 | 值 |
|------|-----|
| **节点名** | `navigation_node` |
| **包名** | `navigation` |
| **语言** | Python (可调用 nav2) |
| **负责人** | 曹莹 |
| **订阅 Topic** | `/map`, `/odom`, `/scan` |
| **发布 Topic** | `/goal_pose`, `/nav_status` |
| **功能** | 接收目标点, 规划路径, 控制小车自主行驶；发布导航状态 |
| **启动命令** | `ros2 run navigation navigation_node` |

### 6. vision_node

| 属性 | 值 |
|------|-----|
| **节点名** | `vision_node` |
| **包名** | `vision` |
| **语言** | Python |
| **负责人** | 韦雪 |
| **订阅 Topic** | 无（直接读取摄像头） |
| **发布 Topic** | `/vision/detections` |
| **功能** | 摄像头图像采集、YOLO 模型推理、目标检测结果输出、可选目标追踪 |
| **启动命令** | `ros2 run vision vision_node` |

### 7. sensor_node

| 属性 | 值 |
|------|-----|
| **节点名** | `sensor_node` |
| **包名** | `sensor` |
| **语言** | Python |
| **负责人** | 王璐 |
| **订阅 Topic** | 无（直接读取传感器硬件） |
| **发布 Topic** | `/sensor/env_data` |
| **功能** | 定时采集温湿度/烟雾/PM2.5/光照/气压数据；异常阈值判定与告警 |
| **启动命令** | `ros2 run sensor sensor_node` |

### 8. task_manager_node

| 属性 | 值 |
|------|-----|
| **节点名** | `task_manager_node` |
| **包名** | `task_manager` |
| **语言** | Python |
| **负责人** | 熊浩宇 |
| **订阅 Topic** | `/obstacle_status`, `/vision/detections`, `/sensor/env_data`, `/nav_status` |
| **发布 Topic** | `/task/status`, `/task/log`, `/cmd_vel`（紧急停止） |
| **功能** | 核心调度节点：接收各模块状态, 决策任务流程, 记录巡检日志, 异常处理 |
| **启动命令** | `ros2 run task_manager task_manager_node` |

### 9. llm_gateway_node

| 属性 | 值 |
|------|-----|
| **节点名** | `llm_gateway_node` |
| **包名** | `llm_gateway` |
| **语言** | Python |
| **负责人** | 熊浩宇 |
| **订阅 Topic** | `/task/log` |
| **发布 Topic** | 无（通过 Service 返回） |
| **服务** | `/llm/parse_task` |
| **功能** | P2 加分项：自然语言任务解析、巡检报告生成；与外部 LLM API 通信 |
| **启动命令** | `ros2 run llm_gateway llm_gateway_node` |

---

## 节点启动顺序

```
1. lidar_node         (先启驱动)
2. sensor_node        (先启传感器)
3. obstacle_avoid_node(依赖 /scan)
4. slam_node          (依赖 /scan, /odom)
5. navigation_node    (依赖 /map, /odom)
6. vision_node        (独立启动)
7. task_manager_node  (依赖各模块 Topic)
8. app_control_node   (最后启动，连接 APP)
9. llm_gateway_node   (P2阶段启动)
```

---

> **注意**：以上节点表为初版设计，开发过程中根据实际情况调整节点划分和通信关系。
