cmake_minimum_required(VERSION 3.5)
project(icar_interfaces)

# 默认依赖
find_package(ament_cmake REQUIRED)
find_package(rosidl_default_generators REQUIRED)
find_package(builtin_interfaces REQUIRED)
find_package(std_msgs REQUIRED)
find_package(geometry_msgs REQUIRED)
find_package(sensor_msgs REQUIRED)
find_package(nav_msgs REQUIRED)

# 自定义消息定义
set(msg_files
  "msg/NavStatus.msg"
  "msg/ObstacleStatus.msg"
  "msg/Detection.msg"
  "msg/DetectionArray.msg"
  "msg/EnvData.msg"
  "msg/SensorAlert.msg"
  "msg/TaskRequest.msg"
  "msg/TaskStatus.msg"
  "msg/TaskLog.msg"
)

# 自定义服务定义
set(srv_files
  "srv/ParseTask.srv"
  "srv/TaskControl.srv"
)

# 生成消息和服务代码
rosidl_generate_interfaces(${PROJECT_NAME}
  ${msg_files}
  ${srv_files}
  DEPENDENCIES builtin_interfaces std_msgs geometry_msgs sensor_msgs nav_msgs
)

ament_export_dependencies(rosidl_default_runtime)
ament_package()
