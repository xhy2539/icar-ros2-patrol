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
#     record    可控截图/数据采集
#     detect    仅目标检测（默认）
#     track     目标追踪速度建议（默认不直接控制 /cmd_vel）
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
CAPTURE_COMMAND_TOPIC=${CAPTURE_COMMAND_TOPIC:-/vision/capture_command}
CAPTURE_STATUS_TOPIC=${CAPTURE_STATUS_TOPIC:-/vision/capture_status}
SAVE_DIR=${SAVE_DIR:-/tmp/icar_vision_dataset}
AUTO_INTERVAL_SEC=${AUTO_INTERVAL_SEC:-0.0}
MAX_IMAGES=${MAX_IMAGES:-200}
TRACK_COMMAND_TOPIC=${TRACK_COMMAND_TOPIC:-/vision/target_tracking/command}
TRACK_CMD_TOPIC=${TRACK_CMD_TOPIC:-/vision/target_cmd_vel}
TRACK_STATUS_TOPIC=${TRACK_STATUS_TOPIC:-/vision/target_tracking/status}
TARGET_CLASSES=${TARGET_CLASSES:-person}
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
elif [ "$MODE" = "record" ]; then
    ros2 run vision_patrol dataset_recorder --ros-args \
        -p image_topic:="$IMAGE_TOPIC" \
        -p command_topic:="$CAPTURE_COMMAND_TOPIC" \
        -p status_topic:="$CAPTURE_STATUS_TOPIC" \
        -p save_dir:="$SAVE_DIR" \
        -p auto_interval_sec:="$AUTO_INTERVAL_SEC" \
        -p max_images:="$MAX_IMAGES"
elif [ "$MODE" = "track" ]; then
    ros2 run vision_patrol target_tracker --ros-args \
        -p detections_topic:="$DETECTIONS_TOPIC" \
        -p command_topic:="$TRACK_COMMAND_TOPIC" \
        -p cmd_vel_topic:="$TRACK_CMD_TOPIC" \
        -p status_topic:="$TRACK_STATUS_TOPIC" \
        -p enabled_on_start:=false \
        -p target_classes:="[$TARGET_CLASSES]"
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
