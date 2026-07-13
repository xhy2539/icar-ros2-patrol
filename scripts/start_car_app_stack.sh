#!/bin/bash
# Start the safe app stack on the Jetson host after autodrive_ros2 is running.

set -euo pipefail

CONTAINER="${ICAR_ROS_CONTAINER:-autodrive_ros2}"
ROS_DOMAIN_ID="${ROS_DOMAIN_ID:-30}"
REPO_DIR="${ICAR_REPO_DIR:-$HOME/icar-ros2-patrol}"
APP_WS="${ICAR_APP_WS:-/root/icar_app_ws}"

docker inspect "$CONTAINER" >/dev/null

# The vendor Rosmaster app opens the camera and chassis outside ROS ownership.
pkill -f 'Rosmaster-App/rosmaster/app.py' 2>/dev/null || true
pkill -f '^python3 app.py$' 2>/dev/null || true
docker exec "$CONTAINER" pkill -f '^python3 /tmp/fast_bridge.py$' 2>/dev/null || true
docker exec "$CONTAINER" pkill -f '/app_control/lib/app_control/app_bridge_node' 2>/dev/null || true
docker exec "$CONTAINER" pkill -f '/app_control/lib/app_control/velocity_mux_node' 2>/dev/null || true
docker exec "$CONTAINER" pkill -f 'ros2 run app_control app_bridge_node' 2>/dev/null || true
docker exec "$CONTAINER" pkill -f 'ros2 run app_control velocity_mux_node' 2>/dev/null || true
docker exec "$CONTAINER" pkill -f '/task_manager/lib/task_manager/task_manager_node' 2>/dev/null || true
docker exec "$CONTAINER" pkill -f '/llm_gateway/lib/llm_gateway/llm_gateway_node' 2>/dev/null || true
docker exec "$CONTAINER" pkill -f 'ros2 run task_manager task_manager_node' 2>/dev/null || true
docker exec "$CONTAINER" pkill -f 'ros2 run llm_gateway llm_gateway_node' 2>/dev/null || true

run_ros_node() {
  local package="$1"
  local executable="$2"
  local logfile="$3"
  shift 3
  local ros_args="$*"
  docker exec "$CONTAINER" bash -lc \
    "source /opt/ros/foxy/setup.bash
     source $APP_WS/install/setup.bash
     export ROS_DOMAIN_ID=$ROS_DOMAIN_ID
     export PYTHONPATH=$APP_WS/src/llm:\${PYTHONPATH:-}
     nohup ros2 run $package $executable $ros_args </dev/null >$logfile 2>&1 &"
}

run_ros_node app_control velocity_mux_node /tmp/velocity_mux.log
sleep 1
run_ros_node task_manager task_manager_node /tmp/task_manager.log
run_ros_node llm_gateway llm_gateway_node /tmp/llm_gateway.log \
  --ros-args -p tool_mode:=true -p provider:=auto
run_ros_node app_control app_bridge_node /tmp/app_bridge.log

docker exec "$CONTAINER" pkill -x yahboom_joy_X3 2>/dev/null || true
docker exec "$CONTAINER" bash -lc \
  "source /opt/ros/foxy/setup.bash
   source /root/yahboomcar_ros2_ws/yahboomcar_ws/install/setup.bash
   export ROS_DOMAIN_ID=$ROS_DOMAIN_ID
   nohup ros2 run yahboomcar_ctrl yahboom_joy_X3 --ros-args \
     -r /cmd_vel:=/cmd_vel_joy </dev/null >/tmp/joy_ctrl.log 2>&1 &"

pkill -f '^python3 app/web_gateway.py$' 2>/dev/null || true
cd "$REPO_DIR"
nohup python3 app/web_gateway.py </dev/null >/tmp/icar_web_gateway.log 2>&1 &

sleep 3
curl --fail --silent --show-error --max-time 2 http://127.0.0.1:6500/health
echo
echo "Safe app stack started: http://0.0.0.0:6500"
