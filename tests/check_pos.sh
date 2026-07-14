#!/bin/bash
source /opt/ros/foxy/setup.bash
export ROS_DOMAIN_ID=30
echo ">>> AMCL position"
timeout 4 ros2 run tf2_ros tf2_echo map base_footprint 2>&1 | head -3
echo ">>> sending goal D (11.331, 8.676)"
ros2 topic pub --once /goal_pose geometry_msgs/msg/PoseStamped '{header: {frame_id: map}, pose: {position: {x: 11.331, y: 8.676}, orientation: {x: 0, y: 0, z: -0.7393, w: 0.6733}}}' 2>&1 | head -2
echo ">>> done"
