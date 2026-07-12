# 基于ROS2的智能巡检小车系统

> **icar-ros2-patrol** — 实验室/校园场景下的智能巡检小车实训项目

**仓库地址**：https://github.com/xhy2539/icar-ros2-patrol

---

## 项目简介

本项目基于 ROS2 (Robot Operating System 2) 构建一套智能巡检小车系统，以 Jetson Orin Nano 为主控，搭载思岚A1激光雷达、奥比中光 Astra Pro Plus 深度相机、AT32底盘控制板及环境感知模块（温湿度/烟雾/PM2.5/光照/气压），实现 APP/网页控制小车运动、ROS2 通信、雷达避障、SLAM 建图、自主导航、视觉检测、传感器采集、任务日志展示等功能。LLM（大语言模型）作为最后加分项，不影响 P0/P1 基础演示。

**设计原则**：先保证 P0 核心链路可演示；P1 形成巡检闭环；LLM 作为增强层，不直接控制底盘。

### 硬件平台

| 硬件 | 型号 | 设备路径 | 用途 |
|------|------|----------|------|
| 主控 | Jetson Orin Nano (JetPack R35.3.1) | - | 运行 ROS2 和 AI 推理 |
| 激光雷达 | 思岚 A1 (RPLIDAR) | `/dev/rplidar` → `ttyUSB0` | 360° 扫描测距 |
| 深度相机 | 奥比中光 Astra Pro Plus | `/dev/astradepth`, `/dev/astrauvc`, `/dev/video0-1` | RGB + 深度图像 |
| 底盘控制 | AT32 (Mecanum麦轮) | `/dev/myserial` → `ttyUSB1`, 115200bps | 运动控制（固件 v3.5） |
| 传感器 | 温湿度/烟雾/PM2.5/光照/气压 | `/dev/sensors` → `ttyUSB2` | 环境数据采集 |

### 系统架构

```
┌──────────────────────────────────────────┐
│         宿主机 (Jetson Ubuntu 20.04)       │
│                                          │
│  Rosmaster-App (Flask :6500)             │
│  └─ Rosmaster-Lib (Python) ──串口──▶ AT32底盘 │
│                                          │
│  Docker: yahboomtechnology/ros-foxy:5.0.1│
│  ├─ astra_camera (相机驱动)               │
│  ├─ sllidar_ros2 (激光雷达)               │
│  ├─ slam_gmapping (SLAM建图)             │
│  ├─ teb_local_planner (路径规划)          │
│  └─ icar_* (ICAR项目包)                  │
└──────────────────────────────────────────┘
```

> **关键**：ROS2 Foxy 运行在 Docker 容器内，不是原生安装。底盘控制可通过 Rosmaster-Lib 串口直接通信，也可通过 ROS2 `/cmd_vel` 间接控制。仓库中的 `app_control_node`、`lidar_node` 等名称是项目规划层节点名；实车预置包主要使用 `yahboomcar_*`、`sllidar_ros2`、`astra_camera`、`slam_gmapping`、`teb_local_planner` 等包。

---

## 功能优先级

| 优先级 | 编号 | 功能模块 | 说明 |
|--------|------|----------|------|
| **P0** | FR-P0-01 | 基础环境与连接 | 小车上电、联网、远程连接、ROS2 环境确认 |
| **P0** | FR-P0-02 | APP/上位机控制 | 前进/后退/左转/右转/停止，手动控制小车运动 |
| **P0** | FR-P0-03 | ROS2 核心通信 | Topic/Service/Action 串联底盘、雷达、相机、传感器和任务模块 |
| **P0** | FR-P0-04 | 激光雷达数据读取 | 启动激光雷达，读取扫描数据并展示 |
| **P0** | FR-P0-05 | 雷达避障 | 根据雷达距离判断前方障碍物，触发减速/停止或避让 |
| **P0** | FR-P0-06 | SLAM 建图 | 使用激光雷达扫描环境生成地图并保存 |
| **P0** | FR-P0-07 | 自主导航 | 在已建地图上设置目标点，小车自动规划路径并移动 |
| **P0** | FR-P0-08 | 摄像头接入 | 接入深度相机/摄像头并读取画面 |
| **P0** | FR-P0-09 | 视觉检测 | 识别人/障碍物/标志物，输出类别、位置、置信度 |
| **P0** | FR-P0-10 | 传感器采集 | 读取温湿度/烟雾/PM2.5/光照/气压等环境数据 |
| **P0** | FR-P0-11 | 数据展示 | APP/网页展示小车状态、传感器数据、视觉结果和任务日志 |
| **P0** | FR-P0-12 | 工程提交 | 代码仓库、README、启动脚本、测试记录、视频和文档 |
| **P1** | FR-P1-01 | 固定路线巡检 | 预设 A/B/C 巡检点，小车依次前往 |
| **P1** | FR-P1-02 | 巡检点打卡 | 到达后记录时间、坐标、传感器值和视觉检测结果 |
| **P1** | FR-P1-03 | 异常检测 | 根据烟雾/PM2.5/温湿度/障碍物/人员等规则生成异常事件 |
| **P1** | FR-P1-04 | 任务日志 | 记录任务开始/导航/到点/检测/采集/异常/结束等事件 |
| **P1** | FR-P1-05 | 前端可视化 | 统一展示地图/状态/视频截图/传感器/日志 |
| **P2** | FR-P2-01 | LLM 任务解析 | 自然语言 → 结构化 JSON 任务（加分项） |
| **P2** | FR-P2-02 | LLM 异常解释 | 根据传感器/视觉/避障异常生成解释和建议 |
| **P2** | FR-P2-03 | LLM 报告生成 | 根据任务日志生成结构化巡检报告 |
| **P2** | FR-P2-04 | LLM 模拟兜底 | 网络不可用时用规则/模板返回固定结果 |

---

## 成员分工

| 姓名 | 角色 | 负责模块 | 主要产出 |
|------|------|----------|----------|
| **熊浩宇** | 组长/系统集成 | 项目管理、ROS2 架构、任务调度、Git/CI/CD、LLM 后期接入 | 架构图、接口表、仓库、README、启动脚本、CI说明、任务日志、PPT统稿、演示流程 |
| **韦雪** | 视觉模块 | vision/：深度相机接入、OpenCV/YOLO 目标检测、目标追踪、截图保存 | 摄像头画面、检测视频、检测结果JSON、视觉模块说明 |
| **曹莹** | 雷达导航 | navigation/：激光雷达、避障、SLAM建图、自主导航、固定路线巡检 | 雷达截图、避障视频、地图文件、导航视频、导航测试表 |
| **李雨晨** | APP 开发 | app/：APP/网页控制台、手动控制、状态展示、传感器/视觉/日志展示 | 控制界面、控制视频、状态面板、日志展示页面 |
| **王璐** | 传感器 | sensor/：温湿度/烟雾/PM2.5/光照/气压采集、异常规则、巡检点记录 | 传感器数据截图、异常规则表、巡检点记录、报告数据 |

---

## RACI 责任矩阵

> R=负责执行, A=最终负责, C=协商参与, I=知会

| 工作项 | 熊浩宇 | 韦雪 | 曹莹 | 李雨晨 | 王璐 |
|--------|--------|------|------|--------|------|
| 需求分析与立项 | A/R | C | C | C | C |
| 总体架构与接口 | A/R | C | C | C | C |
| Git仓库/目录/分支 | A/R | I | I | I | I |
| CI/CD基础检查/README/启动脚本 | A/R | C | C | C | C |
| 小车连接与控制链路 | C | I | C | A/R | I |
| APP/网页控制与展示 | C | C | C | A/R | C |
| 雷达数据读取与避障 | C | I | A/R | C | I |
| SLAM建图与自主导航 | C | I | A/R | C | I |
| 视觉检测/目标追踪 | I | A/R | C | C | I |
| 传感器数据采集 | C | I | I | C | A/R |
| 巡检点打卡与任务日志 | A/R | C | C | C | C |
| 异常检测规则 | C | C | C | I | A/R |
| LLM任务解析 | A/R | I | I | C | C |
| 巡检报告生成 | A | C | C | C | R |
| 测试报告 | A | R | R | R | R |
| 中期/最终PPT | A/R | C | C | C | C |
| 演示视频 | A | R | R | R | R |

---

## 课程基本需求覆盖矩阵

| 课程要求 | 项目对应功能 | 主负责人 | 验证方式 |
|----------|-------------|----------|----------|
| ROS2核心开发与分布式通信 | ROS2节点/Topic/Launch、任务调度、模块联调 | 熊浩宇 | 节点表、Topic列表、日志和启动脚本 |
| SLAM建图与自主导航 | 雷达扫描建图、地图保存、RViz展示、目标点导航、固定路线巡检 | 曹莹 | 地图、导航视频、导航测试记录 |
| AI边缘推理与多传感器融合 | 视觉检测、传感器采集、雷达避障、异常规则与任务日志融合 | 韦雪、王璐、曹莹 | 检测框、传感器数据、异常日志 |
| 云平台集成与CI/CD流水线 | Git仓库、分支管理、README、启动脚本、CI基础检查、版本交付 | 熊浩宇 | 仓库地址、提交记录、CI说明和Release/提交包 |
| 开发APP控制小车运动 | APP/网页控制台，支持前进/后退/转向/停止和状态展示 | 李雨晨 | 现场或视频展示APP控制小车运动 |

---
# iCar 智能巡检小车控制端

Flutter 开发的 iCar 巡检小车 Android/Web 控制 APP，2026 年北京交通大学软件学院小学期实训项目。

## 项目概述

本 APP 用于通过手机/平板远程控制 iCar 巡检小车，功能包括：运动控制、状态监控、传感器数据实时展示、任务日志记录和系统设置。

**目标小车环境：** Jetson Orin Nano + Ubuntu 20.04 + ROS2 Foxy + Docker 容器化部署

## 技术栈

- **Flutter 3.x** + Material 3 设计语言
- **通信方式：** WebSocket（`ws://<IP>:6500/ws/control`），纯文本指令
- **视频流：** MJPEG HTTP 流（`http://<IP>:6500/video_feed`）
- **状态管理：** 内置 ChangeNotifier 单例，无第三方依赖
- **支持平台：** Android APK / Web / Chrome
## 目录结构

```
icar-ros2-patrol/
├── app/                    # APP/网页控制台（李雨晨）
│   ├── backend/            #   后端服务
│   └── frontend/           #   前端页面
├── navigation/             # 雷达/导航模块（曹莹）
│   ├── lidar/              #   激光雷达驱动（当前可运行 mock 数据模式）
│   ├── obstacle_avoid/     #   避障算法（默认真实 /scan，保留 mock 演示模式）
│   ├── slam/               #   SLAM 建图（当前可运行 mock 数据模式）
│   ├── navigation/         #   自主导航 / 巡检（当前可运行 mock 数据模式）
│   ├── navigation_utils.py #   导航公共工具
│   └── README.md           #   导航模块说明
├── vision/                 # 视觉检测模块（韦雪）
│   ├── camera/             #   摄像头驱动
│   ├── detection/          #   YOLO 目标检测
│   └── tracking/           #   目标追踪
├── sensor/                 # 传感器模块（王璐）
│   ├── temp_humidity/      #   温湿度传感器
│   ├── smoke/              #   烟雾传感器
│   ├── pm25/               #   PM2.5 传感器
│   ├── light/              #   光照传感器
│   └── pressure/           #   气压传感器
├── icar_interfaces/        # 自定义 ROS2 消息/服务（熊浩宇）✅
│   ├── msg/                #   9 个自定义消息
│   ├── srv/                #   1 个自定义服务 (ParseTask)
│   ├── CMakeLists.txt
│   └── package.xml
├── task_manager/           # 任务调度模块（熊浩宇）✅
│   ├── task_manager/       #   task_manager_node（状态机）
│   ├── setup.py
│   └── package.xml
├── llm/                    # LLM 模块（熊浩宇，P2加分项）
│   ├── task_parser/        #   任务解析
│   └── report_gen/         #   报告生成
├── docs/                   # 项目文档
│   ├── 接口设计.md          #   模块间接口说明 (IF-01~IF-10)
│   ├── ROS2节点表.md        #   ROS2 节点清单 (11个节点)
│   ├── Topic通信表.md       #   Topic 通信矩阵 (16 Topic)
│   ├── 模块集成产出清单.md   #   各模块接入前必须产出的 Topic/数据
│   ├── 项目进度记录.md       #   开发进度跟踪 (7.7-7.15)
│   └── 测试用例.md          #   测试用例 (TC-01~TC-12)
├── scripts/                # 启动脚本
│   ├── start_app.sh
│   ├── start_navigation.sh
│   ├── start_vision.sh
│   ├── start_sensor.sh
│   └── start_demo.sh
├── test/                   # 测试用例和测试记录
├── videos/                 # 演示视频（含兜底视频）
├── config/                 # 系统配置文件
│   └── navigation/
│       ├── maps/           #   地图资源（含 mock_lab.pgm/.yaml）
│       └── mock/           #   mock 场景、点位、地图元信息
├── logs/                   # 运行日志（不提交到仓库）
├── .github/workflows/      # CI/CD 流水线 ✅
│   └── ci.yml
├── .gitignore
└── README.md
```

## 非功能需求

| 编号 | 类别 | 需求描述 |
|------|------|----------|
| NFR-01 | 安全性 | 遇到障碍物/烟雾异常/通信异常/人工停止指令时，小车进入停止或安全状态；LLM不直接控制底盘 |
| NFR-02 | 稳定性 | 关键演示须有现场版和录屏兜底；P0功能优先稳定，不因LLM影响演示 |
| NFR-03 | 可维护性 | 代码按模块划分，仓库目录结构清晰 |
| NFR-04 | 可复现性 | 每个模块提供启动命令、配置说明和测试步骤 |
| NFR-05 | 可演示性 | 所有功能有可见结果：地图、检测框、传感器值、任务日志、报告 |
| NFR-06 | 可测试性 | 核心模块至少2个测试用例，最终有完整巡检流程测试 |
| NFR-07 | 工程规范 | Git管理代码，保留分支、提交记录、README、运行说明 |

## 快速启动

> ROS2 Foxy 运行在 Docker 容器内，通过宿主机脚本管理。
> 2026-07-07 实测：小车 IP 为 `10.90.164.78`；当前运行容器可能不是文档旧编号 `5b1c`，启动前先用 `docker ps -a` 确认。

```bash
# 1. SSH 连接小车
ssh jetson@10.90.164.78   # 密码: yahboom

# 2. 确认并进入 ROS2 Docker 容器
docker ps -a
docker start <容器ID或容器名>
docker exec -it <容器ID或容器名> /bin/bash

# 3. 容器内启动预置 Yahboom ROS2 模块（以容器内 ~/.bashrc 为准）
r     # 底盘 bringup: yahboomcar_bringup_X3_launch.py
n1    # 雷达 bringup: yahboomcar_nav laser_bringup_launch.py
m1    # SLAM 建图: yahboomcar_nav map_gmapping_launch.py
n3    # DWA 导航: yahboomcar_nav navigation_dwa_launch.py
n4    # TEB 导航: yahboomcar_nav navigation_teb_launch.py

# 4. 宿主机启动 APP（底盘直接串口控制，默认使用 /dev/myserial）
run   # 或 cd ~/Rosmaster-App/rosmaster && python3 app.py
# APP 运行在 http://<小车IP>:6500

# 5. 底盘串口直控测试（不经ROS2，测试前确认 /dev/myserial 指向底盘 ttyUSB1）
ls -l /dev/myserial /dev/rplidar /dev/sensors
python3 ~/rosmaster_test.py 1 50   # 前进
python3 ~/rosmaster_test.py 7 50   # 停止
```

## Mock 联调与巡检闭环

真实导航、视觉、传感器未完全接入前，可先跑 mock 链路完成任务调度和前端联调。工程结构保持正式模块命名，mock 只体现在运行模式和 `config/navigation/mock/` 配置中。

```bash
# 1. 进入仓库目录
cd icar-ros2-patrol

# 2. 启动最小导航 mock 数据模式
./scripts/start_navigation.sh mock

# 3. 启动完整导航 mock 联调
./scripts/start_navigation.sh mock-full

# 4. 总演示入口（导航 mock）
./scripts/start_demo.sh nav-mock

# 5. 不依赖 ROS2 的本机 mock 演示
python3 scripts/run_mock_demo.py

# 6. ROS2 环境内 mock 巡检联调，不会启动真实底盘
source /opt/ros/foxy/setup.bash
source install/setup.bash
./scripts/start_mock_demo.sh
```

说明：

- `/map`、`/pose`、`/goal_pose`、`/scan` 使用标准 ROS2 消息
- `/nav_status`、`/obstacle_status` 使用正式自定义消息；`/obstacle_status` 默认由真实 `/scan` 前方扇区判定生成
- 当前运行的是正式模块目录下的 mock 数据模式，不再使用 `mock_*` 实现文件作为工程主结构
- 后续真车恢复后，优先保持 Topic 名和字段约定不变，再切回真实数据源

后续各模块需要提供的 Topic、字段和验收材料见 `docs/模块集成产出清单.md`。

### 实车联调注意

- 正常设备映射应为：`/dev/rplidar -> ttyUSB0`，`/dev/myserial -> ttyUSB1`，`/dev/sensors -> ttyUSB2`
- 2026-07-07 排查时发现宿主机 `/dev/myserial` 曾错误指向 `ttyUSB0`（雷达口），会导致 Rosmaster-App 和 `rosmaster_test.py` 无法正确控制底盘；遇到 APP 不能动或雷达/底盘串口互相占用时，优先检查该映射
- 容器内 alias 与宿主机 alias 可能不同。宿主机旧 alias `s/d` 曾指向已退出容器，进入容器前先执行 `docker ps -a`，不要只依赖旧别名
- ROS2 业务节点未启动时，`ros2 topic list -t` 只会看到 `/parameter_events` 和 `/rosout`，这是未启动链路，不是 Topic 表错误

## 开发计划

| 阶段 | 日期 | 主要目标 | 关键产出 | 负责人 |
|------|------|----------|----------|--------|
| 阶段1：环境与基础控制 | 7.7-7.8 | 设备环境跑通；确认小车连接、ROS2、APP控制链路；建仓库和目录 | 环境记录、连接步骤、控制演示、仓库初版 | 熊浩宇、李雨晨 |
| 阶段2：P0 核心链路 | 7.8-7.10 | 跑通雷达、SLAM、导航、视觉、传感器基础实验 | 雷达图、地图截图、摄像头画面、传感器数据截图 | 曹莹、韦雪、王璐 |
| 阶段3：中期检查 | 7.11 | 完成架构、分工、甘特图、最低演示版本、LLM JSON Demo | 中期PPT、初版视频、任务JSON Demo | 熊浩宇统筹 |
| 阶段4：P1 巡检闭环 | 7.12-7.13 | 完成任务下发、路线巡检、导航、检测、采集、日志展示 | 完整任务日志、前端展示、异常记录 | 全员 |
| 阶段5：LLM加分与材料收口 | 7.13-7.14 | 接入LLM任务解析/报告生成；完善文档、测试报告、视频 | 最终PPT、使用手册、测试报告、演示视频 | 熊浩宇、王璐、李雨晨 |
| 阶段6：最终答辩 | 7.15 | 现场演示 + 视频兜底 + 全员发言 | 答辩展示 | 全员 |

### CI/CD 与提交管理

| 管理项 | 规则 | 负责人 | 验收方式 |
|--------|------|--------|----------|
| 仓库名称 | icar-ros2-patrol | 熊浩宇 | 仓库地址可访问 |
| 目录结构 | app/navigation/vision/sensor/llm/docs/scripts/test/videos/config/logs | 熊浩宇 | README中说明目录用途 |
| 分支策略 | main主分支 + 模块文件夹协作 | 熊浩宇/全员 | 提交记录清晰 |
| 提交规范 | 格式：`模块名：动作说明`，如 `navigation：新增目标点导航测试记录` | 全员 | 每日有效提交或文档更新 |
| CI基础检查 | 检查README、目录完整性、Python语法、Shell脚本存在性/可执行性 | 熊浩宇 | CI配置文件或检查截图 |
| 启动脚本 | start_app/navigation/vision/sensor/demo.sh | 熊浩宇统筹 | 按脚本可复现核心模块 |
| 版本交付 | 中期 v0.1-mid，最终 v1.0-final | 熊浩宇 | Release/压缩包/提交记录 |

---

## 演示与安全边界

- **LLM 不直接控制底盘**：LLM 不发布 `/cmd_vel`，所有自然语言输出先转换为结构化任务 JSON，经 task_manager_node 进行动作白名单和安全规则校验。
- **现场演示以 P0/P1 为主**：LLM 只作为最后加分展示。
- **SLAM/导航兜底**：不稳定环节提前录制稳定视频兜底。

---

> *本项目为实训课程项目，用于学习 ROS2 机器人操作系统、多模块协作开发与 Git 团队协作。*
lib/
├── main.dart                    # APP 入口 + 主导航
├── theme/
│   └── app_theme.dart           # 全局主题配色 + 通用组件 (AppCard, StatusBadge)
├── pages/
│   ├── control_page.dart        # 控制台 - 方向控制/速度调节/快捷操作
│   ├── status_page.dart         # 状态监控 - 摄像头/系统信息/导航状态
│   ├── sensor_page.dart         # 传感器数据 - 温湿度/PM2.5/烟雾/光照/气压
│   ├── mission_log_page.dart    # 任务日志 - 时间线/筛选/统计
│   └── settings_page.dart       # 设置 - 连接/控制/告警/关于
└── services/
    ├── car_tcp_service.dart     # WebSocket 通信服务（连接/收发/自动重连）
    ├── car_commands.dart        # 指令定义（纯文本: forward/backward/left/right/stop/start）
    └── car_controller.dart      # 小车控制器 - ChangeNotifier 单例全局状态管理
```

## 快速开始

### 环境要求

- Flutter SDK 3.x（stable channel）
- Android SDK（打包 APK 需要）
- Chrome（Web 预览）

### 安装依赖

```bash
flutter pub get
```

### Web 预览

```bash
flutter run -d chrome --web-port=8080
```

### 打包 APK

```bash
flutter build apk --release
# 输出: build/app/outputs/flutter-apk/app-release.apk
```

> **注意：** 如果 Gradle 下载超时，在 `android/gradle.properties` 中添加代理配置：
> ```
> systemProp.http.proxyHost=127.0.0.1
> systemProp.http.proxyPort=你的代理端口
> systemProp.https.proxyHost=127.0.0.1
> systemProp.https.proxyPort=你的代理端口
> ```

## 配色方案

| 颜色 | Hex | 用途 |
|------|-----|------|
| 浅灰背景 | #EAEFEF | 页面底色 |
| 蓝灰 | #BFC9D1 | 边框、辅助文字 |
| 深蓝 | #25343F | 主文字、标题 |
| 橙色 | #FF9B51 | 按钮、强调、选中态 |
| 蓝紫 | #4B5694 | 信息标签、点缀 |

## 当前开发状态

| 功能 | 状态 | 说明 |
|------|------|------|
| UI 界面（5个Tab） | 已完成 | 完整交互，可安装测试 |
| WebSocket 通信 | 已完成 | 连接 `ws://IP:6500/ws/control`，纯文本指令收发 |
| 控制指令 | 已完成 | forward/backward/left/right/stop/start（来自 app.py 确认） |
| 摄像头画面 | 已完成 | MJPEG HTTP 流 `http://IP:6500/video_feed`，连接后自动显示 |
| 自动重连 | 已完成 | 断线后自动重连，最多 5 次 |
| 传感器数据 | Mock | 需确认 ROS2 Topic 或读取方式 |
| 导航状态 | Mock | 需确认导航 Topic 和地图格式 |
| YOLO 检测 | 待集成 | 视频流 `http://IP:6500/yolo_video_feed` 已就绪 |

## 待确认事项

P0 已解决（通过阅读 app.py 源码 + APP接入指南.md）：
- ✅ WebSocket 控制指令格式：纯文本 `forward/backward/left/right/stop/start`
- ✅ 摄像头视频流：MJPEG HTTP 流 `http://IP:6500/video_feed`

待确认（P1）：
1. **传感器数据读取方式** — ROS2 Topic 还是其他接口
2. **导航状态与 SLAM 地图** — Topic 名称和数据格式
3. **YOLO 检测集成** — `yolo_video_feed` 和 `yolo_detailed_status` 接口已就绪，待 APP 端集成

## 小车环境信息

- **IP：** 10.90.164.83
- **SSH/VNC 密码：** yahboom
- **WebSocket 端口：** 6500（路径 `/ws/control`）
- **视频流端口：** 6500（路径 `/video_feed`）
- **导航容器：** autodrive_ros2（命令: `s`/`t`/`d`）
- **视觉容器：** icar_ros2（命令: `is`/`it`/`id`）
- **底盘串口：** /dev/myserial (ttyUSB1)
- **雷达串口：** /dev/rplidar (ttyUSB0)
- **传感器串口：** /dev/sensors (ttyUSB2)

## 项目信息

- **课程：** 2026 北京交通大学 软件学院 小学期实训
- **项目：** iCar 智能巡检机器人
- **APP 开发：** 李雨晨
