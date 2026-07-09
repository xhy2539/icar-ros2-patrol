# SensorAlert.msg — 传感器异常告警
# 发布者: sensor_node
# 订阅者: task_manager_node, app_control_node
# 频率: 按需（异常触发时）

string sensor_type          # 传感器类型 (smoke/temperature/pm25/humidity)
float32 current_value       # 当前值
float32 threshold           # 阈值
string severity             # 严重级别 (WARN/ERROR)
string message              # 告警描述
