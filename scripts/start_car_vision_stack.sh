#!/bin/bash
# Start the real camera and visual pipeline in the unified ROS domain.

set -euo pipefail

CONTAINER="${ICAR_VISION_CONTAINER:-icar_ros2}"
ROS_DOMAIN_ID="${ICAR_ROS_DOMAIN_ID:-30}"
VISION_WS="${ICAR_VISION_WS:-/root/icar_ros2_ws/icar_ws}"

# Write a self-contained wrapper script inside the container and run it via
# nohup.  The wrapper is a single command (not `bash -c ... &') so pkill
# patterns never match the killer, and `exec' replaces the shell with the
# ROS node — one process, no zombie bash parent.
run_node() {
  local logfile="$1"
  shift
  # Build a safely-quoted command string so we can inline it in a wrapper
  # script without worrying about spaces or special characters.
  local cmd_str
  printf -v cmd_str '%q ' "$@"
  local script="/tmp/icar_run_$(date +%s)_$$.sh"
  # Unquoted heredoc delimiter (ICAR_EOF without quotes) so that $cmd_str,
  # $ROS_DOMAIN_ID and $VISION_WS are expanded by *this* shell before the
  # container sees them.
  docker exec -e ROS_DOMAIN_ID="$ROS_DOMAIN_ID" "$CONTAINER" bash -lc \
    "cat > $script <<ICAR_EOF
#!/usr/bin/env bash
export ROS_DOMAIN_ID=$ROS_DOMAIN_ID
source /opt/ros/foxy/setup.bash
source /root/icar_ros2_ws/software/library_ws/install/setup.bash
source $VISION_WS/install/setup.bash
exec $cmd_str
ICAR_EOF
     chmod +x $script
     nohup $script </dev/null >$logfile 2>&1 &"
}

# ------------------------------------------------------------------ cleanup
# Bracket trick ([t] instead of t) prevents pkill from matching its own
# command line.  SIGKILL (-9) guarantees the old process is gone.
_cleanup() {
  local node_pattern="$1"
  docker exec "$CONTAINER" bash -lc \
    "pkill -9 -f \"$node_pattern\" 2>/dev/null || true"
}
_cleanup '[v]ision_node'
_cleanup '[t]arget_tracker'
_cleanup '[d]ataset_recorder'
_cleanup '[m]jpeg_server'
_cleanup '[a]stra_camera_node'
_cleanup '[r]os2 launch astra_camera'
sleep 3

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
    -p yolo_confidence:=0.15 \
    -p water_detector_backend:=yolo \
    -p water_model:=$VISION_WS/models/water_seg_v1.pt \
    -p water_device:=cpu \
    -p water_confidence:=0.15 \
    -p water_imgsz:=320 \
    -p water_max_area_ratio:=0.85 \
    -p water_max_mask_area_ratio:=0.75 \
    -p water_refine_reflection_enabled:=true \
    -p water_class_name:=water \
    -p target_classes:='[person,obstacle,water]' \
    -p publish_annotated:=true \
    -p annotated_topic:=/vision/annotated_image

run_node /tmp/icar_capture.log \
  ros2 run vision_patrol dataset_recorder --ros-args \
    -p image_topic:=/camera/color/image_raw \
    -p save_dir:=/tmp/icar_vision_dataset \
    -p max_images:=200

# ── Tracking parameters ──────────────────────────────────────────────
# desired_bbox_area_ratio  controls following distance:
#   LARGER  (0.30+) → car gets closer before stopping
#   SMALLER (0.10)  → car keeps farther away
# linear_gain: how aggressively the car accelerates (0.25–0.45)
# deadband_area: "good enough" zone where no forward/back is commanded
# max_linear_speed: safety cap, keep ≤ 0.15 m/s when following people
# max_angular_speed: turning speed cap
run_node /tmp/icar_tracker.log \
  ros2 run vision_patrol target_tracker --ros-args \
    -p detections_topic:=/vision/detections \
    -p cmd_vel_topic:=/vision/target_cmd_vel \
    -p enabled_on_start:=false \
    -p min_confidence:=0.15 \
    -p desired_bbox_area_ratio:=0.28 \
    -p deadband_area:=0.05 \
    -p linear_gain:=0.35 \
    -p angular_gain:=0.70 \
    -p max_linear_speed:=0.12 \
    -p max_angular_speed:=0.40 \
    -p cmd_publish_period_sec:=0.10 \
    -p lost_timeout_sec:=1.2

run_node /tmp/icar_mjpeg.log \
  ros2 run vision_patrol mjpeg_server --ros-args \
    -p raw_topic:=/camera/color/image_raw \
    -p annotated_topic:=/vision/annotated_image \
    -p listen_host:=127.0.0.1 \
    -p listen_port:=6502

wait_for_raw_snapshot() {
  for _ in $(seq 1 15); do
    if docker exec "$CONTAINER" curl --fail --silent --show-error \
      --max-time 2 http://127.0.0.1:6502/snapshot >/dev/null 2>&1; then
      return 0
    fi
    sleep 2
  done
  return 1
}

# Astra UVC can need a longer USB release interval during a hot service
# restart. Retry the camera owner once while keeping all consumers subscribed.
if ! wait_for_raw_snapshot; then
  echo "Raw camera frame not ready; restarting Astra once"
  _cleanup '[a]stra_camera_node'
  _cleanup '[r]os2 launch astra_camera'
  sleep 5
  run_node /tmp/icar_camera.log \
    ros2 launch astra_camera astro_pro_plus.launch.xml
  wait_for_raw_snapshot
fi

echo "Vision stack started in ROS domain $ROS_DOMAIN_ID"
