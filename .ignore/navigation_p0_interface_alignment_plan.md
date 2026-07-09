# 导航模块 P0 接口对齐执行计划

## 目标

本计划的目标不是立即完成真机 P0 验收，而是先把 `navigation/` 模块改造成：

- 对外接口完全按 `docs/` 文档固定
- `mock` 只保留为数据源或运行模式，不再占用接口层
- 后续一旦真实 `/scan`、`/odom`、SLAM 或导航能力接入，可以最小代价切换到真数据
- 切换真数据后，不需要再修改前端、任务调度、Topic 名、消息类型和节点职责

最终希望达到的口径：

> 导航模块代码已按文档完成正式接口对齐，当前仅数据源和算法执行仍运行在 mock 模式；接入真实链路后可直接进入 P0 验收。

---

## 当前现状

结合 `docs/` 和当前代码，现状可分为三类：

### 1. 已经基本对齐的部分

- 目录结构采用正式命名：`lidar/`、`obstacle_avoid/`、`slam/`、`navigation/`
- 关键 Topic 名已基本稳定：
  - `/scan`
  - `/map`
  - `/pose`
  - `/goal_pose`
  - `/nav_status`
  - `/obstacle_status`
- `scripts/start_navigation.sh` 已提供统一启动入口
- `icar_interfaces/` 中已经存在 `NavStatus.msg`、`ObstacleStatus.msg`
- 导航主链路已切到正式消息：
  - `/nav_status` -> `icar_interfaces/NavStatus`
  - `/obstacle_status` -> `icar_interfaces/ObstacleStatus`

### 1.1 2026-07-09 状态更新

截至本轮代码改造后的实际状态：

- `/scan` 已接入真实雷达源，当前不再由项目内 mock 生成
- `navigation_node`、`obstacle_avoid_node`、`slam_node`、`patrol_node` 已完成正式消息与 Topic 骨架对齐
- `task_manager` 与导航模块之间已不再依赖 `String(JSON)` 作为主协议
- `/map`、`/pose`、`/nav_status`、`/obstacle_status` 的内部生成逻辑仍为过渡实现
- 当前最适合的推进方式是：继续结合手册 `3.7` 的真实链路调试，逐步把 `slam -> navigation -> obstacle_avoid` 的内部数据源从 mock 切到真实

### 2. 当前仍未完成真机化的关键点

- `slam_node.py` 目前仍使用静态地图和模拟位姿，不是最终真实 `SLAM(/scan + /odom -> /map + /pose)` 输出
- `navigation_node.py` 目前仍按 mock 场景推进导航状态，不是最终真实导航反馈
- `obstacle_avoid_node.py` 目前虽然已具备 `/scan -> /obstacle_status (+ /cmd_vel)` 骨架，但障碍判定仍由 mock 场景驱动
- `navigation/README.md` 和 `docs/` 已同步为“正式接口 + mock 过渡态”的口径，但还不能据此宣称通过真机 P0 验收

### 3. 当前可以保留为 mock 的部分

下列内容可以暂时保留 mock，只要它们不破坏正式接口：

- mock 地图资源
- mock 巡检点配置
- mock 导航进度推进逻辑
- mock 障碍物场景
- mock 位姿演进

保留原则：

- 可以 mock 数据
- 可以 mock 状态演进
- 不能 mock 接口定义
- 不能让 mock 逻辑决定正式消息格式

---

## 文档对齐目标

本次改造后，导航模块应满足以下“接口级目标”：

### 1. 消息类型对齐

- `/nav_status` 使用 `icar_interfaces/NavStatus`
- `/obstacle_status` 使用 `icar_interfaces/ObstacleStatus`

字段必须严格匹配文档：

#### NavStatus

```text
string status
float32 progress
float32 distance_remain
string message
```

#### ObstacleStatus

```text
bool is_obstacle
float32 min_distance
string direction
string risk_level
string action
```

### 2. 节点职责对齐

#### lidar_node

- 正式职责：接入或监测真实 `/scan`
- mock 阶段允许不自己造 `/scan`
- 但代码表述必须明确：这是雷达输入接入节点，不是“临时兼容脚本”

#### obstacle_avoid_node

- 固定订阅：`/scan`
- 固定发布：`/obstacle_status`
- 预留发布：`/cmd_vel`
- mock 阶段可以不真的控制底盘，但节点职责和接口必须就位

#### slam_node

- 固定输入：`/scan`、`/odom`
- 固定输出：`/map`、`/pose`
- mock 阶段可以从静态地图和模拟位姿源生成输出
- 但代码结构必须明确区分：
  - 正式 ROS2 接口层
  - mock 数据源层

#### navigation_node

- 固定输入：`/map`、`/pose`、`/goal_pose`、`/scan`
- 固定输出：`/nav_status`
- 预留运动指令输出能力
- mock 阶段允许用预设进度推进状态
- 但状态发布必须走正式消息，不再走 JSON 字符串

#### patrol_node

- 固定发布：`/goal_pose`
- 固定订阅：正式 `NavStatus`
- 仍作为固定路线巡检的调度辅助节点

### 3. 启动方式对齐

- `scripts/start_navigation.sh` 保留统一入口
- 通过模式参数区分：
  - `mock`
  - `mock-full`
  - `real`
- 模式只切换数据源，不改变节点名、Topic 名、消息类型和职责

---

## 设计原则

本次改造采用“接口层固定、数据源可切换”的思路。

### 原则 1：先稳定接口，再切换数据源

先把 ROS2 层全部固定下来：

- 节点名
- Topic 名
- 消息类型
- 字段定义
- 节点职责

之后再替换数据源：

- mock provider -> real provider

### 原则 2：mock 只在节点内部，不外溢到接口层

允许：

- 节点内部从 YAML 读 mock 场景
- 节点内部用定时器模拟状态变化

不允许：

- 对外发 `String(JSON)` 代替正式 msg
- 为 mock 单独发一套 Topic
- 文档与代码长期保持两套口径

### 原则 3：优先兼容 task_manager

由于 `task_manager_node.py` 已经按正式 `NavStatus` / `ObstacleStatus` 订阅，因此导航模块必须向它靠齐，不能继续要求调度模块兼容 JSON 字符串。

---

## 拟修改文件清单

### 1. `navigation/navigation/navigation_node.py`

目标：

- 改为发布 `icar_interfaces/NavStatus`
- 保留 mock 场景推进逻辑
- 固定订阅 `/goal_pose`、`/obstacle_status`
- 视需要补齐 `/map`、`/pose`、`/scan` 的订阅骨架

重点修改：

- 移除 `std_msgs/String`
- 引入 `icar_interfaces.msg.NavStatus`
- 接收正式 `ObstacleStatus`
- 用正式消息发布导航状态
- 保留现有状态机：`IDLE / NAVIGATING / ARRIVED / FAILED`

### 2. `navigation/obstacle_avoid/obstacle_avoid_node.py`

目标：

- 改为发布 `icar_interfaces/ObstacleStatus`
- 补齐对 `/scan` 的正式订阅
- 补齐 `/cmd_vel` 发布口或至少保留占位实现

重点修改：

- 移除 `std_msgs/String`
- 引入 `icar_interfaces.msg.ObstacleStatus`
- 增加 `LaserScan` 订阅
- 增加 `Twist` publisher
- mock 阶段允许仍由场景配置驱动判断结果

备注：

- 当前阶段不要求真的控制底盘运动
- 但接口必须与文档一致，后续真车时只替换判断来源和控制策略

### 3. `navigation/slam/slam_node.py`

目标：

- 固定成正式 `slam_node` 接口骨架
- 补齐 `/odom` 订阅骨架
- 输出 `/map` 和 `/pose`
- mock 阶段继续使用静态地图和模拟位姿

重点修改：

- 去掉对 `String /nav_status` 的依赖
- 改为接收正式 `NavStatus`
- 增加 `/odom` 订阅骨架，即使当前 mock 模式暂未使用
- 明确区分：
  - 地图输出接口
  - 位姿生成逻辑
  - mock provider

### 4. `navigation/navigation/patrol_node.py`

目标：

- 改为订阅正式 `NavStatus`
- 保持 `/goal_pose` 发布逻辑不变

### 5. `navigation/lidar/lidar_node.py`

目标：

- 保持当前真实 `/scan` 监测职责
- 统一文档描述，避免与“正式雷达驱动节点”表述冲突

可能改动：

- 小幅调整日志与注释
- 明确“当前阶段对接真实雷达链路，项目内不重复造轮子”

### 6. `navigation/navigation_utils.py`

目标：

- 拆出 JSON 辅助逻辑
- 新增正式消息构造辅助函数
- 让 mock 场景仍可复用，但不再影响接口层

建议方向：

- 保留配置加载函数
- 保留插值和距离计算函数
- 删除或弱化 `parse_json_message` / `dump_json_message` 在主流程中的作用

### 7. `scripts/start_navigation.sh`

目标：

- 保留统一入口
- 明确说明各模式下哪些节点是正式接口、哪些数据仍为 mock
- 不再把“mock”描述成“兼容层模式”

### 8. `navigation/README.md`

目标：

- 重写为正式口径
- 说明“当前数据源仍部分 mock，但接口已对齐文档”
- 清晰区分“已完成接口对齐”和“尚未完成真机验收”

---

## 建议执行顺序

### 阶段 A：接口和消息先对齐

目标：

- 先让导航模块能和 `task_manager` 按正式消息联调

步骤：

1. 先改 `navigation_node.py`
2. 再改 `obstacle_avoid_node.py`
3. 再改 `slam_node.py`
4. 最后改 `patrol_node.py`

完成标准：

- 导航模块内部不再依赖 `String(JSON)` 的 `/nav_status`、`/obstacle_status`
- `task_manager` 不需要做任何兼容层处理

状态：

- 本阶段已完成

### 阶段 B：节点职责骨架补齐

目标：

- 即使内部仍有 mock，也让节点的订阅发布关系和文档一致

步骤：

1. 为 `obstacle_avoid_node` 补齐 `/scan` 和 `/cmd_vel`
2. 为 `slam_node` 补齐 `/odom`
3. 为 `navigation_node` 补齐 `/map`、`/pose`、`/scan` 的正式输入骨架

完成标准：

- 用 `ros2 topic info` 看接口关系时，基本符合文档定义

状态：

- 本阶段已基本完成

### 阶段 C：启动脚本和说明文档收口

目标：

- 让仓库整体口径一致

步骤：

1. 改 `start_navigation.sh`
2. 改 `navigation/README.md`
3. 必要时补一份 `.ignore/` 内部说明

完成标准：

- 任何组员看脚本和 README，都不会误以为当前已经完成真机 P0
- 但也能清楚知道：接口层已经对齐，可直接接真数据

状态：

- 本阶段已完成首轮收口，后续只需随真实接入进度增量更新

### 阶段 D：结合 3.7 的真数据切换

目标：

- 在不改变现有正式接口的前提下，逐步把内部数据源从 mock 切到真实

建议顺序：

1. 保持 `/scan` 真实接入稳定
2. 优先推进 `slam_node` 与真实 `/scan`、`/odom` 的接入，尽快让 `/map`、`/pose` 脱离 mock
3. 再推进 `navigation_node` 使用真实 `/map`、`/pose` 和目标点反馈
4. 最后把 `obstacle_avoid_node` 的判定逻辑从场景 YAML 切到真实雷达计算

完成标准：

- `SLAM` 与 `导航` 的真实链路可以在不修改 Topic 和消息类型的情况下替换 mock 内核

---

## 每一步验收标准

### A. 接口级验收

满足以下条件即可认定“代码除了 mock 数据外都符合文档”：

- `/nav_status` 类型为 `icar_interfaces/NavStatus`
- `/obstacle_status` 类型为 `icar_interfaces/ObstacleStatus`
- `patrol_node`、`slam_node`、`navigation_node`、`task_manager_node` 之间消息可以互通
- 不再依赖 `String(JSON)` 作为正式导航状态协议

### B. 结构级验收

满足以下条件即可认定“后续真数据切换成本较低”：

- `obstacle_avoid_node` 已有 `/scan -> /obstacle_status (+ /cmd_vel)` 正式骨架
- `slam_node` 已有 `/scan + /odom -> /map + /pose` 正式骨架
- `navigation_node` 已有 `/map + /pose + /goal_pose + /scan -> /nav_status` 正式骨架

### C. 当前不能宣称通过的内容

在真数据接入前，不能宣称以下内容已经通过：

- TC-04 自动避障
- TC-05 SLAM 建图
- TC-06 自主导航

原因：

- 当前仍缺真实环境输入和真实执行链路
- 现阶段目标是“接口对齐、架构对齐、切换预备完成”，不是“真机功能验收完成”

---

## 真数据回来后的切换策略

当小车恢复可用后，建议按下面顺序切换：

### 1. 先切 `obstacle_avoid`

- 把障碍判定从场景 YAML 改为真实 `/scan` 计算
- 保持 `/obstacle_status` 消息类型不变

### 2. 再切 `slam`

- 把静态地图和模拟位姿，切换为真实建图或定位链路输出
- 保持 `/map`、`/pose` 不变

### 3. 最后切 `navigation`

- 把定时器推进的 mock 状态改为真实路径规划和导航反馈
- 保持 `/nav_status` 格式不变

好处：

- 前端不需要改
- `task_manager` 不需要改
- 文档不需要改
- Topic 表不需要改

---

## 风险与注意事项

### 风险 1：边改接口边保留旧兼容层，容易出现双协议

避免方式：

- 改造时一次性把导航模块主链路切到正式消息
- 不再在主节点中保留 `String(JSON)` 输出

### 风险 2：把“订阅骨架补齐”误当作“功能已完成”

避免方式：

- README 和计划文档里明确区分：
  - 接口已对齐
  - 功能待真机验收

### 风险 3：脚本口径与代码口径不一致

避免方式：

- 所有说明统一写“正式接口 + mock 数据源模式”
- 不再写“兼容层消息”“临时 JSON 协议”之类的过渡表述

---

## 本次计划执行边界

本计划确认后的下一轮代码修改，不包含以下内容：

- 不直接接真车硬件
- 不直接实现完整真实 SLAM 算法
- 不直接实现完整真实导航算法
- 不新增低价值测试用例

本计划确认后的下一轮代码修改，包含以下内容：

- 接口层改造
- 消息类型对齐
- 节点职责骨架补齐
- 启动脚本和 README 收口

---

## 建议的下一步

如果确认执行，建议按以下顺序开始真正改代码：

1. 先改 `navigation/navigation/navigation_node.py`
2. 再改 `navigation/obstacle_avoid/obstacle_avoid_node.py`
3. 再改 `navigation/slam/slam_node.py`
4. 再改 `navigation/navigation/patrol_node.py`
5. 最后收口 `navigation/README.md` 和 `scripts/start_navigation.sh`

执行完成后，再统一做一次：

- `git diff` 复查
- 关键文件诊断检查
- topic/消息对齐复核
