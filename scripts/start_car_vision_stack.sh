#!/bin/bash
# Start the real camera and visual pipeline in the unified ROS domain.

set -euo pipefail

CONTAINER="${ICAR_VISION_CONTAINER:-icar_ros2}"
ROS_DOMAIN_ID="${ICAR_ROS_DOMAIN_ID:-30}"
VISION_WS="${ICAR_VISION_WS:-/root/icar_ros2_ws/icar_ws}"

run_node() {
  local logfile="$1"
  shift
  docker exec -e ROS_DOMAIN_ID="$ROS_DOMAIN_ID" "$CONTAINER" bash -lc \
    "source /opt/ros/foxy/setup.bash
     source /root/icar_ros2_ws/software/library_ws/install/setup.bash
     source $VISION_WS/install/setup.bash
     nohup $* </dev/null >$logfile 2>&1 &"
}

# Remove stale domain-32 processes and restart the complete pipeline in 30.
docker exec "$CONTAINER" pkill -f '/vision_patrol/vision_node' 2>/dev/null || true
docker exec "$CONTAINER" pkill -f '/vision_patrol/target_tracker' 2>/dev/null || true
docker exec "$CONTAINER" pkill -f '/vision_patrol/dataset_recorder' 2>/dev/null || true
docker exec "$CONTAINER" pkill -f '/vision_patrol/mjpeg_server' 2>/dev/null || true
docker exec "$CONTAINER" pkill -f '/astra_camera/lib/astra_camera/astra_camera_node' 2>/dev/null || true
docker exec "$CONTAINER" pkill -f 'ros2 launch astra_camera astro_pro_plus.launch.xml' 2>/dev/null || true
sleep 2

run_node /tmp/icar_camera.log \
  ros2 launch astra_camera astro_pro_plus.launch.xml
sleep 4

run_node /tmp/icar_vision.log \
  ros2 run vision_patrol vision_node --ros-args \
    -p image_topic:=/camera/color/image_raw \
    -p detector_backend:=yolo \
    -p inference_frame_stride:=6 \
    -p yolo_model:=$VISION_WS/models/yolo11n.pt \
    -p yolo_device:=cpu \
    -p yolo_imgsz:=320 \
    -p yolo_confidence:=0.20 \
    -p water_detector_backend:=none \
    -p target_classes:='[person,obstacle]' \
    -p publish_annotated:=true \
    -p annotated_topic:=/vision/annotated_image

run_node /tmp/icar_capture.log \
  ros2 run vision_patrol dataset_recorder --ros-args \
    -p image_topic:=/camera/color/image_raw \
    -p save_dir:=/tmp/icar_vision_dataset \
    -p max_images:=200

run_node /tmp/icar_tracker.log \
  ros2 run vision_patrol target_tracker --ros-args \
    -p detections_topic:=/vision/detections \
    -p cmd_vel_topic:=/vision/target_cmd_vel \
    -p enabled_on_start:=false \
    -p min_confidence:=0.20 \
    -p max_linear_speed:=0.08 \
    -p max_angular_speed:=0.25 \
    -p desired_bbox_area_ratio:=0.10

run_node /tmp/icar_mjpeg.log \
  ros2 run vision_patrol mjpeg_server --ros-args \
    -p raw_topic:=/camera/color/image_raw \
    -p annotated_topic:=/vision/annotated_image \
    -p listen_host:=127.0.0.1 \
    -p listen_port:=6502

echo "Vision stack started in ROS domain $ROS_DOMAIN_ID"
