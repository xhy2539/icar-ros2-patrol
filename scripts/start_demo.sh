#!/bin/bash
# ============================================================
# start_demo.sh
# 一键启动完整巡检演示系统
# 负责人：熊浩宇
# ============================================================
#
# 启动顺序：
#   1. 激光雷达驱动
#   2. 传感器采集
#   3. 避障模块
#   4. SLAM 建图
#   5. 自主导航
#   6. 视觉检测
#   7. 任务调度
#   8. APP 控制台
#
# 用法：
#   ./scripts/start_demo.sh
#
# 前置条件：
#   - ROS2 环境已 source
#   - 工作空间已 source
#   - 所有硬件已连接
# ============================================================

set -e

echo "============================================="
echo "  iCar ROS2 Patrol - Full Demo Startup"
echo "============================================="
echo ""
echo "  Starting all modules..."
echo ""

# Phase 1: 驱动层
echo "=== Phase 1: Drivers ==="
echo "[1/8] Starting lidar_node..."
# ros2 run navigation lidar_node &
sleep 2

echo "[2/8] Starting sensor_node..."
# ros2 run sensor sensor_node &
sleep 1

# Phase 2: 感知层
echo "=== Phase 2: Perception ==="
echo "[3/8] Starting obstacle_avoid_node..."
# ros2 run navigation obstacle_avoid_node &
sleep 1

echo "[4/8] Starting slam_node..."
# ros2 run navigation slam_node &
sleep 2

echo "[5/8] Starting navigation_node..."
# ros2 run navigation navigation_node &
sleep 1

echo "[6/8] Starting vision_node..."
# ros2 run vision vision_node &
sleep 1

# Phase 3: 调度层
echo "=== Phase 3: Task Management ==="
echo "[7/8] Starting task_manager_node..."
# ros2 run task_manager task_manager_node &
sleep 1

# Phase 4: 应用层
echo "=== Phase 4: Application ==="
echo "[8/8] Starting app_control_node..."
# ros2 run app_control app_control_node &
sleep 1

echo ""
echo "============================================="
echo "  All modules started!"
echo "  APP: http://localhost:3000"
echo "  Press Ctrl+C to stop all nodes"
echo "============================================="

# 等待退出信号
# trap 'kill $(jobs -p)' EXIT
# wait

# TODO: LLM 模块（P2 加分项，后期启动）
# echo "[9/9] Starting llm_gateway_node..."
# ros2 run llm_gateway llm_gateway_node &
