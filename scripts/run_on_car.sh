#!/bin/bash
# Run mock demo inside icar_ros2 container
docker exec icar_ros2 bash -c '
source /root/ros2_ws/install/setup.bash

ros2 run task_manager task_manager_node &
T=$!
sleep 1
ros2 run task_manager mock_navigation_node &
N=$!
sleep 1
ros2 run task_manager mock_sensor_node &
S=$!
sleep 1
ros2 run task_manager mock_vision_node &
V=$!
sleep 1
ros2 run task_manager report_generator_node &
R=$!
sleep 1
ros2 run task_manager mock_app_node &
A=$!

echo "=== MOCK DEMO RUNNING (10s) ==="
sleep 10

kill $T $N $S $V $R $A 2>/dev/null
wait 2>/dev/null
echo "=== DONE ==="
'
