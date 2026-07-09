# navigation README

## 当前目标

导航模块当前按“正式接口对齐、数据源可切换”的方式推进：

- 节点命名、目录结构、Topic 名和消息类型按 `docs/` 固定
- `mock` 只保留为当前运行模式，不再占用接口层
- 后续真实 `/scan`、`/odom`、SLAM 或导航能力接入后，尽量不再修改前端、调度和 Topic 协议

当前阶段的正确口径是：

> 导航模块已完成接口级对齐，当前数据源和部分算法执行仍运行在 mock 模式，尚未宣称通过真机 P0 验收。

## 当前对外接口

### 输入 Topic

- `/scan` -> `sensor_msgs/msg/LaserScan`
- `/odom` -> `nav_msgs/msg/Odometry`
- `/map` -> `nav_msgs/msg/OccupancyGrid`
- `/pose` -> `geometry_msgs/msg/PoseStamped`
- `/goal_pose` -> `geometry_msgs/msg/PoseStamped`

### 输出 Topic

- `/nav_status` -> `icar_interfaces/msg/NavStatus`
- `/obstacle_status` -> `icar_interfaces/msg/ObstacleStatus`
- `/cmd_vel` -> `geometry_msgs/msg/Twist`

### 正式消息字段

`NavStatus`

```text
string status
float32 progress
float32 distance_remain
string message
```

`ObstacleStatus`

```text
bool is_obstacle
float32 min_distance
string direction
string risk_level
string action
```

## 目录说明

- `navigation/lidar/lidar_node.py`：接入并监测真实 `/scan`
- `navigation/obstacle_avoid/obstacle_avoid_node.py`：订阅 `/scan`，发布 `/obstacle_status`，预留 `/cmd_vel`
- `navigation/slam/slam_node.py`：保留 `/scan + /odom -> /map + /pose` 的正式骨架，当前地图和位姿仍为 mock 驱动
- `navigation/navigation/navigation_node.py`：保留 `/map + /pose + /goal_pose + /scan -> /nav_status` 的正式骨架，当前导航状态仍按 mock 场景推进
- `navigation/navigation/patrol_node.py`：自动下发 A/B/C 巡检点
- `navigation/navigation_utils.py`：导航公共工具
- `config/navigation/mock/`：导航 mock 场景配置
- `config/navigation/maps/`：当前 mock 地图资源

## 启动方式

在 ROS2 容器或已 `source` ROS2 环境的终端中，从仓库根目录执行：

```bash
./scripts/start_navigation.sh mock
```

完整联调模式：

```bash
./scripts/start_navigation.sh mock-full
```

总演示入口：

```bash
./scripts/start_demo.sh nav-mock
```

说明：

- `/scan` 当前优先接真实雷达链路
- `mock` 模式不会改变对外 Topic 名和消息类型
- `real` 模式是后续真车恢复后的切换入口，不应再引入第二套协议

## 可选环境变量

```bash
NAV_SCENARIO=success
OBSTACLE_SCENARIO=warning_then_clear
PATROL_ROUTE=A,B,C
./scripts/start_navigation.sh mock-full
```

可用值：

- `NAV_SCENARIO`: `success` / `timeout` / `fail_fast`
- `OBSTACLE_SCENARIO`: `clear` / `warning_then_clear` / `danger_then_recover`

## 当前边界

当前阶段已经具备：

- 正式节点命名
- 正式 Topic 命名
- 正式消息类型
- 后续切换真数据的接口骨架

当前阶段仍未宣称完成：

- 真机自动避障验收
- 真机 SLAM 建图验收
- 真机自主导航验收

## 切回真车时怎么处理

- 保留 `/goal_pose`、`/map`、`/pose`、`/scan`、`/nav_status`、`/obstacle_status` 不变
- 将 `obstacle_avoid` 的障碍判定切换为真实 `/scan` 计算
- 将 `slam` 的地图和位姿输出切换为真实链路
- 将 `navigation` 的状态推进切换为真实导航反馈

## 组内同步建议

- 前端和任务调度直接按正式消息字段接入
- 不要再依赖 `String(JSON)` 作为导航主链路协议
- 当前交付的是“可切真数据的正式接口版本”，不是“真机验收完成版本”
