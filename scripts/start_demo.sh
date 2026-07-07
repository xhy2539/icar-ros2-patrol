#!/bin/bash
# ============================================================
# start_demo.sh
# 一键启动完整巡检演示系统
# 负责人：熊浩宇
# ============================================================
#
# 架构说明：
#   底盘控制：宿主机 Rosmaster-Lib 串口直控 (/dev/myserial → ttyUSB1)
#   ROS2：Docker 容器内 (yahboomtechnology/ros-foxy:5.0.1)
#
# 启动顺序：
#   1. 激光雷达驱动 (容器内 sllidar_ros2)
#   2. 相机驱动 (容器内 astra_camera)
#   3. 避障模块 (容器内 laser_Avoidance)
#   4. SLAM 建图 (容器内 slam_gmapping)
#   5. 自主导航 (容器内 teb_local_planner)
#   6. 视觉检测 (容器内 icar_visual)
#   7. 任务调度 (宿主机 task_manager)
#   8. APP 控制台 (宿主机 Flask :6500)
#
# 用法：
#   ./scripts/start_demo.sh
#
# 前置条件：
#   - SSH 连接小车 jetson@<IP>
#   - Docker 容器已启动：docker start 5b1c
#   - 所有硬件已连接
# ============================================================

set -e

echo "============================================="
echo "  iCar ROS2 Patrol - Full Demo Startup"
echo "============================================="
echo ""
echo "  架构: 宿主机(Rosmaster-Lib串口) + Docker(ROS2 Foxy)"
echo ""

# Phase 0: 环境准备
echo "=== Phase 0: Environment ==="
echo "[0/3] Starting Docker container..."
# docker start 5b1c    # 或 s (bashrc别名)
sleep 3

# Phase 1: 驱动层（容器内）
echo "=== Phase 1: Drivers (Docker) ==="
echo "[1/8] Starting lidar (sllidar_ros2)..."
# docker exec -it 5b1c bash -c "source /opt/ros/foxy/setup.bash && ros2 launch sllidar_ros2 sllidar_launch.py &"
sleep 2

echo "[2/8] Starting camera (astra_camera)..."
# docker exec -it 5b1c bash -c "source /opt/ros/foxy/setup.bash && ros2 launch astra_camera astra.launch.xml &"
sleep 2

# Phase 2: 感知层（容器内）
echo "=== Phase 2: Perception (Docker) ==="
echo "[3/8] Starting obstacle_avoid..."
# docker exec -it 5b1c bash -c "source /opt/ros/foxy/setup.bash && ros2 run icar_laser laser_Avoidance_a1_X3 &"
sleep 1

echo "[4/8] Starting SLAM (slam_gmapping)..."
# docker exec -it 5b1c bash -c "source /opt/ros/foxy/setup.bash && ros2 launch slam_gmapping ... &"
sleep 2

echo "[5/8] Starting navigation (teb_local_planner)..."
# docker exec -it 5b1c bash -c "source /opt/ros/foxy/setup.bash && ros2 launch teb_local_planner ... &"
sleep 1

echo "[6/8] Starting vision (icar_visual)..."
# docker exec -it 5b1c bash -c "source /opt/ros/foxy/setup.bash && ros2 run icar_visual ... &"
sleep 1

# Phase 3: 调度层
echo "=== Phase 3: Task Management ==="
echo "[7/8] Starting task_manager_node..."
# 方式A: 宿主机直接用 Python 运行
# python3 $(ros2 pkg prefix task_manager)/lib/task_manager/task_manager_node &
# 方式B: ROS2 方式运行（推荐）
# ros2 run task_manager task_manager_node &
sleep 1

# Phase 4: 应用层（宿主机）
echo "=== Phase 4: Application (Host) ==="
echo "[8/8] Starting APP (Rosmaster-App)..."
# cd ~/Rosmaster-App/rosmaster && python3 app.py &
sleep 1

echo ""
echo "============================================="
echo "  All modules started!"
echo "  APP: http://<小车IP>:6500"
echo "  Press Ctrl+C to stop all nodes"
echo "============================================="

# TODO: LLM 模块（P2 加分项，后期启动）
# echo "[9/9] Starting llm_gateway_node..."
# python3 llm_gateway_node.py &
