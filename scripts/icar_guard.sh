#!/bin/bash
# Lightweight service guard — only restarts dead processes, never kills running ones.
# Run via cron: * * * * * /home/jetson/icar-ros2-patrol/scripts/icar_guard.sh

LOG=/tmp/icar_guard.log
exec 2>>$LOG; set -euo pipefail

log() { echo "$(date +%H:%M:%S) guard: $*" >> $LOG; }

if pgrep -f '[/]home/jetson/icar-ros2-patrol/scripts/icar_startup.sh' >/dev/null 2>&1 || \
   pgrep -f '[/]home/jetson/icar-deploy/current/scripts/icar_startup.sh' >/dev/null 2>&1; then
  log "startup active; skipping"
  exit 0
fi

count_live() {
  local container="$1" pattern="$2"
  docker exec "$container" bash -c '
    pattern="$1"
    ps -eo stat=,comm=,args= | awk -v p="$pattern" '"'"'
      $1 !~ /^Z/ && $2 !~ /^(python3|python|ros2|bash|sh|awk|grep|ps)$/ && index($0, p) { count++ }
      END { print count + 0 }
    '"'"'
  ' _ "$pattern" 2>/dev/null || echo 0
}

ensure_single() {
  local name="$1" container="$2" pattern="$3"
  shift 3
  # Count live (non-zombie) processes
  local count
  count=$(count_live "$container" "$pattern")
  count=${count// /}
  if [ "$count" -eq 1 ]; then return 0; fi
  if [ "$count" -gt 1 ]; then
    log "killing $count $name extras"
    docker exec "$container" pkill -f "$pattern" 2>/dev/null || true
    sleep 2
  fi
  log "starting $name"
  docker exec -d "$container" bash -lc "source /opt/ros/foxy/setup.bash; source /root/icar_ros2_ws/icar_ws/install/setup.bash; export ROS_DOMAIN_ID=30; $*" 2>/dev/null || true
}

# Variant for autodrive_ros2 (different setup paths)
ensure_single_ad() {
  local name="$1" pattern="$2"; shift 2
  local count
  count=$(count_live autodrive_ros2 "$pattern")
  count=${count// /}
  if [ "$count" -eq 1 ]; then return 0; fi
  if [ "$count" -gt 1 ]; then
    log "killing $count $name extras"
    docker exec autodrive_ros2 pkill -f "$pattern" 2>/dev/null || true
    sleep 2
  fi
  log "starting $name"
  docker exec -d autodrive_ros2 bash -lc "source /opt/ros/foxy/setup.bash; source /root/yahboomcar_ros2_ws/software/library_ws/install/setup.bash; source /root/yahboomcar_ros2_ws/yahboomcar_ws/install/setup.bash; source /root/icar_app_ws/install/setup.bash; export ROS_DOMAIN_ID=30; $*" 2>/dev/null || true
}

# ── Disable buzzer ──
docker exec icar_ros2 bash -lc "source /opt/ros/foxy/setup.bash && ros2 topic pub -1 /safety/alarm_sound_enabled std_msgs/msg/Bool \"data: false\" 2>/dev/null" || true
docker exec autodrive_ros2 bash -lc "source /opt/ros/foxy/setup.bash && ros2 topic pub -1 /Buzzer std_msgs/msg/Bool \"data: false\" 2>/dev/null" || true

# ── Critical ──
ensure_single cloud_bridge  icar_ros2 "/install/cloud_bridge/lib/cloud_bridge/cloud_bridge_node" \
  "ros2 run cloud_bridge cloud_bridge_node"

# ── autodrive_ros2 ──
ensure_single_ad velocity_mux "/root/icar_app_ws/install/app_control/lib/app_control/velocity_mux_node" \
  "ros2 run app_control velocity_mux_node"

ensure_single_ad app_bridge "/root/icar_app_ws/install/app_control/lib/app_control/app_bridge_node" \
  "ros2 run app_control app_bridge_node"

# ── Vision ──
ensure_single vision_node   icar_ros2 "/install/vision_patrol/lib/vision_patrol/vision_node" \
  "source /root/icar_ros2_ws/software/library_ws/install/setup.bash; ros2 run vision_patrol vision_node --ros-args -p image_topic:=/camera/color/image_raw -p detector_backend:=yolo -p inference_frame_stride:=6 -p yolo_model:=/root/icar_ros2_ws/icar_ws/models/yolo11n.pt -p yolo_device:=cpu -p yolo_imgsz:=320 -p yolo_confidence:=0.20 -p target_classes:='[person,obstacle]' -p publish_annotated:=true"

ensure_single mjpeg_server  icar_ros2 "/install/vision_patrol/lib/vision_patrol/mjpeg_server" \
  "source /root/icar_ros2_ws/software/library_ws/install/setup.bash; ros2 run vision_patrol mjpeg_server --ros-args -p raw_topic:=/camera/color/image_raw -p listen_host:=127.0.0.1 -p listen_port:=6502"

# ── Navigation ──
ensure_single obstacle_avoid icar_ros2 "/install/navigation/lib/navigation/obstacle_avoid_node" \
  "ros2 run navigation obstacle_avoid_node --mode real"
