#!/bin/bash
source /opt/ros/foxy/setup.bash
source /root/icar_ros2_ws/icar_ws/install/setup.bash
export ROS_DOMAIN_ID=30

echo "=== query_vision ==="
ros2 topic pub --once /llm/user_command std_msgs/msg/String "{data: '看到什么了'}" 2>/dev/null
sleep 3
tail -3 /tmp/llm_standalone.log

echo ""
echo "=== check_safety ==="
ros2 topic pub --once /llm/user_command std_msgs/msg/String "{data: '安全吗'}" 2>/dev/null
sleep 3
tail -3 /tmp/llm_standalone.log

echo ""
echo "=== query_navigation ==="
ros2 topic pub --once /llm/user_command std_msgs/msg/String "{data: '到哪了'}" 2>/dev/null
sleep 3
tail -3 /tmp/llm_standalone.log

echo ""
echo "=== get_robot_status ==="
ros2 topic pub --once /llm/user_command std_msgs/msg/String "{data: '当前状态'}" 2>/dev/null
sleep 3
tail -3 /tmp/llm_standalone.log

echo ""
echo "=== play_audio ==="
ros2 topic pub --once /llm/user_command std_msgs/msg/String "{data: '播放欢迎语音'}" 2>/dev/null
sleep 2
tail -2 /tmp/llm_standalone.log

echo ""
echo "DONE"
