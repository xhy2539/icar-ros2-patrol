# TaskStatus.msg — 任务执行状态
# 发布者: task_manager_node
# 订阅者: app_control_node
# 频率: 按需（状态变化时）

string task_id              # 任务 ID
string status               # PENDING / RUNNING / NAVIGATING / CHECKPOINT / DETECTING / COLLECTING / COMPLETED / FAILED / CANCELLED
int32 current_step          # 当前步骤编号
int32 total_steps           # 总步骤数
string message              # 状态描述
