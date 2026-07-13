#!/bin/bash
# Safe, idempotent car startup for the unified ROS-domain runtime.

set -euo pipefail

LOG="/home/jetson/icar_startup.log"
REPO="/home/jetson/icar-ros2-patrol"
DOMAIN=30
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

echo "[5/14] Starting chassis bringup and lidar"
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
if ! docker exec autodrive_ros2 pgrep -x sllidar_node >/dev/null; then
  docker exec autodrive_ros2 bash -lc \
    'source /opt/ros/foxy/setup.bash
     source /root/yahboomcar_ros2_ws/software/library_ws/install/setup.bash
     export ROS_DOMAIN_ID=30
     nohup ros2 launch sllidar_ros2 sllidar_launch.py \
       </dev/null >/tmp/sllidar.log 2>&1 &'
  sleep 3
fi

echo "[6/14] Syncing and building app_control"
SOURCE_REVISION=$(git -C "$REPO" rev-parse HEAD)
if [ "$SOURCE_REVISION" != "$(docker exec autodrive_ros2 cat /root/icar_app_ws/.icar_source_revision 2>/dev/null || true)" ] || \
   ! docker exec autodrive_ros2 test -x /root/icar_app_ws/install/app_control/lib/app_control/app_bridge_node; then
  tar --exclude='._*' -C "$REPO" -cf - app_control icar_interfaces | \
    docker exec -i autodrive_ros2 bash -c \
      'mkdir -p /root/icar_app_ws/src; cd /root/icar_app_ws/src; rm -rf app_control icar_interfaces; tar xf -'
  docker exec autodrive_ros2 bash -lc \
    'source /opt/ros/foxy/setup.bash; source /root/yahboomcar_ros2_ws/yahboomcar_ws/install/setup.bash; cd /root/icar_app_ws; colcon build --packages-select icar_interfaces app_control --symlink-install'
  docker exec autodrive_ros2 sh -c "printf '%s\\n' '$SOURCE_REVISION' > /root/icar_app_ws/.icar_source_revision"
fi

echo "[7/14] Syncing and building task_manager + LLM + navigation"
ICAR_WS="/root/icar_ros2_ws/icar_ws"
if [ "$SOURCE_REVISION" != "$(docker exec icar_ros2 cat $ICAR_WS/.icar_source_revision 2>/dev/null || true)" ]; then
  tar --exclude='._*' -C "$REPO" -cf - task_manager llm navigation icar_interfaces audio | \
    docker exec -i icar_ros2 bash -c \
      "mkdir -p $ICAR_WS/src; cd $ICAR_WS/src; rm -rf task_manager llm navigation icar_interfaces audio; tar xf -"
  docker exec icar_ros2 bash -lc \
    "source /opt/ros/foxy/setup.bash; cd $ICAR_WS; colcon build --symlink-install --packages-select icar_interfaces task_manager llm_gateway navigation"
  docker exec icar_ros2 sh -c "printf '%s\\n' '$SOURCE_REVISION' > $ICAR_WS/.icar_source_revision"
fi

echo "[8/14] Starting camera and vision stack"
ICAR_ROS_DOMAIN_ID="$DOMAIN" "$REPO/scripts/start_car_vision_stack.sh"

echo "[9/14] Starting safe App/video/control stack"
ICAR_ROS_CONTAINER=autodrive_ros2 ROS_DOMAIN_ID="$DOMAIN" \
  "$REPO/scripts/start_car_app_stack.sh"

echo "[10/14] Starting task_manager + LLM gateway + obstacle_avoid"
export DEEPSEEK_API_KEY="${DEEPSEEK_API_KEY:-}"
ICAR_DOCKER_CMD="docker exec icar_ros2 bash -lc 'source /opt/ros/foxy/setup.bash; source $ICAR_WS/install/setup.bash; export ROS_DOMAIN_ID=30"
if [ -n "$DEEPSEEK_API_KEY" ]; then
  ICAR_DOCKER_CMD="$ICAR_DOCKER_CMD; export DEEPSEEK_API_KEY=$DEEPSEEK_API_KEY"
fi
# task_manager
if ! docker exec icar_ros2 pgrep -f task_manager_node >/dev/null 2>&1; then
  eval "$ICAR_DOCKER_CMD; nohup ros2 run task_manager task_manager_node </dev/null >/tmp/task_manager.log 2>&1 &'"
  sleep 2
fi
# obstacle_avoid (real radar, not mock)
if ! docker exec icar_ros2 pgrep -f obstacle_avoid_node >/dev/null 2>&1; then
  eval "$ICAR_DOCKER_CMD; nohup ros2 run navigation obstacle_avoid_node --mode real </dev/null >/tmp/obstacle_avoid.log 2>&1 &'"
  sleep 1
fi
# llm_gateway (with tool_mode)
if ! docker exec icar_ros2 pgrep -f llm_gateway_node >/dev/null 2>&1; then
  eval "$ICAR_DOCKER_CMD; export ICAR_AUDIO_DIR=/root/icar_ros2_ws/icar_ws/src/audio; nohup ros2 run llm_gateway llm_gateway_node --ros-args -p tool_mode:=true </dev/null >/tmp/llm_gateway.log 2>&1 &'"
  sleep 2
fi

echo "[11/14] Verifying ROS graph"
CMD_INFO=""
for _ in $(seq 1 20); do
  CMD_INFO=$(docker exec -e ROS_DOMAIN_ID=30 autodrive_ros2 bash -lc \
    'source /opt/ros/foxy/setup.bash; ros2 topic info /cmd_vel 2>/dev/null' || true)
  if echo "$CMD_INFO" | grep -q 'Publisher count: 1' && \
     echo "$CMD_INFO" | grep -q 'Subscription count: 1'; then
    break
  fi
  sleep 1
done
echo "$CMD_INFO"
echo "$CMD_INFO" | grep -q 'Publisher count: 1'
echo "$CMD_INFO" | grep -q 'Subscription count: 1'
docker exec -e ROS_DOMAIN_ID=30 icar_ros2 bash -lc \
  'source /opt/ros/foxy/setup.bash; source /root/icar_ros2_ws/icar_ws/install/setup.bash; ros2 topic info /vision/detections'

echo "[12/14] Verifying web gateway"
curl --fail --silent --show-error --max-time 5 http://127.0.0.1:6500/health
echo
echo "=== iCar safe startup complete ==="
