# TaskRequest.msg — 任务请求
# 发布者: app_control_node
# 订阅者: task_manager_node
# 频率: 按需

string task_type            # 任务类型 (manual_control/patrol/inspect)
string[] route              # 巡检路线点 (如 ["A","B","C"])
string params               # 任务参数 JSON
