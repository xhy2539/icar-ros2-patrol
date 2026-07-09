# Vision Module

This folder contains the camera access and vision pipeline code owned by the
vision role. The first target is to connect to the car camera topic safely; YOLO
object detection and road detection will be added on top of the same ROS2 input.

## Current Package

`vision/vision_patrol` is a ROS2 Foxy Python package.

- `camera_probe`: subscribes to the camera image topic, publishes JSON status to
  `/vision/camera_status`, and can save one sample frame.
- `dataset_recorder`: saves images on demand or at a bounded interval for YOLO
  dataset collection and inspection screenshots.
- `fake_camera`: publishes a synthetic patrol camera image for off-car tests.
- `vision_node`: subscribes to the camera image topic and publishes JSON results
  to `/vision/detections`. It currently includes lightweight color-object and
  lane-line detection so the ROS2 flow can be tested before YOLO is added.
- `target_tracker`: subscribes to `/vision/detections`, selects a target such as
  `person`, and publishes follow-control velocity hints to `/vision/target_cmd_vel`.
  It does not publish directly to `/cmd_vel` by default. It stays idle until an
  App/task command is received on `/vision/target_tracking/command`.

## Class Table

The initial class table is in `config/vision_classes.json`.

- Common pretrained classes: `person`, `backpack`, `handbag`, `bottle`, `chair`,
  `stop sign`, `traffic light`.
- Project/custom classes: `obstacle`, `sign_A`, `sign_B`, `sign_C`,
  `danger_object`, `road_lane`.

Common classes can start from a COCO-pretrained YOLO model. Custom checkpoint
signs and project-specific danger objects need real images and annotation before
fine-tuning.

## Off-Car Simulation

Use the Ubuntu 20.04 + ROS2 Foxy VM for this flow.

```bash
cd ~/ros2_ws
colcon build --symlink-install --packages-select vision_patrol
source install/setup.bash
```

Terminal 1 publishes a fake camera feed:

```bash
ros2 run vision_patrol fake_camera --ros-args \
  -p image_topic:=/camera/color/image_raw
```

Terminal 2 checks camera reception:

```bash
ros2 run vision_patrol camera_probe --ros-args \
  -p image_topic:=/camera/color/image_raw \
  -p save_first_frame:=true
```

Terminal 3 runs the vision pipeline:

```bash
ros2 run vision_patrol vision_node --ros-args \
  -p image_topic:=/camera/color/image_raw \
  -p enable_road_detection:=true \
  -p publish_annotated:=true
```

Terminal 4 observes JSON results:

```bash
ros2 topic echo /vision/detections
```

Optional target tracking test:

```bash
ros2 run vision_patrol target_tracker --ros-args \
  -p detections_topic:=/vision/detections \
  -p cmd_vel_topic:=/vision/target_cmd_vel
```

Start tracking a person:

```bash
ros2 topic pub --once /vision/target_tracking/command std_msgs/String \
  "{data: '{\"action\":\"start\",\"class_name\":\"person\"}'}"
```

Switch to another target class:

```bash
ros2 topic pub --once /vision/target_tracking/command std_msgs/String \
  "{data: '{\"action\":\"select_target\",\"class_name\":\"bottle\"}'}"
```

Stop tracking:

```bash
ros2 topic pub --once /vision/target_tracking/command std_msgs/String \
  "{data: '{\"action\":\"stop\"}'}"
```

Observe velocity hints:

```bash
ros2 topic echo /vision/target_cmd_vel
ros2 topic echo /vision/target_tracking/status
```

Optional dataset/screenshot recorder:

```bash
ros2 run vision_patrol dataset_recorder --ros-args \
  -p image_topic:=/camera/color/image_raw \
  -p save_dir:=/tmp/icar_vision_dataset \
  -p max_images:=50
```

Capture one frame from another terminal:

```bash
ros2 topic pub --once /vision/capture_command std_msgs/String \
  "{data: '{\"action\":\"capture_once\",\"tag\":\"mock_test\"}'}"
```

Start saving one frame every 3 seconds:

```bash
ros2 topic pub --once /vision/capture_command std_msgs/String \
  "{data: '{\"action\":\"set_interval\",\"interval_sec\":3.0}'}"
```

Stop interval capture:

```bash
ros2 topic pub --once /vision/capture_command std_msgs/String \
  "{data: '{\"action\":\"stop\"}'}"
```

## Car Usage

Use the team-agreed container flow. Do not run camera commands on the host.

```bash
~/run_docker.sh
id
```

Inside `icar_ros2`, confirm the real camera topic first:

```bash
source /opt/ros/foxy/setup.bash
m1
ros2 topic list | grep -E "image|camera|depth|rgb|color|astra|points"
```

When the topic is known, build this repo in the ROS2 workspace and run:

```bash
colcon build --symlink-install --packages-select vision_patrol
source install/setup.bash
ros2 run vision_patrol camera_probe --ros-args \
  -p image_topic:=/camera/color/image_raw \
  -p save_first_frame:=true
```

Then run the placeholder vision pipeline:

```bash
ros2 run vision_patrol vision_node --ros-args \
  -p image_topic:=/camera/color/image_raw \
  -p mode:=detect
```

Replace `/camera/color/image_raw` with the actual topic reported by the car.

## Integration Topics

- Input: camera RGB image topic, expected to be similar to
  `/camera/color/image_raw`.
- Output: `/vision/camera_status` (`std_msgs/String`, JSON).
- Output: `/vision/detections` (`std_msgs/String`, JSON for the P0 prototype).
- Input: `/vision/capture_command` (`std_msgs/String`, JSON command).
- Output: `/vision/capture_status` (`std_msgs/String`, JSON).
- Input: `/vision/target_tracking/command` (`std_msgs/String`, JSON command).
- Output: `/vision/target_cmd_vel` (`geometry_msgs/Twist`, target-following
  velocity hint).
- Output: `/vision/target_tracking/status` (`std_msgs/String`, JSON).
- Optional output: `/vision/annotated_image` (`sensor_msgs/Image`).

The project design document may later replace the JSON string with custom
`DetectionArray` messages after the first camera and detection demo is stable.
