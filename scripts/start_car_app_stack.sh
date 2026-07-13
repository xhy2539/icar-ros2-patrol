#!/bin/bash
# Start the safe app stack on the Jetson host after autodrive_ros2 is running.

set -euo pipefail

CONTAINER="${ICAR_ROS_CONTAINER:-autodrive_ros2}"
ROS_DOMAIN_ID="${ROS_DOMAIN_ID:-30}"
REPO_DIR="${ICAR_REPO_DIR:-$HOME/icar-ros2-patrol}"
APP_WS="${ICAR_APP_WS:-/root/icar_app_ws}"
APP_MAX_LINEAR="${ICAR_APP_MAX_LINEAR:-0.45}"
APP_MAX_ANGULAR="${ICAR_APP_MAX_ANGULAR:-1.2}"
APP_COMMAND_TIMEOUT="${ICAR_APP_COMMAND_TIMEOUT:-1.0}"
APP_ENABLE_JOYSTICK="${ICAR_ENABLE_JOYSTICK:-0}"

docker inspect "$CONTAINER" >/dev/null

# The vendor Rosmaster app opens the camera and chassis outside ROS ownership.
pkill -f 'Rosmaster-App/rosmaster/app.py' 2>/dev/null || true
pkill -f '^python3 app.py$' 2>/dev/null || true
docker exec "$CONTAINER" pkill -f '^python3 /tmp/fast_bridge.py$' 2>/dev/null || true
docker exec "$CONTAINER" pkill -f '/app_control/lib/app_control/app_bridge_node' 2>/dev/null || true
docker exec "$CONTAINER" pkill -f '/app_control/lib/app_control/velocity_mux_node' 2>/dev/null || true
docker exec "$CONTAINER" pkill -f 'ros2 run app_control app_bridge_node' 2>/dev/null || true
docker exec "$CONTAINER" pkill -f 'ros2 run app_control velocity_mux_node' 2>/dev/null || true
# Remove legacy nodes previously launched in this container. Their old task
# manager and keyboard controller publish directly to /cmd_vel and bypass mux.
docker exec "$CONTAINER" pkill -f '/task_manager/lib/task_manager/task_manager_node' 2>/dev/null || true
docker exec "$CONTAINER" pkill -f 'ros2 run task_manager task_manager_node' 2>/dev/null || true
docker exec "$CONTAINER" pkill -f '/llm_gateway/lib/llm_gateway/llm_gateway_node' 2>/dev/null || true
docker exec "$CONTAINER" pkill -f 'ros2 run llm_gateway llm_gateway_node' 2>/dev/null || true
docker exec "$CONTAINER" pkill -f '/yahboomcar_ctrl/lib/yahboomcar_ctrl/yahboom_keyboard' 2>/dev/null || true
docker exec "$CONTAINER" pkill -f 'ros2 run yahboomcar_ctrl yahboom_keyboard' 2>/dev/null || true
run_ros_node() {
  local executable="$1"
  local logfile="$2"
  shift 2
  local ros_args="$*"
  docker exec "$CONTAINER" bash -lc \
    "source /opt/ros/foxy/setup.bash
     source $APP_WS/install/setup.bash
     export ROS_DOMAIN_ID=$ROS_DOMAIN_ID
     nohup ros2 run app_control $executable $ros_args </dev/null >$logfile 2>&1 &"
}

run_ros_node velocity_mux_node /tmp/velocity_mux.log
sleep 1
run_ros_node app_bridge_node /tmp/app_bridge.log \
  --ros-args \
  -p command_timeout_sec:="$APP_COMMAND_TIMEOUT" \
  -p max_linear:="$APP_MAX_LINEAR" \
  -p max_angular:="$APP_MAX_ANGULAR"

# The vendor launch starts this Python executable under the interpreter, so
# `pkill -x yahboom_joy_X3` never matches it.  Remove every existing instance
# before starting the remapped one below; otherwise one joystick writes
# directly to /cmd_vel and bypasses velocity_mux.
docker exec "$CONTAINER" pkill -f '/yahboomcar_ctrl/lib/yahboomcar_ctrl/yahboom_joy_X3' 2>/dev/null || true
docker exec "$CONTAINER" pkill -f 'ros2 run yahboomcar_ctrl yahboom_joy_X3' 2>/dev/null || true
if [ "$APP_ENABLE_JOYSTICK" = "1" ]; then
  docker exec "$CONTAINER" bash -lc \
    "source /opt/ros/foxy/setup.bash
     source /root/yahboomcar_ros2_ws/yahboomcar_ws/install/setup.bash
     export ROS_DOMAIN_ID=$ROS_DOMAIN_ID
     nohup ros2 run yahboomcar_ctrl yahboom_joy_X3 --ros-args \
       -r /cmd_vel:=/cmd_vel_joy </dev/null >/tmp/joy_ctrl.log 2>&1 &"
fi

WEB_USER="${ICAR_WEB_USER:-$(stat -c '%U' "$REPO_DIR")}"
WEB_SERVICE="${ICAR_WEB_SERVICE:-icar_web_gateway.service}"
USE_SYSTEMD_WEB=0
if [ "$(id -u)" -eq 0 ] && systemctl cat "$WEB_SERVICE" >/dev/null 2>&1; then
  USE_SYSTEMD_WEB=1
  systemctl stop "$WEB_SERVICE" 2>/dev/null || true
fi
pkill -f '^python3 app/web_gateway.py$' 2>/dev/null || true
rm -f /tmp/icar_web_gateway.log
if [ "$(id -u)" -eq 0 ] && [ "$WEB_USER" != root ]; then
  runuser -u "$WEB_USER" -- python3 -c 'import flask_sock' 2>/dev/null || \
    runuser -u "$WEB_USER" -- python3 -m pip install --user \
      --disable-pip-version-check -r "$REPO_DIR/app/requirements.txt"
  if [ "$USE_SYSTEMD_WEB" = "1" ]; then
    systemctl restart "$WEB_SERVICE"
  else
    runuser -u "$WEB_USER" -- bash -lc \
      "cd '$REPO_DIR'; nohup python3 app/web_gateway.py </dev/null >/tmp/icar_web_gateway.log 2>&1 &"
  fi
else
  python3 -c 'import flask_sock' 2>/dev/null || \
    python3 -m pip install --user --disable-pip-version-check \
      -r "$REPO_DIR/app/requirements.txt"
  if [ "$USE_SYSTEMD_WEB" = "1" ]; then
    systemctl restart "$WEB_SERVICE"
  else
    cd "$REPO_DIR"
    nohup python3 app/web_gateway.py </dev/null >/tmp/icar_web_gateway.log 2>&1 &
  fi
fi

sleep 3
curl --fail --silent --show-error --max-time 2 http://127.0.0.1:6500/health
echo
echo "Safe app stack started: http://0.0.0.0:6500"
