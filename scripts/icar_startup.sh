#!/bin/bash
# Safe, idempotent car startup for the unified ROS-domain runtime.

set -euo pipefail

LOG="/home/jetson/icar_startup.log"
SCRIPT_DIR=$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd -P)
REPO=$(cd "$SCRIPT_DIR/.." && pwd -P)
DOMAIN=30
ENABLE_NAV2="${ICAR_ENABLE_NAV2:-0}"
NAV2_MAP="${ICAR_NAV2_MAP:-/root/yahboomcar_ros2_ws/yahboomcar_ws/src/yahboomcar_nav/maps/yahboomcar.yaml}"
NAV2_PARAMS="${ICAR_NAV2_PARAMS:-/root/yahboomcar_ros2_ws/yahboomcar_ws/src/yahboomcar_nav/params/dwa_nav_params.yaml}"
exec > >(tee -a "$LOG") 2>&1
echo "=== iCar safe startup $(date) ==="

echo "[0/14] Setting USB speaker as default and volume"
cat > /etc/asound.conf << 'ALSAEOF'
pcm.!default { type plug; slave { pcm "hw:0,0"; channels 2; rate 48000; } }
ctl.!default { type hw; card 0; }
ALSAEOF
amixer -c 0 sset PCM 80% 2>/dev/null || true

echo "[1/14] Waiting for chassis serial"
for _ in $(seq 1 30); do
  [ -e /dev/myserial ] && break
  sleep 1
done
[ -e /dev/myserial ] || { echo "ERROR: /dev/myserial missing"; exit 1; }

echo "[2/14] Starting containers"
docker start autodrive_ros2 >/dev/null
docker start icar_ros2 >/dev/null
docker update --restart unless-stopped autodrive_ros2 icar_ros2 >/dev/null
sleep 4

echo "[3/14] Installing shared ROS domain environment"
for container in autodrive_ros2 icar_ros2; do
  docker exec "$container" sh -c \
    'printf "%s\n" "export ROS_DOMAIN_ID=30" > /etc/profile.d/icar_ros_domain.sh'
  docker exec "$container" pkill -f '/opt/ros/foxy/bin/_ros2_daemon' 2>/dev/null || true
done
docker exec autodrive_ros2 bash -lc \
  'source /opt/ros/foxy/setup.bash; export ROS_DOMAIN_ID=30; ros2 daemon start >/dev/null'

echo "[4/14] Removing legacy control and camera processes"
pkill -f 'Rosmaster-App/rosmaster/app.py' 2>/dev/null || true
pkill -f '^python3 app.py$' 2>/dev/null || true
docker exec autodrive_ros2 pkill -f '^python3 /tmp/fast_bridge.py$' 2>/dev/null || true
# The vendor DWA launch publishes directly to /cmd_vel and bypasses the
# application mux. Navigation is started separately only after localization.
docker exec autodrive_ros2 pkill -f '[n]avigation_dwa_launch.py' 2>/dev/null || true
docker exec autodrive_ros2 pkill -f \
  '[/]navigation/lib/navigation/obstacle_avoid_node' 2>/dev/null || true

echo "[5/14] Starting chassis bringup and lidar"
# A container restart can restore a launch process a few seconds after Docker is
# reported as running. Wait before deciding that standalone bringup is needed;
# otherwise both launch files can race and open the chassis serial twice.
for _ in $(seq 1 10); do
  docker exec autodrive_ros2 pgrep -f 'Mcnamu_driver_X3 --ros-args' >/dev/null && break
  sleep 1
done
if ! docker exec autodrive_ros2 pgrep -f 'Mcnamu_driver_X3 --ros-args' >/dev/null; then
  docker exec autodrive_ros2 bash -lc \
    'source /opt/ros/foxy/setup.bash
     source /root/yahboomcar_ros2_ws/software/library_ws/install/setup.bash
     source /root/yahboomcar_ros2_ws/yahboomcar_ws/install/setup.bash
     export ROS_DOMAIN_ID=30
     nohup ros2 launch yahboomcar_bringup yahboomcar_bringup_X3_launch.py \
       </dev/null >/tmp/yahboomcar_bringup.log 2>&1 &'
  sleep 10
fi
if ! docker exec autodrive_ros2 pgrep -f \
  '/sllidar_ros2/lib/sllidar_ros2/sllidar_node --ros-args' >/dev/null; then
  docker exec autodrive_ros2 bash -lc \
    'source /opt/ros/foxy/setup.bash
     source /root/yahboomcar_ros2_ws/software/library_ws/install/setup.bash
     export ROS_DOMAIN_ID=30
     nohup ros2 launch sllidar_ros2 sllidar_launch.py \
       </dev/null >/tmp/sllidar.log 2>&1 &'
  sleep 3
fi

echo "[6/14] Syncing and building app_control"
if [ -s "$REPO/.icar_deploy_revision" ]; then
  SOURCE_REVISION=$(tr -d '[:space:]' < "$REPO/.icar_deploy_revision")
else
  SOURCE_REVISION=$(git -c safe.directory="$REPO" -C "$REPO" rev-parse HEAD)
fi
if [ "$SOURCE_REVISION" != "$(docker exec autodrive_ros2 cat /root/icar_app_ws/.icar_source_revision 2>/dev/null || true)" ] || \
   ! docker exec autodrive_ros2 test -x /root/icar_app_ws/install/app_control/lib/app_control/app_bridge_node; then
  tar --exclude='._*' -C "$REPO" -cf - app_control icar_interfaces | \
    docker exec -i autodrive_ros2 bash -c \
      'mkdir -p /root/icar_app_ws/src; cd /root/icar_app_ws/src; rm -rf app_control icar_interfaces; tar xf -'
  docker exec autodrive_ros2 bash -lc \
    'source /opt/ros/foxy/setup.bash; source /root/yahboomcar_ros2_ws/yahboomcar_ws/install/setup.bash; cd /root/icar_app_ws; colcon build --packages-select icar_interfaces app_control --symlink-install'
  docker exec autodrive_ros2 sh -c "printf '%s\\n' '$SOURCE_REVISION' > /root/icar_app_ws/.icar_source_revision"
fi

echo "[7/14] Syncing and building task_manager + LLM + navigation + cloud + vision"
ICAR_WS="/root/icar_ros2_ws/icar_ws"
docker exec icar_ros2 bash -lc \
  "python3 -c 'import paho.mqtt.client' 2>/dev/null || python3 -m pip install 'paho-mqtt>=1.5,<3'"
if [ "$SOURCE_REVISION" != "$(docker exec icar_ros2 cat $ICAR_WS/.icar_source_revision 2>/dev/null || true)" ]; then
  tar --exclude='._*' -C "$REPO" -cf - task_manager llm navigation cloud_bridge vision icar_interfaces audio | \
    docker exec -i icar_ros2 bash -c \
      "mkdir -p $ICAR_WS/src; cd $ICAR_WS/src; rm -rf task_manager llm navigation cloud_bridge vision icar_interfaces audio; tar xf -"
  docker exec icar_ros2 bash -lc \
    "source /opt/ros/foxy/setup.bash; cd $ICAR_WS; colcon build --symlink-install --packages-select icar_interfaces task_manager llm_gateway navigation cloud_bridge vision_patrol"
  docker exec icar_ros2 sh -c "printf '%s\\n' '$SOURCE_REVISION' > $ICAR_WS/.icar_source_revision"
fi

echo "[8/14] Starting camera and vision stack"
ICAR_ROS_DOMAIN_ID="$DOMAIN" "$REPO/scripts/start_car_vision_stack.sh"

echo "[9/14] Starting safe App/video/control stack"
ICAR_ROS_CONTAINER=autodrive_ros2 ROS_DOMAIN_ID="$DOMAIN" \
  ICAR_REPO_DIR="$REPO" \
  "$REPO/scripts/start_car_app_stack.sh"

if [ "$ENABLE_NAV2" = "1" ]; then
  echo "[9.5/14] Starting Nav2 through /cmd_vel_nav safety mux"
  docker exec autodrive_ros2 pkill -f '[n]avigation_dwa_launch.py' 2>/dev/null || true
  docker exec autodrive_ros2 pkill -f '[n]avigation_mux.launch.py' 2>/dev/null || true
  docker exec autodrive_ros2 bash -lc \
    "source /opt/ros/foxy/setup.bash
     source /root/yahboomcar_ros2_ws/software/library_ws/install/setup.bash
     source /root/yahboomcar_ros2_ws/yahboomcar_ws/install/setup.bash
     source /root/icar_app_ws/install/setup.bash
     export ROS_DOMAIN_ID=$DOMAIN
     nohup ros2 launch app_control navigation_mux.launch.py \
       map:='$NAV2_MAP' params_file:='$NAV2_PARAMS' \
       </dev/null >/tmp/navigation_mux.log 2>&1 &"
else
  echo "[9.5/14] Nav2 disabled (set ICAR_ENABLE_NAV2=1 after map/localization are ready)"
fi

echo "[10/14] Starting task_manager + LLM gateway + obstacle_avoid + alarm + cloud_bridge"
export DEEPSEEK_API_KEY="${DEEPSEEK_API_KEY:-}"
ICAR_DOCKER_CMD="docker exec icar_ros2 bash -lc 'source /opt/ros/foxy/setup.bash; source $ICAR_WS/install/setup.bash; export ROS_DOMAIN_ID=30"
if [ -n "$DEEPSEEK_API_KEY" ]; then
  ICAR_DOCKER_CMD="$ICAR_DOCKER_CMD; export DEEPSEEK_API_KEY=$DEEPSEEK_API_KEY"
fi
# Restart these nodes from the freshly built install tree. Merely checking for
# an old process leaves the previous Python code loaded after a deployment.
docker exec icar_ros2 pkill -f '/task_manager/lib/task_manager/task_manager_node' 2>/dev/null || true
docker exec icar_ros2 pkill -f '/task_manager/lib/task_manager/obstacle_alarm_node' 2>/dev/null || true
docker exec icar_ros2 pkill -f '/navigation/lib/navigation/obstacle_avoid_node' 2>/dev/null || true
docker exec icar_ros2 pkill -f '/llm_gateway/lib/llm_gateway/llm_gateway_node' 2>/dev/null || true
docker exec icar_ros2 pkill -f '/cloud_bridge/lib/cloud_bridge/cloud_bridge_node' 2>/dev/null || true
sleep 1
eval "$ICAR_DOCKER_CMD; nohup ros2 run task_manager task_manager_node </dev/null >/tmp/task_manager.log 2>&1 &'"
sleep 2
eval "$ICAR_DOCKER_CMD; nohup ros2 run task_manager obstacle_alarm_node </dev/null >/tmp/obstacle_alarm.log 2>&1 &'"
sleep 1
eval "$ICAR_DOCKER_CMD; nohup ros2 run navigation obstacle_avoid_node --mode real </dev/null >/tmp/obstacle_avoid.log 2>&1 &'"
sleep 1
eval "$ICAR_DOCKER_CMD; export ICAR_AUDIO_DIR=/root/icar_ros2_ws/icar_ws/src/audio; nohup ros2 run llm_gateway llm_gateway_node --ros-args -p tool_mode:=true </dev/null >/tmp/llm_gateway.log 2>&1 &'"
sleep 2

# Forward only explicitly supplied cloud settings. Otherwise cloud_bridge uses
# its own defaults or ROS parameters. Array arguments avoid shell re-parsing.
CLOUD_ENV_ARGS=()
for variable in ICAR_MQTT_HOST ICAR_MQTT_PORT ICAR_MQTT_USER ICAR_MQTT_PASS \
  ICAR_MQTT_TLS ICAR_MQTT_CA_CERT ICAR_MQTT_TOPIC_PREFIX ICAR_DEVICE_ID; do
  if [ -n "${!variable:-}" ]; then
    CLOUD_ENV_ARGS+=("-e" "$variable=${!variable}")
  fi
done
docker exec "${CLOUD_ENV_ARGS[@]}" icar_ros2 bash -lc \
  "source /opt/ros/foxy/setup.bash
   source $ICAR_WS/install/setup.bash
   export ROS_DOMAIN_ID=30
   nohup ros2 run cloud_bridge cloud_bridge_node </dev/null >/tmp/cloud_bridge.log 2>&1 &"
sleep 2

echo "[11/14] Verifying ROS graph"
# Foxy daemon can retain a partial cross-container graph. Query the two
# safety-critical nodes without the daemon and verify the endpoint direction.
# Discovery on the Jetson can take several seconds immediately after a restart,
# so retry instead of turning a healthy graph into a service restart loop.
ros_node_info() {
  local node="$1"
  local output=""
  for _ in $(seq 1 3); do
    if output=$(docker exec -e ROS_DOMAIN_ID=30 autodrive_ros2 bash -lc \
      "source /opt/ros/foxy/setup.bash; ros2 node info --no-daemon --spin-time 10 '$node'" 2>/dev/null); then
      printf '%s\n' "$output"
      return 0
    fi
    sleep 2
  done
  return 1
}
MUX_INFO=$(ros_node_info /velocity_mux)
DRIVER_INFO=$(ros_node_info /driver_node)
echo "$MUX_INFO"
echo "$DRIVER_INFO"
echo "$MUX_INFO" | grep -q '^    /cmd_vel: geometry_msgs/msg/Twist$'
echo "$DRIVER_INFO" | grep -q '^    /cmd_vel: geometry_msgs/msg/Twist$'

NODE_LIST=$(docker exec -e ROS_DOMAIN_ID=30 autodrive_ros2 bash -lc \
  'source /opt/ros/foxy/setup.bash; ros2 node list --no-daemon --spin-time 10')
echo "$NODE_LIST"
[ "$(echo "$NODE_LIST" | grep -c '^/task_manager_node$')" -eq 1 ]
[ "$(echo "$NODE_LIST" | grep -c '^/obstacle_alarm_node$')" -eq 1 ]
[ "$(echo "$NODE_LIST" | grep -c '^/llm_gateway_node$')" -eq 1 ]
[ "$(echo "$NODE_LIST" | grep -c '^/vision_node$')" -eq 1 ]
[ "$(echo "$NODE_LIST" | grep -c '^/vision_mjpeg_server$')" -eq 1 ]
[ "$(echo "$NODE_LIST" | grep -c '^/cloud_bridge_node$')" -eq 1 ]

echo "[12/14] Verifying web gateway"
curl --fail --silent --show-error --max-time 5 http://127.0.0.1:6500/health
echo
echo "=== iCar safe startup complete ==="
