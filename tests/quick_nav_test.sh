#!/bin/bash
source /opt/ros/foxy/setup.bash
export ROS_DOMAIN_ID=30

echo ">>> initialpose HOME"
ros2 topic pub --once /initialpose geometry_msgs/msg/PoseWithCovarianceStamped '{header: {frame_id: map}, pose: {pose: {position: {x: 10.762, y: 38.694}, orientation: {x: 0, y: 0, z: 0.7218473479080071, w: 0.692052314726406}}, covariance: [0.25,0,0,0,0,0,0,0.25,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0.0685]}}' 2>&1 | head -2
sleep 8

echo ">>> goal B (11.0, 38.0)"
ros2 topic pub --once /goal_pose geometry_msgs/msg/PoseStamped '{header: {frame_id: map}, pose: {position: {x: 11.0, y: 38.0}, orientation: {x: 0, y: 0, z: 0, w: 1}}}' 2>&1 | head -2

echo ">>> done"
