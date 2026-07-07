#!/bin/bash
# ============================================================
# start_vision.sh
# 启动视觉检测模块节点
# 负责人：韦雪
# ============================================================
#
# 启动节点：
#   - vision_node    摄像头驱动 + YOLO 目标检测
#
# 用法：
#   ./scripts/start_vision.sh [mode]
#
#   mode:
#     detect    仅目标检测（默认）
#     track     目标检测 + 目标追踪
#
# 前置条件：
#   - ROS2 环境已 source
#   - 工作空间已 source
#   - 摄像头已连接
#   - YOLO 模型文件已放置
# ============================================================

set -e

MODE=${1:-detect}

echo "============================================="
echo "  Starting Vision Module (mode: $MODE)..."
echo "============================================="

# TODO: 启动视觉检测节点
# ros2 run vision vision_node --ros-args -p mode:=$MODE &

# TODO: 如果需要单独启动追踪节点
# if [ "$MODE" = "track" ]; then
#     ros2 run vision tracking_node &
# fi

echo "Vision Module started."
