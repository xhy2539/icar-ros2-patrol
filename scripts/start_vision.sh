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
#     fake     发布仿真相机图像 topic
#     probe     仅验证相机图像 topic
#     detect    仅目标检测（默认）
#     track     目标检测 + 目标追踪
#     road      道路检测预留模式
#
# 前置条件：
#   - ROS2 环境已 source
#   - 工作空间已 source
#   - 摄像头已连接
#   - YOLO 模型文件已放置
# ============================================================

set -e

MODE=${1:-detect}
IMAGE_TOPIC=${IMAGE_TOPIC:-/camera/color/image_raw}
DETECTIONS_TOPIC=${DETECTIONS_TOPIC:-/vision/detections}
STATUS_TOPIC=${STATUS_TOPIC:-/vision/camera_status}
PUBLISH_ANNOTATED=${PUBLISH_ANNOTATED:-false}
FAKE_FPS=${FAKE_FPS:-15.0}
FAKE_SCENARIO=${FAKE_SCENARIO:-patrol}

echo "============================================="
echo "  Starting Vision Module (mode: $MODE)..."
echo "============================================="
echo "  image topic: $IMAGE_TOPIC"

if [ "$MODE" = "fake" ]; then
    ros2 run vision_patrol fake_camera --ros-args \
        -p image_topic:="$IMAGE_TOPIC" \
        -p fps:="$FAKE_FPS" \
        -p scenario:="$FAKE_SCENARIO"
elif [ "$MODE" = "probe" ]; then
    ros2 run vision_patrol camera_probe --ros-args \
        -p image_topic:="$IMAGE_TOPIC" \
        -p status_topic:="$STATUS_TOPIC"
else
    ENABLE_ROAD=false
    if [ "$MODE" = "road" ]; then
        ENABLE_ROAD=true
    fi

    ros2 run vision_patrol vision_node --ros-args \
        -p image_topic:="$IMAGE_TOPIC" \
        -p detections_topic:="$DETECTIONS_TOPIC" \
        -p mode:="$MODE" \
        -p publish_annotated:="$PUBLISH_ANNOTATED" \
        -p enable_road_detection:="$ENABLE_ROAD"
fi

echo "Vision Module started."
