#!/bin/bash
# Full-feature vision_node — person+obstacle, annotated, normal resolution, no water
set -e
docker exec icar_ros2 pkill -f vision_node 2>/dev/null || true
sleep 2

docker exec -d icar_ros2 bash -lc '
source /opt/ros/foxy/setup.bash
source /root/icar_ros2_ws/software/library_ws/install/setup.bash
source /root/icar_ros2_ws/icar_ws/install/setup.bash
ros2 run vision_patrol vision_node --ros-args \
  -p image_topic:=/camera/color/image_raw \
  -p detector_backend:=yolo \
  -p inference_frame_stride:=6 \
  -p yolo_model:=/root/icar_ros2_ws/icar_ws/models/yolo11n.pt \
  -p yolo_device:=cpu \
  -p yolo_imgsz:=320 \
  -p yolo_confidence:=0.20 \
  -p target_classes:="[person,obstacle]" \
  -p publish_annotated:=true \
  -p annotated_topic:=/vision/annotated_image \
  >/tmp/icar_vision.log 2>&1
'
sleep 12
docker exec icar_ros2 pgrep -f vision_node >/dev/null && echo "vision RUNNING" || echo "vision DEAD"
docker exec icar_ros2 tail -3 /tmp/icar_vision.log 2>/dev/null
