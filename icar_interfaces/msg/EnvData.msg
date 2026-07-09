# EnvData.msg — 环境传感器数据合集
# 发布者: sensor_node
# 订阅者: task_manager_node, app_control_node, llm_gateway_node(P2)
# 频率: 1 Hz

std_msgs/Header header      # 时间戳
float32 temperature         # 温度 (℃) - DHT22
float32 humidity            # 湿度 (%) - DHT22
float32 smoke               # 烟雾浓度 (ppm) - MQ-2
float32 pm25                # PM2.5 (μg/m³) - PMS5003
float32 light               # 光照强度 (lux) - BH1750
float32 pressure            # 气压 (hPa) - BMP280
