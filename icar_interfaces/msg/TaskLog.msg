# TaskLog.msg — 任务日志记录
# 发布者: task_manager_node
# 订阅者: app_control_node, llm_gateway_node(P2)
# 频率: 按需（巡检事件发生时）

string task_id              # 关联任务 ID
builtin_interfaces/Time timestamp  # 事件时间
string event_type           # 事件类型: NAV_START / CHECKPOINT_REACHED / SENSOR_READING / VISION_DETECT / ANOMALY / NAV_END / TASK_END
string data_json            # 事件数据 JSON
string severity             # INFO / WARN / ERROR
