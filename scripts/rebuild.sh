#!/bin/bash
# ============================================================
# rebuild.sh — 在车上执行的快速重编译脚本
#
# 用法（SSH 小车后）：
#   cd ~/icar-ros2-patrol && git pull && bash scripts/rebuild.sh
#   bash scripts/rebuild.sh --run   # 编译 + 启动 mock demo
# ============================================================
set -e

CONTAINER="${ICAR_CONTAINER:-icar_ros2}"
WS="/root/ros2_ws"
PKGS="icar_interfaces task_manager cloud_bridge vision"

echo "=== 同步代码到容器 ==="
cd "$(dirname "$0")/.."
tar cf - $PKGS | docker exec -i $CONTAINER bash -c "mkdir -p $WS/src && cd $WS/src && rm -rf $PKGS && tar xf -"

echo "=== 编译 ==="
docker exec $CONTAINER bash -c "cd $WS && source /opt/ros/foxy/setup.bash && colcon build --symlink-install"

echo "=== 完成 ==="
echo "启动命令: docker exec -it $CONTAINER bash"
echo "         source $WS/install/setup.bash"
echo "         ros2 run task_manager task_manager_node"

if [ "${1:-}" = "--run" ]; then
    echo ""
    echo "=== 启动 Mock Demo ==="
    docker exec $CONTAINER bash -c "
        source $WS/install/setup.bash
        ros2 run task_manager task_manager_node &
        sleep 1
        ros2 run task_manager mock_navigation_node &
        sleep 1
        ros2 run task_manager mock_sensor_node &
        sleep 1
        ros2 run task_manager mock_vision_node &
        sleep 1
        ros2 run task_manager report_generator_node &
        sleep 1
        ros2 run task_manager mock_app_node &
        sleep 12
        echo ===DONE===
    "
fi
