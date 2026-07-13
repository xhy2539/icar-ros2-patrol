#!/bin/bash
# Test all 10 tools by publishing to /llm/user_command
source /opt/ros/foxy/setup.bash
source /root/icar_ros2_ws/icar_ws/install/setup.bash
export ROS_DOMAIN_ID=30

cmds=(
  "巡检A点和B点"
  "当前状态"
  "立即停下"
  "取消任务"
  "复位任务"
  "看到什么了"
  "到哪了"
  "安全吗"
  "播放欢迎语音"
  "发个警告"
  "播放碎玉轩小曲"
)

for cmd in "${cmds[@]}"; do
  echo "=== $cmd ==="
  ros2 topic pub --once /llm/user_command std_msgs/msg/String "{data: \"$cmd\"}" 2>/dev/null
  sleep 1.5
done
echo "ALL DONE"
