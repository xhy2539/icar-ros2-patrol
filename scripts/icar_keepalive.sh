#!/bin/bash
# iCar keepalive — restart critical services if they die.
# Run via cron every 60s: * * * * * /home/jetson/icar-ros2-patrol/scripts/icar_keepalive.sh

set -euo pipefail
LOG="/tmp/icar_keepalive.log"

log() { echo "$(date '+%H:%M:%S') $*" >> "$LOG"; }

restart_if_dead() {
  local container="$1" node_name="$2" pkg="$3" exe="$4" logfile="$5"
  shift 5
  if docker exec "$container" pgrep -f "$exe" >/dev/null 2>&1; then
    return 0
  fi
  log "restarting $node_name"
  local cmd="source /opt/ros/foxy/setup.bash; source /root/icar_ros2_ws/icar_ws/install/setup.bash; export ROS_DOMAIN_ID=30; nohup ros2 run $pkg $exe $* >$logfile 2>&1 &"
  docker exec -d "$container" bash -lc "$cmd" 2>/dev/null || true
}

restart_if_dead icar_ros2 cloud_bridge_node cloud_bridge cloud_bridge_node /tmp/cloud_bridge.log

# vision stack (only if camera is publishing)
if docker exec autodrive_ros2 bash -lc "source /opt/ros/foxy/setup.bash && ros2 topic info /camera/color/image_raw 2>/dev/null" | grep -q "Publisher count: [1-9]"; then
  VISION_WS=/root/icar_ros2_ws/icar_ws
  if ! docker exec icar_ros2 pgrep -f "vision_patrol/vision_node" >/dev/null 2>&1; then
    log "restarting vision_node"
    docker exec -d icar_ros2 bash -lc "source /opt/ros/foxy/setup.bash; source /root/icar_ros2_ws/software/library_ws/install/setup.bash; source $VISION_WS/install/setup.bash; ros2 run vision_patrol vision_node --ros-args -p image_topic:=/camera/color/image_raw -p detector_backend:=yolo -p inference_frame_stride:=6 -p yolo_model:=$VISION_WS/models/yolo11n.pt -p yolo_device:=cpu -p yolo_imgsz:=320 -p yolo_confidence:=0.20 -p publish_annotated:=true >/tmp/icar_vision.log 2>&1" 2>/dev/null || true
  fi
  if ! docker exec icar_ros2 pgrep -f "vision_patrol/mjpeg_server" >/dev/null 2>&1; then
    log "restarting mjpeg_server"
    docker exec -d icar_ros2 bash -lc "source /opt/ros/foxy/setup.bash; source /root/icar_ros2_ws/software/library_ws/install/setup.bash; source $VISION_WS/install/setup.bash; ros2 run vision_patrol mjpeg_server --ros-args -p raw_topic:=/camera/color/image_raw -p listen_host:=127.0.0.1 -p listen_port:=6502 >/tmp/icar_mjpeg.log 2>&1" 2>/dev/null || true
  fi
fi
