#!/bin/bash
# Safe, idempotent car startup for the unified ROS-domain runtime.

set -euo pipefail

LOG="/home/jetson/icar_startup.log"
LOCK_FILE="/run/icar_startup.lock"
SCRIPT_DIR=$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd -P)
REPO=$(cd "$SCRIPT_DIR/.." && pwd -P)
DOMAIN=30
ENABLE_NAV2="${ICAR_ENABLE_NAV2:-1}"
NAV2_MAP="${ICAR_NAV2_MAP:-/root/yahboomcar_ros2_ws/yahboomcar_ws/install/yahboomcar_nav/share/yahboomcar_nav/maps/yahboomcar.yaml}"
NAV2_PARAMS="${ICAR_NAV2_PARAMS:-/root/yahboomcar_ros2_ws/yahboomcar_ws/src/yahboomcar_nav/params/dwa_nav_params.yaml}"
exec > >(tee -a "$LOG") 2>&1
exec 9>"$LOCK_FILE"
if ! flock -n 9; then
  echo "ERROR: another iCar startup is already running"
  exit 1
fi
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
# The vendor image's PID 1 does not reliably reap children left by an aborted
# launch.  A fresh container guarantees that an automatic service retry cannot
# inherit old EKF, lidar, TF or Nav2 processes.
docker restart autodrive_ros2 >/dev/null
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
# The vendor desktop app can leave several interactive docker exec sessions
# launching overlapping bringup, lidar, RViz and Nav2 stacks. Stop every launch
# owner here so this script becomes the single runtime owner.
docker exec autodrive_ros2 pkill -f '[y]ahboomcar_bringup_X3_launch.py' 2>/dev/null || true
docker exec autodrive_ros2 pkill -f '[l]aser_bringup_launch.py' 2>/dev/null || true
docker exec autodrive_ros2 pkill -f '[d]isplay_nav_launch.py' 2>/dev/null || true
docker exec autodrive_ros2 pkill -f '[n]avigation_dwa_launch.py' 2>/dev/null || true
docker exec autodrive_ros2 pkill -f '[n]avigation_mux.launch.py' 2>/dev/null || true
# ros2 launch can leave Nav2 children orphaned when a previous systemd attempt
# is terminated. Remove those direct /cmd_vel publishers before launching the
# remapped Nav2 stack again.
for nav_process in \
  '/nav2_map_server/map_server' \
  '/nav2_amcl/amcl' \
  '/nav2_controller/controller_server' \
  '/nav2_planner/planner_server' \
  '/nav2_recoveries/recoveries_server' \
  '/nav2_bt_navigator/bt_navigator' \
  '/nav2_waypoint_follower/waypoint_follower' \
  '/nav2_lifecycle_manager/lifecycle_manager' \
  '/rviz2/rviz2'; do
  docker exec autodrive_ros2 pkill -f "$nav_process" 2>/dev/null || true
done
docker exec autodrive_ros2 pkill -f \
  '[/]navigation/lib/navigation/obstacle_avoid_node' 2>/dev/null || true
sleep 3

# ── 彻底清理所有 iCar 进程（避免重启时僵尸堆积）──
echo "[4.5/14] Purging stale iCar processes"
for container in autodrive_ros2 icar_ros2; do
  docker exec "$container" bash -c '
    # 通用匹配：ros2 run 启动的 Python 节点
    for name in app_control cloud_bridge task_manager llm_gateway \
                navigation vision_patrol voice_control; do
      pkill -9 -f "$name" 2>/dev/null || true
    done
    # 驱动节点
    pkill -9 -f Mcnamu_driver 2>/dev/null || true
    pkill -9 -f yahboomcar_bringup 2>/dev/null || true
    pkill -9 -f yahboom_joy 2>/dev/null || true
  ' 2>/dev/null || true
done
sleep 3

# 验证清理效果
STALE_COUNT=0
for container in autodrive_ros2 icar_ros2; do
  cnt=$(docker exec "$container" bash -c \
    "ps -eo args= | grep -E 'app_control|cloud_bridge|task_manager|llm_gateway|navigation|vision_patrol|voice_control' | grep -v grep | wc -l" 2>/dev/null || echo 0)
  cnt=$(echo "$cnt" | tr -cd '0-9')
  STALE_COUNT=$((STALE_COUNT + ${cnt:-0}))
done
if [ "$STALE_COUNT" -gt 0 ]; then
  echo "WARNING: $STALE_COUNT iCar process(es) still alive after purge"
fi

echo "[5/14] Starting chassis bringup and lidar"
# Detached vendor nodes can survive after their launch owner is killed.  Always
# remove their direct executables before starting one controlled bringup; merely
# checking that one driver exists permits a second process to keep the serial
# port and publish duplicate /joint_states.
docker exec autodrive_ros2 pkill -f \
  '/yahboomcar_bringup/lib/yahboomcar_bringup/Mcnamu_driver_X3' 2>/dev/null || true
docker exec autodrive_ros2 pkill -f \
  '/joint_state_publisher/joint_state_publisher' 2>/dev/null || true
sleep 3
# n1 is the vendor-provided interactive shortcut.  It supplies the robot and
# lidar arguments that the raw launch files require, and it is the sole owner
# of the chassis, EKF, lidar and base_link -> laser TF chain.
(
  exec 9>&-
  nohup docker exec autodrive_ros2 bash -ic 'n1' \
    </dev/null >/tmp/n1_laser_bringup.log 2>&1
) &
sleep 10

echo "[6/14] Syncing and building app_control"
if [ -s "$REPO/.icar_deploy_revision" ]; then
  SOURCE_REVISION=$(tr -d '[:space:]' < "$REPO/.icar_deploy_revision")
elif git -c safe.directory="$REPO" -C "$REPO" rev-parse --is-inside-work-tree >/dev/null 2>&1; then
  SOURCE_REVISION=$(git -c safe.directory="$REPO" -C "$REPO" rev-parse HEAD)
else
  # Release directories intentionally omit .git.  They remain a valid source
  # for the container workspaces, so use a stable marker instead of failing.
  SOURCE_REVISION="release-current"
fi
APP_BUILD_REQUIRED=0
if [ "$SOURCE_REVISION" != "$(docker exec autodrive_ros2 cat /root/icar_app_ws/.icar_source_revision 2>/dev/null || true)" ] || \
   ! docker exec autodrive_ros2 test -x /root/icar_app_ws/install/app_control/lib/app_control/app_bridge_node; then
  APP_BUILD_REQUIRED=1
fi
# Always restore the container sources from the selected Git checkout. This is
# cheap and prevents an old manual workspace copy from surviving merely because
# its revision marker was updated.
tar --exclude='._*' -C "$REPO" -cf - app_control icar_interfaces | \
  docker exec -i autodrive_ros2 bash -c \
    'mkdir -p /root/icar_app_ws/src; cd /root/icar_app_ws/src; rm -rf app_control icar_interfaces; tar xf -'
docker exec autodrive_ros2 bash -lc \
  'python3 -m py_compile /root/icar_app_ws/src/app_control/app_control/*.py'
if [ "$APP_BUILD_REQUIRED" -eq 1 ]; then
  docker exec autodrive_ros2 bash -lc \
    'source /opt/ros/foxy/setup.bash; source /root/yahboomcar_ros2_ws/yahboomcar_ws/install/setup.bash; cd /root/icar_app_ws; colcon build --packages-select icar_interfaces app_control --symlink-install'
  docker exec autodrive_ros2 sh -c "printf '%s\\n' '$SOURCE_REVISION' > /root/icar_app_ws/.icar_source_revision"
fi

echo "[7/14] Syncing and building task_manager + LLM + navigation + cloud + vision"
ICAR_WS="/root/icar_ros2_ws/icar_ws"
docker exec icar_ros2 bash -lc \
  "python3 -c 'import paho.mqtt.client' 2>/dev/null || python3 -m pip install 'paho-mqtt>=1.5,<3'"
ICAR_BUILD_REQUIRED=0
if [ "$SOURCE_REVISION" != "$(docker exec icar_ros2 cat $ICAR_WS/.icar_source_revision 2>/dev/null || true)" ]; then
  ICAR_BUILD_REQUIRED=1
fi
tar --exclude='._*' -C "$REPO" -cf - task_manager llm navigation cloud_bridge vision voice icar_interfaces audio | \
  docker exec -i icar_ros2 bash -c \
    "mkdir -p $ICAR_WS/src; cd $ICAR_WS/src; rm -rf task_manager llm navigation cloud_bridge vision voice icar_interfaces audio; tar xf -"
# Model weights are deliberately kept outside the ROS package source tree.
# Copy the configured water detector alongside the generic YOLO model so a
# restart cannot silently disable puddle detection.
if [ -f "$REPO/models/water_seg_v1.pt" ]; then
  docker exec icar_ros2 mkdir -p "$ICAR_WS/models"
  docker cp "$REPO/models/water_seg_v1.pt" \
    "icar_ros2:$ICAR_WS/models/water_seg_v1.pt"
fi
if [ "$ICAR_BUILD_REQUIRED" -eq 1 ]; then
  docker exec icar_ros2 bash -lc \
    "source /opt/ros/foxy/setup.bash; cd $ICAR_WS; colcon build --symlink-install --packages-select icar_interfaces task_manager llm_gateway navigation cloud_bridge vision_patrol voice_control"
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
  # n1 owns the base_link -> laser transform; do not publish a second static TF here.
  # Ensure map origin covers all checkpoints (persistent fix)
  docker exec autodrive_ros2 sed -i 's/origin: \[-21\.2, -45\.2, 0\]/origin: [-10.0, -10.0, 0]/' "$NAV2_MAP" 2>/dev/null || true
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
export DOUBAO_APP_ID="${DOUBAO_APP_ID:-}"
export DOUBAO_ACCESS_KEY="${DOUBAO_ACCESS_KEY:-}"
# The startup watchdog runs this script as root, while deployment credentials
# are deliberately stored under the jetson account.  Load that trusted local
# environment file so a watchdog restart does not silently skip voice nodes.
if { [ -z "$DOUBAO_APP_ID" ] || [ -z "$DOUBAO_ACCESS_KEY" ]; } && [ -f /home/jetson/.env ]; then
  set -a
  # shellcheck disable=SC1091
  . /home/jetson/.env
  set +a
fi
ICAR_DOCKER_CMD="docker exec icar_ros2 bash -lc 'source /opt/ros/foxy/setup.bash; source $ICAR_WS/install/setup.bash; export ROS_DOMAIN_ID=30"
if [ -n "$DEEPSEEK_API_KEY" ]; then
  ICAR_DOCKER_CMD="$ICAR_DOCKER_CMD; export DEEPSEEK_API_KEY=$DEEPSEEK_API_KEY"
fi
if [ -n "$DOUBAO_APP_ID" ]; then
  ICAR_DOCKER_CMD="$ICAR_DOCKER_CMD; export DOUBAO_APP_ID=$DOUBAO_APP_ID"
fi
if [ -n "$DOUBAO_ACCESS_KEY" ]; then
  ICAR_DOCKER_CMD="$ICAR_DOCKER_CMD; export DOUBAO_ACCESS_KEY=$DOUBAO_ACCESS_KEY"
fi
# Restart these nodes from the freshly built install tree. Merely checking for
# an old process leaves the previous Python code loaded after a deployment.
# First kill any lingering docker exec sessions on the host that own these nodes.
# Then use SIGKILL (-9) inside the container so even hung processes are terminated
# immediately, and kill both the ros2 run wrapper and the actual binary to prevent
# double-counting in the verification step.  Retry up to 3× and confirm the
# process is gone.
pkill -f '[d]ocker exec icar_ros2 .*llm_gateway' 2>/dev/null || true
pkill -f '[d]ocker exec icar_ros2 .*cloud_bridge' 2>/dev/null || true
_icar_safe_kill() {
  local container="$1" pattern="$2"
  for _ in $(seq 1 3); do
    docker exec "$container" pkill -9 -f "$pattern" 2>/dev/null || true
    sleep 0.5
  done
  local remaining
  remaining=$(docker exec "$container" bash -lc \
    "ps -eo args= | grep -v grep | grep -v 'ros2 run' | grep -c '$pattern'" 2>/dev/null || echo 0)
  remaining=$(echo "$remaining" | tr -cd '0-9')
  if [ "${remaining:-0}" -gt 0 ]; then
    echo "WARNING: $remaining process(es) matching '$pattern' still alive after kill"
  fi
}
_icar_safe_kill icar_ros2 '/task_manager/lib/task_manager/task_manager_node'
_icar_safe_kill icar_ros2 '/task_manager/lib/task_manager/obstacle_alarm_node'
_icar_safe_kill icar_ros2 '/navigation/lib/navigation/obstacle_avoid_node'
_icar_safe_kill icar_ros2 '/navigation/lib/navigation/nav2_bridge_node'
_icar_safe_kill icar_ros2 'llm_gateway_node'
_icar_safe_kill icar_ros2 'cloud_bridge_node'
_icar_safe_kill icar_ros2 '/voice_control/lib/voice_control/web_voice_gateway_node'
_icar_safe_kill icar_ros2 '/voice_control/lib/voice_control/doubao_voice_node'
_icar_safe_kill icar_ros2 '/voice_control/lib/voice_control/voice_command_router_node'
sleep 1
eval "$ICAR_DOCKER_CMD; nohup ros2 run task_manager task_manager_node </dev/null >/tmp/task_manager.log 2>&1 &'"
sleep 2
eval "$ICAR_DOCKER_CMD; nohup ros2 run task_manager obstacle_alarm_node </dev/null >/tmp/obstacle_alarm.log 2>&1 &'"
sleep 1
eval "$ICAR_DOCKER_CMD; nohup ros2 run navigation obstacle_avoid_node --mode real </dev/null >/tmp/obstacle_avoid.log 2>&1 &'"
sleep 1
if [ "$ENABLE_NAV2" = "1" ]; then
  # Nav2 启用时，navigation_mux.launch.py 中的 nav2_goal_adapter_node 是唯一
  # /goal_pose -> /navigate_to_pose -> /nav_status 桥接。
  echo "Nav2 feedback bridge is nav2_goal_adapter from navigation_mux"
else
  # Nav2 未启用时，nav2_bridge_node mock 模式是唯一的 /goal_pose → /nav_status 桥接。
  # 8 秒模拟导航后自动返回 ARRIVED，保证巡检状态机能够正常流转。
  eval "$ICAR_DOCKER_CMD; nohup ros2 run navigation nav2_bridge_node --mode mock </dev/null >/tmp/nav2_bridge.log 2>&1 &'"
fi
sleep 1
eval "$ICAR_DOCKER_CMD; export ICAR_AUDIO_DIR=/root/icar_ros2_ws/icar_ws/src/audio; nohup ros2 run llm_gateway llm_gateway_node --ros-args -p tool_mode:=true </dev/null >/tmp/llm_gateway.log 2>&1 &'"
sleep 2
if [ -n "$DOUBAO_APP_ID" ] && [ -n "$DOUBAO_ACCESS_KEY" ]; then
  eval "$ICAR_DOCKER_CMD; nohup ros2 run voice_control web_voice_gateway_node </dev/null >/tmp/web_voice_gateway.log 2>&1 &'"
  sleep 1
  eval "$ICAR_DOCKER_CMD; nohup ros2 run voice_control doubao_voice_node </dev/null >/tmp/doubao_voice.log 2>&1 &'"
  sleep 1
  eval "$ICAR_DOCKER_CMD; nohup ros2 run voice_control voice_command_router_node </dev/null >/tmp/voice_command_router.log 2>&1 &'"
else
  echo "豆包语音未启动：请设置 DOUBAO_APP_ID 和 DOUBAO_ACCESS_KEY"
fi

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
if ! MUX_INFO=$(ros_node_info /velocity_mux); then
  echo "velocity_mux was not discoverable; restarting the safe app stack once"
  ICAR_ROS_CONTAINER=autodrive_ros2 ROS_DOMAIN_ID="$DOMAIN" \
    ICAR_REPO_DIR="$REPO" \
    "$REPO/scripts/start_car_app_stack.sh"
  MUX_INFO=$(ros_node_info /velocity_mux)
fi
DRIVER_INFO=$(ros_node_info /driver_node)
echo "$MUX_INFO"
echo "$DRIVER_INFO"
echo "$MUX_INFO" | grep -q '^    /cmd_vel: geometry_msgs/msg/Twist$'
echo "$DRIVER_INFO" | grep -q '^    /cmd_vel: geometry_msgs/msg/Twist$'

# Cross-container node discovery can be incomplete while Nav2 is loading the
# Jetson. Verify the live executable count directly, then use one refreshed ROS
# daemon to prove that /cmd_vel still has only the safety mux publisher.
require_process_count() {
  local container="$1"
  local pattern="$2"
  local label="$3"
  local expected="$4"
  local count
  # The vendor container's PID 1 does not always reap a just-terminated ROS
  # child.  `pgrep` counts those zombies forever, although they cannot publish
  # or hold a device.  Count only runnable/sleeping processes instead.
  count=$(docker exec "$container" bash -lc \
    "ps -eo stat=,comm=,args= | awk -v p='$pattern' '\$1 !~ /^Z/ && \$2 !~ /^(python3|python|ros2|bash|sh|awk)$/ && index(\$0, p) { count++ } END { print count+0 }'" \
    2>/dev/null || true)
  count=$(printf '%s' "$count" | tr -cd '0-9')
  count=${count:-0}
  if [ "$count" -ne "$expected" ]; then
    echo "ERROR: expected $expected $label process(es), found $count"
    return 1
  fi
}
require_single_process() {
  require_process_count "$1" "$2" "$3" 1
}
require_single_process autodrive_ros2 '/root/icar_app_ws/install/app_control/lib/app_control/velocity_mux_node' velocity_mux
require_single_process autodrive_ros2 '/root/icar_app_ws/install/app_control/lib/app_control/app_bridge_node' app_bridge
require_single_process autodrive_ros2 '/yahboomcar_bringup/lib/yahboomcar_bringup/Mcnamu_driver_X3' driver_node
if [ "$ENABLE_NAV2" = "1" ]; then
  require_single_process autodrive_ros2 '/nav2_map_server/map_server' map_server
  require_single_process autodrive_ros2 '/nav2_amcl/amcl' amcl
  require_single_process autodrive_ros2 '/nav2_controller/controller_server' controller_server
  require_single_process autodrive_ros2 '/nav2_planner/planner_server' planner_server
  require_process_count autodrive_ros2 '/nav2_lifecycle_manager/lifecycle_manager' lifecycle_manager 2
  require_single_process autodrive_ros2 '/root/icar_app_ws/install/app_control/lib/app_control/nav2_goal_adapter_node' nav2_goal_adapter
fi
require_single_process icar_ros2 '/install/task_manager/lib/task_manager/task_manager_node' task_manager_node
require_single_process icar_ros2 '/install/task_manager/lib/task_manager/obstacle_alarm_node' obstacle_alarm_node
if [ "$ENABLE_NAV2" != "1" ]; then
  require_single_process icar_ros2 '/install/navigation/lib/navigation/nav2_bridge_node' nav2_bridge_node || \
    echo "WARNING: nav2_bridge_node is unavailable; patrol goal feedback may be missing"
fi
require_single_process icar_ros2 '/install/llm_gateway/lib/llm_gateway/llm_gateway_node' llm_gateway_node
# Camera/vision is deliberately independent from localization and patrol.
# Keep startup moving when the camera is unavailable; the Web health endpoint
# already reports visual readiness separately.
require_single_process icar_ros2 '/install/vision_patrol/lib/vision_patrol/vision_node' vision_node || \
  echo "WARNING: vision_node is unavailable; navigation will continue"
require_single_process icar_ros2 '/install/vision_patrol/lib/vision_patrol/mjpeg_server' vision_mjpeg_server || \
  echo "WARNING: vision_mjpeg_server is unavailable; navigation will continue"
require_single_process icar_ros2 '/install/cloud_bridge/lib/cloud_bridge/cloud_bridge_node' cloud_bridge_node

CMD_VEL_INFO=""
for attempt in $(seq 1 3); do
  docker exec -e ROS_DOMAIN_ID=30 autodrive_ros2 bash -lc \
    'source /opt/ros/foxy/setup.bash; ros2 daemon stop >/dev/null 2>&1 || true; ros2 daemon start >/dev/null'
  sleep 8
  CMD_VEL_INFO=$(docker exec -e ROS_DOMAIN_ID=30 autodrive_ros2 bash -lc \
    'source /opt/ros/foxy/setup.bash; ros2 topic info /cmd_vel -v' 2>/dev/null || true)
  if echo "$CMD_VEL_INFO" | grep -q '^Publisher count: 1$' && \
     echo "$CMD_VEL_INFO" | grep -q '^Subscription count: 1$' && \
     echo "$CMD_VEL_INFO" | grep -q '^Node name: velocity_mux$' && \
     echo "$CMD_VEL_INFO" | grep -q '^Node name: driver_node$'; then
    break
  fi
  if [ "$attempt" -lt 3 ]; then
    echo "Waiting for the unique /cmd_vel graph ($attempt/3)"
  fi
done
echo "$CMD_VEL_INFO"
echo "$CMD_VEL_INFO" | grep -q '^Publisher count: 1$'
echo "$CMD_VEL_INFO" | grep -q '^Subscription count: 1$'
echo "$CMD_VEL_INFO" | grep -q '^Node name: velocity_mux$'
echo "$CMD_VEL_INFO" | grep -q '^Node name: driver_node$'

NODE_LIST=$(docker exec -e ROS_DOMAIN_ID=30 autodrive_ros2 bash -lc \
  'source /opt/ros/foxy/setup.bash; ros2 node list' 2>/dev/null || true)
echo "$NODE_LIST"

echo "[12/14] Verifying web gateway"
curl --fail --silent --show-error --max-time 5 http://127.0.0.1:6500/health
echo
echo "=== iCar safe startup complete ==="
