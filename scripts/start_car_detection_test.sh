#!/bin/bash
# One-command field test for camera + vision detection.
#
# It intentionally avoids dataset_recorder, mjpeg_server, and target_tracker
# so a Jetson Nano/X3 class CPU is not overloaded while checking detection.
#
# Usage on the car host:
#   bash scripts/start_car_detection_test.sh start
#   bash scripts/start_car_detection_test.sh status
#   bash scripts/start_car_detection_test.sh view
#   bash scripts/start_car_detection_test.sh logs
#   bash scripts/start_car_detection_test.sh stop

set -u

CONTAINER="${ICAR_VISION_CONTAINER:-icar_ros2}"
ROS_DOMAIN_ID_VALUE="${ICAR_ROS_DOMAIN_ID:-32}"
VISION_WS="${ICAR_VISION_WS:-/root/icar_ros2_ws/icar_ws}"
IMAGE_TOPIC="${IMAGE_TOPIC:-/camera/color/image_raw}"
ANNOTATED_TOPIC="${ANNOTATED_TOPIC:-/vision/annotated_image}"
YOLO_MODEL="${YOLO_MODEL:-$VISION_WS/models/yolo11n.pt}"
WATER_MODEL="${WATER_MODEL:-$VISION_WS/models/water_seg_v1.pt}"
YOLO_IMGSZ="${YOLO_IMGSZ:-320}"
YOLO_CONFIDENCE="${YOLO_CONFIDENCE:-0.20}"
WATER_IMGSZ="${WATER_IMGSZ:-320}"
WATER_CONFIDENCE="${WATER_CONFIDENCE:-0.25}"
INFERENCE_FRAME_STRIDE="${INFERENCE_FRAME_STRIDE:-15}"
TARGET_CLASSES="${TARGET_CLASSES:-person,obstacle,water}"
ISOLATE="${ISOLATE:-1}"
DISPLAY_VALUE="${DISPLAY:-:0}"

ros_prefix() {
  cat <<EOS
export ROS_DOMAIN_ID=$ROS_DOMAIN_ID_VALUE
source /opt/ros/foxy/setup.bash
source /root/icar_ros2_ws/software/library_ws/install/setup.bash
source $VISION_WS/install/setup.bash
EOS
}

docker_ros() {
  docker exec -e ROS_DOMAIN_ID="$ROS_DOMAIN_ID_VALUE" "$CONTAINER" bash -lc "
$(ros_prefix)
$*
"
}

stop_test_stack() {
  echo "[stop] stopping test/full vision processes..."
  if [ "$ISOLATE" = "1" ]; then
    # These host-side launchers can restart the full, heavy vision stack.
    pkill -9 -f '[w]eb_gateway.py' 2>/dev/null || true
    pkill -9 -f '[s]tart_car_vision_stack.sh' 2>/dev/null || true
  fi

  docker exec "$CONTAINER" bash -lc '
    pkill -9 -f "[a]stra_camera" || true
    pkill -9 -f "[v]ision_node" || true
    pkill -9 -f "[d]ataset_recorder" || true
    pkill -9 -f "[m]jpeg_server" || true
    pkill -9 -f "[t]arget_tracker" || true
    pkill -9 -f "[r]qt_image_view" || true
  ' >/dev/null 2>&1 || true
}

write_inner_scripts() {
  docker exec "$CONTAINER" bash -lc "
cat >/tmp/icar_detection_camera.sh <<'EOS'
#!/usr/bin/env bash
$(ros_prefix)
exec ros2 launch astra_camera astro_pro_plus.launch.xml
EOS

cat >/tmp/icar_detection_vision.sh <<'EOS'
#!/usr/bin/env bash
$(ros_prefix)
exec ros2 run vision_patrol vision_node --ros-args \\
  -p image_topic:=$IMAGE_TOPIC \\
  -p detector_backend:=yolo \\
  -p inference_frame_stride:=$INFERENCE_FRAME_STRIDE \\
  -p yolo_model:=$YOLO_MODEL \\
  -p yolo_device:=cpu \\
  -p yolo_imgsz:=$YOLO_IMGSZ \\
  -p yolo_confidence:=$YOLO_CONFIDENCE \\
  -p water_detector_backend:=yolo \\
  -p water_model:=$WATER_MODEL \\
  -p water_device:=cpu \\
  -p water_imgsz:=$WATER_IMGSZ \\
  -p water_confidence:=$WATER_CONFIDENCE \\
  -p water_class_name:=water \\
  -p target_classes:='[$TARGET_CLASSES]' \\
  -p fall_detection_enabled:=true \\
  -p publish_annotated:=true \\
  -p annotated_topic:=$ANNOTATED_TOPIC
EOS

chmod +x /tmp/icar_detection_camera.sh /tmp/icar_detection_vision.sh
rm -f /tmp/icar_detection_camera.log /tmp/icar_detection_vision.log
"
}

wait_for_topic() {
  local topic="$1"
  local seconds="${2:-25}"
  local i
  for i in $(seq 1 "$seconds"); do
    if docker_ros "ros2 topic list | grep -qx '$topic'" >/dev/null 2>&1; then
      echo "[ok] topic exists: $topic"
      return 0
    fi
    sleep 1
  done
  echo "[warn] topic not found after ${seconds}s: $topic"
  return 1
}

start_test_stack() {
  stop_test_stack
  sleep 2
  write_inner_scripts

  echo "[start] camera: Astra Plus RGB"
  docker exec "$CONTAINER" bash -lc \
    'nohup /tmp/icar_detection_camera.sh >/tmp/icar_detection_camera.log 2>&1 &'

  if ! wait_for_topic "$IMAGE_TOPIC" 30; then
    echo "===== camera log ====="
    docker exec "$CONTAINER" bash -lc 'tail -120 /tmp/icar_detection_camera.log 2>/dev/null || true'
    exit 1
  fi

  echo "[start] detection: person + obstacle + water"
  echo "[note] stair/threshold/fall_hazard is not in vision_node yet; this script will not detect it until that code is integrated."
  docker exec "$CONTAINER" bash -lc \
    'nohup /tmp/icar_detection_vision.sh >/tmp/icar_detection_vision.log 2>&1 &'

  sleep 12
  status_test_stack
}

status_test_stack() {
  echo "===== topics ====="
  docker_ros "ros2 topic list | grep -E '/camera/color/image_raw|/vision/annotated_image|/vision/detections|/vision/detections_json' || true"

  echo "===== processes ====="
  docker exec "$CONTAINER" bash -lc \
    "ps -eo pid,ppid,stat,pcpu,pmem,args | grep -E 'astra_camera|vision_node|dataset_recorder|mjpeg_server|target_tracker' | grep -v grep || true"

  echo "===== memory ====="
  free -h
}

view_image() {
  xhost +local:root >/dev/null 2>&1 || true
  docker exec \
    -e DISPLAY="$DISPLAY_VALUE" \
    -e QT_X11_NO_MITSHM=1 \
    -e ROS_DOMAIN_ID="$ROS_DOMAIN_ID_VALUE" \
    "$CONTAINER" bash -lc "
$(ros_prefix)
ros2 run rqt_image_view rqt_image_view
"
}

show_logs() {
  echo "===== camera log ====="
  docker exec "$CONTAINER" bash -lc 'tail -120 /tmp/icar_detection_camera.log 2>/dev/null || true'
  echo "===== vision log ====="
  docker exec "$CONTAINER" bash -lc 'tail -120 /tmp/icar_detection_vision.log 2>/dev/null || true'
}

case "${1:-start}" in
  start) start_test_stack ;;
  stop) stop_test_stack ;;
  status) status_test_stack ;;
  logs) show_logs ;;
  view) view_image ;;
  *)
    echo "usage: bash scripts/start_car_detection_test.sh {start|stop|status|logs|view}"
    exit 2
    ;;
esac
