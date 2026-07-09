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
