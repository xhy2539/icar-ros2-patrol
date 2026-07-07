#!/bin/bash
# ============================================================
# start_navigation.sh
# 启动导航相关节点（雷达 + SLAM + 避障 + 导航）
# 负责人：曹莹
# ============================================================
#
# 启动节点（按顺序）：
#   1. lidar_node             激光雷达驱动
#   2. obstacle_avoid_node    避障节点
#   3. slam_node              SLAM 建图节点
#   4. navigation_node        自主导航节点
#
# 用法：
#   ./scripts/start_navigation.sh [mode]
#
#   mode:
#     full     启动全部导航节点（默认）
#     lidar    仅启动雷达驱动
#     slam     启动雷达 + SLAM
#     nav      启动雷达 + SLAM + 导航
#
# 前置条件：
#   - ROS2 环境已 source
#   - 工作空间已 source
#   - 激光雷达硬件已连接
# ============================================================

set -e

MODE=${1:-full}

echo "============================================="
echo "  Starting Navigation Module (mode: $MODE)..."
echo "============================================="

# 1. 激光雷达驱动（所有模式都需要）
echo "[1/4] Starting lidar_node..."
# ros2 run navigation lidar_node &
sleep 2

if [ "$MODE" = "lidar" ]; then
    echo "Navigation Module (lidar only) started."
    exit 0
fi

# 2. 避障节点
echo "[2/4] Starting obstacle_avoid_node..."
# ros2 run navigation obstacle_avoid_node &
sleep 1

# 3. SLAM 建图
echo "[3/4] Starting slam_node..."
# ros2 run navigation slam_node &
sleep 2

if [ "$MODE" = "slam" ]; then
    echo "Navigation Module (lidar + SLAM) started."
    exit 0
fi

# 4. 自主导航
echo "[4/4] Starting navigation_node..."
# ros2 run navigation navigation_node &
sleep 1

echo "Navigation Module (full) started."
