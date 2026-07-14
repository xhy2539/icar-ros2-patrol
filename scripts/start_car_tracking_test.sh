#!/bin/bash
# One-command field test for vision target tracking.
#
# Safe default: this starts the detector and target_tracker, then publishes a
# tracking command. The tracker only publishes /vision/target_cmd_vel; it does
# not directly drive /cmd_vel_app here.
#
# Usage on the car host:
#   bash scripts/start_car_tracking_test.sh start
#   bash scripts/start_car_tracking_test.sh follow person
#   bash scripts/start_car_tracking_test.sh echo
#   bash scripts/start_car_tracking_test.sh stop

set -u

CONTAINER="${ICAR_VISION_CONTAINER:-icar_ros2}"
ROS_DOMAIN_ID_VALUE="${ICAR_ROS_DOMAIN_ID:-32}"
VISION_WS="${ICAR_VISION_WS:-/root/icar_ros2_ws/icar_ws}"
DETECTION_SCRIPT="${DETECTION_SCRIPT:-/home/jetson/icar-ros2-patrol/scripts/start_car_detection_test.sh}"
TARGET_CLASS="${TARGET_CLASS:-person}"
MIN_CONFIDENCE="${MIN_CONFIDENCE:-0.20}"
MAX_LINEAR_SPEED="${MAX_LINEAR_SPEED:-0.08}"
MAX_ANGULAR_SPEED="${MAX_ANGULAR_SPEED:-0.25}"
DESIRED_BBOX_AREA_RATIO="${DESIRED_BBOX_AREA_RATIO:-0.10}"
CMD_PUBLISH_PERIOD_SEC="${CMD_PUBLISH_PERIOD_SEC:-0.10}"

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

ensure_detector() {
  if [ "${SKIP_DETECTOR_START:-0}" = "1" ]; then
    return 0
  fi

  if [ -x "$DETECTION_SCRIPT" ]; then
    echo "[start] ensuring camera + detector are running..."
    ICAR_ROS_DOMAIN_ID="$ROS_DOMAIN_ID_VALUE" bash "$DETECTION_SCRIPT" start
  else
    echo "[warn] detector script not found: $DETECTION_SCRIPT"
    echo "       start camera + vision_node first, or set DETECTION_SCRIPT=/path/to/script"
  fi
}

start_tracker() {
  ensure_detector

  echo "[start] starting target_tracker..."
  docker exec "$CONTAINER" bash -lc '
    pkill -9 -f "[t]arget_tracker" || true
    rm -f /tmp/icar_target_tracker.log
  '

  docker exec "$CONTAINER" bash -lc "
cat >/tmp/icar_target_tracker.sh <<'EOS'
#!/usr/bin/env bash
$(ros_prefix)
exec ros2 run vision_patrol target_tracker --ros-args \\
  -p detections_topic:=/vision/detections \\
  -p command_topic:=/vision/target_tracking/command \\
  -p cmd_vel_topic:=/vision/target_cmd_vel \\
  -p status_topic:=/vision/target_tracking/status \\
  -p enabled_on_start:=false \\
  -p min_confidence:=$MIN_CONFIDENCE \\
  -p max_linear_speed:=$MAX_LINEAR_SPEED \\
  -p max_angular_speed:=$MAX_ANGULAR_SPEED \\
  -p desired_bbox_area_ratio:=$DESIRED_BBOX_AREA_RATIO \\
  -p cmd_publish_period_sec:=$CMD_PUBLISH_PERIOD_SEC \\
  -p target_classes:='[$TARGET_CLASS]'
EOS
chmod +x /tmp/icar_target_tracker.sh
nohup /tmp/icar_target_tracker.sh >/tmp/icar_target_tracker.log 2>&1 &
"

  sleep 3
  send_follow_command "$TARGET_CLASS"
  status_tracker
}

send_follow_command() {
  local class_name="${1:-$TARGET_CLASS}"
  echo "[command] start tracking class: $class_name"
  docker_ros "ros2 topic pub --once /vision/target_tracking/command std_msgs/String \"{data: '{\\\"action\\\":\\\"start\\\",\\\"class_name\\\":\\\"$class_name\\\"}'}\""
}

stop_tracker() {
  echo "[command] stop target tracking"
  docker_ros "ros2 topic pub --once /vision/target_tracking/command std_msgs/String \"{data: '{\\\"action\\\":\\\"stop\\\"}'}\"" >/dev/null 2>&1 || true
  docker_ros "ros2 topic pub --once /vision/target_cmd_vel geometry_msgs/Twist \"{linear: {x: 0.0, y: 0.0, z: 0.0}, angular: {x: 0.0, y: 0.0, z: 0.0}}\"" >/dev/null 2>&1 || true
  docker exec "$CONTAINER" bash -lc 'pkill -9 -f "[t]arget_tracker" || true' >/dev/null 2>&1 || true
}

status_tracker() {
  echo "===== topics ====="
  docker_ros "ros2 topic list | grep -E '/vision/detections|/vision/target_cmd_vel|/vision/target_tracking/status|/vision/target_tracking/command' || true"

  echo "===== tracker processes ====="
  docker exec "$CONTAINER" bash -lc \
    "ps -eo pid,ppid,stat,pcpu,pmem,args | grep -E 'target_tracker|vision_node|astra_camera' | grep -v grep || true"

  echo "===== recent tracker log ====="
  docker exec "$CONTAINER" bash -lc 'tail -80 /tmp/icar_target_tracker.log 2>/dev/null || true'
}

echo_streams() {
  echo "Press Ctrl+C to stop echoing. This does not stop tracking."
  docker_ros "ros2 topic echo /vision/target_tracking/status"
}

echo_cmd_vel() {
  echo "Press Ctrl+C to stop echoing. This does not stop tracking."
  docker_ros "ros2 topic echo /vision/target_cmd_vel"
}

case "${1:-start}" in
  start) start_tracker ;;
  follow) send_follow_command "${2:-$TARGET_CLASS}" ;;
  stop) stop_tracker ;;
  status) status_tracker ;;
  echo) echo_streams ;;
  cmdvel) echo_cmd_vel ;;
  logs)
    docker exec "$CONTAINER" bash -lc 'tail -120 /tmp/icar_target_tracker.log 2>/dev/null || true'
    ;;
  *)
    echo "usage: bash scripts/start_car_tracking_test.sh {start|follow [class]|stop|status|echo|cmdvel|logs}"
    exit 2
    ;;
esac
