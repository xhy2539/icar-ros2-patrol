# navigation README

## 目标

当前真实小车暂不可用，导航模块先提供一套基于 ROS2 Topic 的 mock 数据模式，保证任务调度和前端可以继续开发，不必等待真车恢复。工程目录和实现文件保持正式导航模块命名，mock 只体现在数据配置和运行模式中。

## 当前提供的 Topic

### 标准 ROS2 消息

- `/goal_pose` -> `geometry_msgs/msg/PoseStamped`
- `/map` -> `nav_msgs/msg/OccupancyGrid`
- `/pose` -> `geometry_msgs/msg/PoseStamped`
- `/scan` -> `sensor_msgs/msg/LaserScan`

### 兼容层消息

仓库当前没有 `.msg` 定义，因此 mock 阶段临时使用 `std_msgs/msg/String` 承载 JSON 字段：

- `/nav_status`
- `/obstacle_status`

JSON 字段保持和文档中的 `NavStatus` / `ObstacleStatus` 一致，后续补齐自定义消息后可平滑切回。

## 目录说明

- `navigation/lidar/lidar_node.py`：发布 `/scan`，当前可运行 mock 数据模式
- `navigation/obstacle_avoid/obstacle_avoid_node.py`：发布 `/obstacle_status`
- `navigation/slam/slam_node.py`：发布 `/map`、`/pose`
- `navigation/navigation/navigation_node.py`：消费 `/goal_pose`，输出 `/nav_status`
- `navigation/navigation/patrol_node.py`：自动下发 A/B/C 巡检点
- `navigation/navigation_utils.py`：导航公共工具
- `config/navigation/mock/`：导航 mock 配置
- `config/navigation/maps/`：静态 mock 地图

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

## 状态说明

### `/nav_status`

示例：

```json
{
  "source": "navigation_node",
  "mode": "mock",
  "status": "NAVIGATING",
  "progress": 0.375,
  "distance_remain": 0.82,
  "message": "mock navigation in progress",
  "current_goal": {
    "x": 1.25,
    "y": 0.75,
    "yaw": 1.57
  },
  "scenario": "success"
}
```

### `/obstacle_status`

示例：

```json
{
  "source": "obstacle_avoid_node",
  "mode": "mock",
  "scenario": "warning_then_clear",
  "is_obstacle": true,
  "min_distance": 0.8,
  "direction": "front",
  "risk_level": "warning",
  "action": "slow_down"
}
```

## 切回真车时怎么处理

- 保留 `/goal_pose`、`/map`、`/pose`、`/scan` Topic 名不变
- 用真实 `lidar/slam/navigation/avoidance` 节点替换 mock 节点
- 如果后续补齐 `NavStatus.msg` / `ObstacleStatus.msg`，优先保持字段名不变

## 组内同步建议

- 前端直接按现有 Topic 字段接，不要额外依赖 mock 专用字段
- 任务调度先按 `IDLE / NAVIGATING / ARRIVED / FAILED` 推进状态机
- 所有人都要明确：当前交付的是联调输入，不是最终真机验收结果
