#!/bin/bash
# ============================================================
# start_app.sh
# 启动 APP 控制台相关节点
# 负责人：李雨晨
# ============================================================
#
# 启动节点：
#   - app_control_node    APP/网页控制台与 ROS2 通信桥梁
#
# 用法：
#   ./scripts/start_app.sh
#
# 前置条件：
#   - ROS2 环境已 source（source /opt/ros/humble/setup.bash）
#   - 工作空间已 source（source install/setup.bash）
# ============================================================

set -e

echo "============================================="
echo "  Starting APP Control Module..."
echo "============================================="

# TODO: 启动 APP 后端服务
# ros2 run app_control app_control_node &

# TODO: 启动前端页面（如有）
# cd app/frontend && npm start &

echo "APP Control Module started."
