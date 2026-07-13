#!/bin/bash
# Safe, idempotent car startup for the unified ROS-domain runtime.

set -euo pipefail

LOG="/home/jetson/icar_startup.log"
REPO="/home/jetson/icar-ros2-patrol"
DOMAIN=30
exec > >(tee -a "$LOG") 2>&1
echo "=== iCar safe startup $(date) ==="

echo "[1/10] Waiting for chassis serial"
for _ in $(seq 1 30); do
  [ -e /dev/myserial ] && break
  sleep 1
done
[ -e /dev/myserial ] || { echo "ERROR: /dev/myserial missing"; exit 1; }

echo "[2/10] Starting containers"
docker start autodrive_ros2 >/dev/null
docker start icar_ros2 >/dev/null
docker update --restart unless-stopped autodrive_ros2 icar_ros2 >/dev/null
sleep 4

echo "[3/10] Installing shared ROS domain environment"
for container in autodrive_ros2 icar_ros2; do
  docker exec "$container" sh -c \
    'printf "%s\n" "export ROS_DOMAIN_ID=30" > /etc/profile.d/icar_ros_domain.sh'
  docker exec "$container" pkill -f '/opt/ros/foxy/bin/_ros2_daemon' 2>/dev/null || true
done
docker exec autodrive_ros2 bash -lc \
  'source /opt/ros/foxy/setup.bash; export ROS_DOMAIN_ID=30; ros2 daemon start >/dev/null'

echo "[4/10] Removing legacy control and camera processes"
pkill -f 'Rosmaster-App/rosmaster/app.py' 2>/dev/null || true
pkill -f '^python3 app.py$' 2>/dev/null || true
docker exec autodrive_ros2 pkill -f '^python3 /tmp/fast_bridge.py$' 2>/dev/null || true

echo "[5/10] Starting chassis bringup and lidar"
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

echo "[6/10] Ensuring packaged app_control is installed"
if ! docker exec autodrive_ros2 test -x \
  /root/icar_app_ws/install/app_control/lib/app_control/app_bridge_node; then
  tar --exclude='._*' -C "$REPO" -cf - app_control | \
    docker exec -i autodrive_ros2 bash -c \
      'mkdir -p /root/icar_app_ws/src; cd /root/icar_app_ws/src; rm -rf app_control; tar xf -'
  docker exec autodrive_ros2 bash -lc \
    'source /opt/ros/foxy/setup.bash
     source /root/yahboomcar_ros2_ws/yahboomcar_ws/install/setup.bash
     cd /root/icar_app_ws
     colcon build --packages-select app_control --symlink-install'
fi

echo "[7/10] Starting camera and vision stack"
ICAR_ROS_DOMAIN_ID="$DOMAIN" "$REPO/scripts/start_car_vision_stack.sh"

echo "[8/10] Starting safe App/video/control stack"
ICAR_ROS_CONTAINER=autodrive_ros2 ROS_DOMAIN_ID="$DOMAIN" \
  "$REPO/scripts/start_car_app_stack.sh"

echo "[9/10] Verifying ROS graph"
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

echo "[10/10] Verifying web gateway"
curl --fail --silent --show-error --max-time 5 http://127.0.0.1:6500/health
echo
echo "=== iCar safe startup complete ==="
