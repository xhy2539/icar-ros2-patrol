#!/bin/bash
# ============================================================
# start_sensor.sh
# 启动传感器采集模块节点
# 负责人：王璐
# ============================================================
#
# 启动节点：
#   - sensor_node    多传感器数据采集与发布
#
# 采集传感器：
#   - 温湿度传感器 (DHT22)
#   - 烟雾传感器 (MQ-2)
#   - PM2.5 传感器 (PMS5003)
#   - 光照传感器 (BH1750)
#   - 气压传感器 (BMP280)
#
# 用法：
#   ./scripts/start_sensor.sh
#
# 前置条件：
#   - ROS2 环境已 source
#   - 工作空间已 source
#   - 所有传感器硬件已连接并配置
# ============================================================

set -e

echo "============================================="
echo "  Starting Sensor Module..."
echo "============================================="

# TODO: 启动传感器采集节点
# ros2 run sensor sensor_node &

# TODO: 可选配置参数
# ros2 run sensor sensor_node --ros-args \
#   -p sample_rate:=1.0 \
#   -p alert_threshold_temp:=50.0 \
#   -p alert_threshold_smoke:=100.0 &

echo "Sensor Module started."
