# ROS2 节点表

> **icar-ros2-patrol** ROS2 节点清单（正式节点 11 个，另含导航 mock 临时节点）

---

## 节点总览

| 序号 | 节点名称 | 所属模块 | 负责人 | 优先级 | 功能描述 |
|------|----------|----------|--------|--------|----------|
| 1 | `app_control_node` | app | 李雨晨 | P0 | APP/网页控制台与 ROS2 通信桥梁，发布控制指令、订阅状态信息 |
| 2 | `task_manager_node` | 架构 | 熊浩宇 | P0 | 任务调度核心节点，巡检状态机、任务日志、模块协调 |
| 3 | `lidar_node` | navigation | 曹莹 | P0 | 激光雷达驱动节点，发布 `/scan` 数据 |
| 4 | `obstacle_avoid_node` | navigation | 曹莹 | P0 | 避障节点，订阅 `/scan`，检测障碍物并发布避障/停止指令 |
| 5 | `slam_node` | navigation | 曹莹 | P0 | SLAM 建图节点，生成并发布 `/map` 栅格地图和 `/pose` 位姿 |
| 6 | `navigation_node` | navigation | 曹莹 | P0 | 自主导航节点，路径规划与目标点导航 |
| 7 | `camera_node` | vision | 韦雪 | P0 | 摄像头驱动节点，发布 `/image` 和 `/depth` |
| 8 | `vision_node` | vision | 韦雪 | P0 | 视觉检测节点，YOLO 目标检测、目标追踪、截图保存 |
| 9 | `sensor_node` | sensor | 王璐 | P0 | 传感器数据采集节点，汇总多传感器数据，发布异常告警 |
| 10 | `llm_gateway_node` | llm | 熊浩宇 | P2 | LLM 网关节点（加分项），任务解析与报告生成，不发布 `/cmd_vel` |
| 11 | `底盘控制模块` | 底盘 | 平台(复用) | P0 | AT32 麦轮底盘，接收 `/cmd_vel` 或 Rosmaster-Lib 串口直控，固件 v3.5，`/dev/myserial` 115200bps |

---

## 节点详细信息

### 1. app_control_node

| 属性 | 值 |
|------|-----|
| **节点名** | `app_control_node` |
| **包名** | `app_control` |
| **语言** | Python |
| **负责人** | 李雨晨 |
| **订阅 Topic** | `/map`, `/nav_status`, `/obstacle_status`, `/task/status`, `/task/log`, `/sensor/env_data`, `/vision/detections` |
| **发布 Topic** | `/cmd_vel`, `/task/request` |
| **服务** | 无 |
| **功能** | 1. 接收 APP 按钮/网页控制指令转为 `/cmd_vel` 消息（前进/后退/转向/停止）2. 展示地图、导航状态、传感器数据、视觉检测结果、任务日志 3. 向任务调度模块下发巡检任务请求 |
| **启动命令** | `ros2 run app_control app_control_node` |

### 2. task_manager_node

| 属性 | 值 |
|------|-----|
| **节点名** | `task_manager_node` |
| **包名** | `task_manager` |
| **语言** | Python |
| **负责人** | 熊浩宇 |
| **订阅 Topic** | `/task/request`, `/nav_status`, `/obstacle_status`, `/vision/detections`, `/sensor/env_data`, `/sensor/alert` |
| **发布 Topic** | `/task/status`, `/task/log`, `/cmd_vel`（紧急停止场景） |
| **功能** | 核心调度节点：1. 维护巡检状态机（PENDING→RUNNING→NAVIGATING→CHECKPOINT→DETECTING→COLLECTING→COMPLETED/FAILED）2. 接收各模块状态，决策任务流程 3. 汇总导航/视觉/传感器事件为结构化任务日志 4. 异常情况下发布紧急停止指令 |
| **启动命令** | `ros2 run task_manager task_manager_node` |

### 3. lidar_node

| 属性 | 值 |
|------|-----|
| **节点名** | `lidar_node` |
| **包名** | `navigation` |
| **语言** | Python |
| **负责人** | 曹莹 |
| **订阅 Topic** | 无（直接读取思岚A1硬件） |
| **发布 Topic** | `/scan` |
| **服务** | 无 |
| **功能** | 驱动思岚A1激光雷达硬件，发布 `sensor_msgs/LaserScan` 消息，360° 距离扫描 |
| **启动命令** | `ros2 run navigation lidar_node` |

### 4. obstacle_avoid_node

| 属性 | 值 |
|------|-----|
| **节点名** | `obstacle_avoid_node` |
| **包名** | `navigation` |
| **语言** | Python |
| **负责人** | 曹莹 |
| **订阅 Topic** | `/scan`, 运动状态 |
| **发布 Topic** | `/cmd_vel`（停止/避让指令）, `/obstacle_status` |
| **功能** | 分析激光雷达数据，检测障碍物距离和方位；当距离 < 安全阈值时发布停止或避让指令；输出风险等级和动作建议 |
| **启动命令** | `ros2 run navigation obstacle_avoid_node` |

### 5. slam_node

| 属性 | 值 |
|------|-----|
| **节点名** | `slam_node` |
| **包名** | `navigation` |
| **语言** | Python (可调用 slam_toolbox) |
| **负责人** | 曹莹 |
| **订阅 Topic** | `/scan`, `/odom` |
| **发布 Topic** | `/map`, `/pose` |
| **功能** | 基于激光雷达和里程计数据构建栅格地图；支持地图保存（.pgm + .yaml）和加载；发布实时位姿估计 |
| **启动命令** | `ros2 run navigation slam_node` |

### 6. navigation_node

| 属性 | 值 |
|------|-----|
| **节点名** | `navigation_node` |
| **包名** | `navigation` |
| **语言** | Python (可调用 nav2) |
| **负责人** | 曹莹 |
| **订阅 Topic** | `/map`, `/pose`, `/goal_pose`, `/scan` |
| **发布 Topic** | `/nav_status`, 路径/运动指令 |
| **功能** | 接收目标点，规划路径，控制小车自主行驶；支持固定路线巡检（A→B→C）；发布导航状态（IDLE/NAVIGATING/ARRIVED/FAILED）。当前无车阶段可先运行 mock 数据模式。 |
| **启动命令** | `ros2 run navigation navigation_node` |

### 7. camera_node

| 属性 | 值 |
|------|-----|
| **节点名** | `camera_node` |
| **包名** | `vision` |
| **语言** | Python |
| **负责人** | 韦雪 |
| **订阅 Topic** | 无（直接读取奥比中光 Astra Pro Plus） |
| **发布 Topic** | `/image`, `/depth` |
| **功能** | 驱动深度相机硬件，发布 RGB 图像和深度图像数据 |
| **启动命令** | `ros2 run vision camera_node` |

### 8. vision_node

| 属性 | 值 |
|------|-----|
| **节点名** | `vision_node` |
| **包名** | `vision` |
| **语言** | Python |
| **负责人** | 韦雪 |
| **订阅 Topic** | `/image`（或直接读取 camera_node 输出） |
| **发布 Topic** | `/vision/detections` |
| **功能** | 1. 接收图像数据 2. YOLO 模型推理 3. 目标检测结果输出（类别/置信度/bbox）4. 可选目标追踪 5. 截图保存到 logs/images/ |
| **启动命令** | `ros2 run vision vision_node` |

### 9. sensor_node

| 属性 | 值 |
|------|-----|
| **节点名** | `sensor_node` |
| **包名** | `sensor` |
| **语言** | Python |
| **负责人** | 王璐 |
| **订阅 Topic** | 无（直接读取传感器硬件） |
| **发布 Topic** | `/sensor/env_data`, `/sensor/alert` |
| **功能** | 1. 定时采集温湿度(DHT22)/烟雾(MQ-2)/PM2.5(PMS5003)/光照(BH1750)/气压(BMP280) 2. 异常阈值判定 3. 发布实时环境数据 4. 超标时发布 `/sensor/alert` 告警 |
| **启动命令** | `ros2 run sensor sensor_node` |

### 10. llm_gateway_node

| 属性 | 值 |
|------|-----|
| **节点名** | `llm_gateway_node` |
| **包名** | `llm_gateway` |
| **语言** | Python |
| **负责人** | 熊浩宇、王璐 |
| **订阅 Topic** | `/task/log`（巡检日志数据） |
| **发布 Topic** | 无（通过 Service 返回结果） |
| **服务** | `/llm/parse_task`（任务解析）, `/llm/generate_report`（报告生成） |
| **功能** | P2 加分项：1. 自然语言任务解析 → 结构化 JSON 2. 异常解释生成 3. 巡检报告生成 4. 网络不可用时用规则/模板模拟接口兜底 |
| **安全约束** | **LLM 不直接发布 `/cmd_vel`**，所有输出先经过 task_manager_node 校验 |
| **启动命令** | `ros2 run llm_gateway llm_gateway_node` |

---

## 节点启动顺序

```
Phase 1 (驱动层):
  1. lidar_node           - 激光雷达驱动
  2. camera_node          - 摄像头驱动
  3. sensor_node          - 传感器采集

Phase 2 (感知层):
  4. obstacle_avoid_node  - 避障（依赖 /scan）
  5. slam_node            - SLAM 建图（依赖 /scan, /odom）
  6. vision_node          - 视觉检测（依赖 /image）

Phase 3 (决策层):
  7. navigation_node      - 自主导航（依赖 /map, /pose）
  8. task_manager_node    - 任务调度（依赖各模块 Topic）

Phase 4 (应用层):
  9. app_control_node     - APP 控制台（最后启动）

Phase 5 (增强层, P2):
  10. llm_gateway_node    - LLM 网关（P0/P1 稳定后启动）
```

---

> **注意**：底盘控制模块由小车平台预置，不需要从零开发，通过 `/cmd_vel` 接口对接即可。
