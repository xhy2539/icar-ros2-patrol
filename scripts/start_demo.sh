#!/bin/bash
# ============================================================
# start_demo.sh
# Demo entrypoint with mock-first navigation mode
# 负责人：熊浩宇
# ============================================================

set -euo pipefail

SCRIPT_DIR=$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)
PROJECT_ROOT=$(cd "$SCRIPT_DIR/.." && pwd)
MODE=${1:-nav-mock}

cd "$PROJECT_ROOT"

echo "============================================="
echo " iCar ROS2 Patrol Demo Startup"
echo " mode: $MODE"
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

case "$MODE" in
    nav-mock)
        echo "[phase] navigation running in mock data mode"
        echo "[note] starts /map, /pose, /nav_status, /obstacle_status and /scan"
        ./scripts/start_navigation.sh mock-full
        ;;
    nav-mock-basic)
        echo "[phase] navigation basic mock data mode"
        ./scripts/start_navigation.sh mock
        ;;
    nav-mock-with-app)
        echo "[phase] navigation mock data mode + placeholders for app/task_manager"
        echo "[todo] start app_control_node and task_manager_node in their own terminals if they exist locally."
        ./scripts/start_navigation.sh mock-full
        ;;
    real)
        echo "[todo] real demo startup should be wired after the replacement vehicle arrives."
        exit 1
        ;;
    -h|--help|help)
        cat <<'EOF'
Usage:
  ./scripts/start_demo.sh [mode]

Modes:
  nav-mock          Start full navigation chain in mock data mode
  nav-mock-basic    Start /map, /pose and /nav_status only
  nav-mock-with-app Start navigation mock mode and leave notes for app/task_manager
  real              Placeholder for future real robot demo
EOF
        ;;
    *)
        echo "[error] unknown mode: $MODE"
        exit 1
        ;;
esac
