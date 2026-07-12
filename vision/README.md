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
- `vision_node`: subscribes to the camera image topic and publishes
  `icar_interfaces/DetectionArray` results to `/vision/detections`. It also
  publishes optional JSON debug data to `/vision/detections_json`. The node
  includes lightweight color-object and lane-line detection for no-model tests,
  and can optionally load an Ultralytics YOLO model through runtime parameters.
- `target_tracker`: subscribes to `/vision/detections`, selects a target such as
  `person`, and publishes follow-control velocity hints to `/vision/target_cmd_vel`.
  It does not publish directly to `/cmd_vel` by default. It stays idle until an
  App/task command is received on `/vision/target_tracking/command`.

## Class Table

The initial class table is in `config/vision_classes.json`.

- Common pretrained classes: `person`, `backpack`, `handbag`, `bottle`, `chair`,
  `bed`, `stop sign`, `traffic light`.
- Project/custom classes: `obstacle`, `sign_A`, `sign_B`, `sign_C`,
  `water`, `road_lane`.

Common classes can start from a COCO-pretrained YOLO model. Custom checkpoint
signs, low-position obstacles, and water/wet-floor scenes need real images and
annotation before fine-tuning.

For a no-training water/puddle demo, `vision_node` can optionally load a second
Ultralytics YOLO-World model and map prompts such as `water puddle`, `puddle`,
`standing water`, `wet floor`, and `water on floor` to the project class
`water`. This is useful for early validation, but a custom water dataset and
fine-tuned checkpoint will be more reliable for the final car scene.

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

Terminal 4 observes typed detection results:

```bash
ros2 topic echo /vision/detections
```

Optional JSON debug output:

```bash
ros2 topic echo /vision/detections_json
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

## Local Webcam Test

For quick local validation without ROS2 or a VM, use the Windows Python webcam
script:

```bash
cd D:\北交大两周项目\code_repos\icar-ros2-patrol-yolo-obstacle
python vision\local_webcam_detect.py --backend yolo --model yolo11n.pt --camera 0
```

The first run may download `yolo11n.pt`. Put common blocking objects such as a
chair, backpack, suitcase, bottle, bed, couch, or table in front of the camera;
the script publishes them visually as `obstacle:<raw_yolo_class>` on the preview
window. Press `s` to save a screenshot and JSON result, and `q` to quit.

Headless one-frame check:

```bash
python vision\local_webcam_detect.py --backend yolo --model yolo11n.pt \
  --camera 0 --frames 1 --no-window
```

Optional YOLO-World water/puddle check:

```bash
python vision\local_webcam_detect.py --backend yolo --model yolo11n.pt \
  --water-model yolov8s-world.pt --camera 0
```

The first water run may download the YOLO-World checkpoint and text encoder
dependencies. Water detections are shown as `water:<raw_prompt>` in the preview
and JSON output.

Optional nursing-home fall hazard check for stairs, steps, curbs, thresholds,
ramps, ledges, and floor height changes:

```bash
python vision\local_webcam_detect.py --backend yolo --model yolo11n.pt \
  --water-model yolov8s-world.pt \
  --fall-hazard-backend world \
  --fall-hazard-model yolov8s-world.pt \
  --fall-hazard-frame-stride 5 \
  --camera 0
```

Fall-risk detections are shown as `fall_hazard:<raw_prompt>` in the preview and
JSON output. This is an RGB open-vocabulary check; final car-side height-change
judgement should also use Astra depth data to confirm the actual vertical
drop/rise.

Fallback without a YOLO model:

```bash
python vision\local_webcam_detect.py --backend color --camera 0
```

## Car Usage

Use the team-agreed container flow. Do not run camera commands on the host.

```bash
source ~/.bashrc
is
id
```

Inside `icar_ros2`, confirm the real camera topic first:

```bash
source /opt/ros/foxy/setup.bash
source /root/icar_ros2_ws/software/library_ws/install/setup.bash
source /root/icar_ros2_ws/icar_ws/install/setup.bash
export ROS_DOMAIN_ID=32
ros2 launch astra_camera astro_pro_plus.launch.xml
ros2 topic list | grep -E "image|camera|depth|rgb|color|astra|points"
```

For the Astra Plus on car `192.168.180.83`, `astra.launch.xml` started depth and
IR only and logged `color is not enable`. Use
`astro_pro_plus.launch.xml` for the RGB UVC stream. Real data checked on
2026-07-12:

- `/camera/color/image_raw`: `sensor_msgs/Image`, 640x480, `rgb8`, about 16.9 fps,
  `camera_color_optical_frame`.
- `/camera/depth/image_raw`: 640x480, `16UC1`, about 30.2 fps.
- `/camera/ir/image_raw`: 640x480, `mono8`, about 30.1 fps.

When the topic is known, build this repo in the ROS2 workspace and run:

```bash
colcon build --symlink-install --packages-select icar_interfaces vision_patrol
source install/setup.bash
ros2 run vision_patrol camera_probe --ros-args \
  -p image_topic:=/camera/color/image_raw \
  -p save_first_frame:=false
```

Then run the placeholder vision pipeline:

```bash
ros2 run vision_patrol vision_node --ros-args \
  -p image_topic:=/camera/color/image_raw \
  -p detector_backend:=color \
  -p mode:=detect
```

Replace `/camera/color/image_raw` with the actual topic reported by the car.
If `/camera/color/image_raw` has no data, first confirm whether the APP service
is occupying `/dev/video0`; coordinate before stopping APP processes.
If `/dev/sensors` points to a missing `/dev/ttyUSB2`, do not rewrite the unified
soft links. For vision-only checks, the `icar_ros2` container can be started
without mounting `/dev/sensors`; restore the standard container flow when the
sensor device is present again.

Optional YOLO runtime, when the car already has `ultralytics` and a local model:

```bash
ros2 run vision_patrol vision_node --ros-args \
  -p image_topic:=/camera/color/image_raw \
  -p detector_backend:=yolo \
  -p yolo_model:=/home/jetson/models/yolo11n.pt \
  -p yolo_device:=0 \
  -p yolo_confidence:=0.35 \
  -p yolo_imgsz:=640 \
  -p target_classes:="[person,obstacle,water,sign]" \
  -p publish_annotated:=true
```

Optional YOLO-World water/puddle fusion:

```bash
ros2 run vision_patrol vision_node --ros-args \
  -p image_topic:=/camera/color/image_raw \
  -p detector_backend:=yolo \
  -p yolo_model:=/home/jetson/models/yolo11n.pt \
  -p water_model:=/home/jetson/models/yolov8s-world.pt \
  -p water_classes:="[water puddle,puddle,standing water,wet floor,water on floor]" \
  -p water_confidence:=0.15 \
  -p target_classes:="[person,obstacle,water]" \
  -p publish_annotated:=true
```

With `scripts/start_vision.sh`, the same setup can be started with environment
variables:

```bash
DETECTOR_BACKEND=yolo \
YOLO_MODEL=/home/jetson/models/yolo11n.pt \
WATER_MODEL=/home/jetson/models/yolov8s-world.pt \
DETECTION_CLASSES=person,obstacle,water \
PUBLISH_ANNOTATED=true \
./scripts/start_vision.sh detect
```

YOLO obstacle mapping is enabled by default. Common COCO classes that can block
the patrol path, such as `chair`, `dining table`, `backpack`, `handbag`,
`suitcase`, `bottle`, `bed`, `couch`, `bench`, and `potted plant`, are published
as the project class `obstacle`. The original YOLO class is still included as
`raw_class_name` in `/vision/detections_json` for debugging.

Override the mapped classes when needed:

```bash
ros2 run vision_patrol vision_node --ros-args \
  -p detector_backend:=yolo \
  -p yolo_model:=/home/jetson/models/yolo11n.pt \
  -p obstacle_classes:="[chair,backpack,suitcase,bottle,dining table]" \
  -p obstacle_min_area_ratio:=0.003
```

If the YOLO model cannot be loaded, the node logs a warning and falls back to
the lightweight detector so the ROS2 vision chain can still be demonstrated.

## Integration Topics

- Input: camera RGB image topic, expected to be similar to
  `/camera/color/image_raw`.
- Output: `/vision/camera_status` (`std_msgs/String`, JSON).
- Output: `/vision/detections` (`icar_interfaces/DetectionArray`, main APP/task
  interface).
- Optional output: `/vision/detections_json` (`std_msgs/String`, JSON debug).
- Input: `/vision/capture_command` (`std_msgs/String`, JSON command).
- Output: `/vision/capture_status` (`std_msgs/String`, JSON).
- Input: `/vision/target_tracking/command` (`std_msgs/String`, JSON command).
- Output: `/vision/target_cmd_vel` (`geometry_msgs/Twist`, target-following
  velocity hint).
- Output: `/vision/target_tracking/status` (`std_msgs/String`, JSON).
- Optional output: `/vision/annotated_image` (`sensor_msgs/Image`).
