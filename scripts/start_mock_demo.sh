#!/bin/bash
# ============================================================
# start_mock_demo.sh
# 启动 mock 巡检闭环：APP任务 -> 模拟导航 -> 模拟传感器
# -> 模拟视觉 -> task_manager日志 -> 报告生成
#
# 用法：
#   source /opt/ros/foxy/setup.bash
#   source install/setup.bash
#   ./scripts/start_mock_demo.sh
#
# 注意：
#   本脚本不启动真实底盘/雷达/相机，不会让小车运动。
# ============================================================

set -e

echo "Starting ICAR mock patrol demo..."

ros2 run task_manager task_manager_node &
PIDS="$!"
sleep 1

ros2 run task_manager mock_navigation_node &
PIDS="$PIDS $!"

ros2 run task_manager mock_sensor_node &
PIDS="$PIDS $!"

ros2 run task_manager mock_vision_node &
PIDS="$PIDS $!"

ros2 run task_manager report_generator_node &
PIDS="$PIDS $!"

sleep 1
ros2 run task_manager mock_app_node &
PIDS="$PIDS $!"

trap 'echo "Stopping mock demo..."; kill $PIDS 2>/dev/null || true' INT TERM EXIT

echo "Mock demo started. Press Ctrl+C to stop."
wait
