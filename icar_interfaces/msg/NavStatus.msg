# NavStatus.msg — 导航状态反馈
# 发布者: navigation_node
# 订阅者: task_manager_node, app_control_node

string status             # IDLE / NAVIGATING / ARRIVED / FAILED
float32 progress          # 导航进度 (0.0 ~ 1.0)
float32 distance_remain   # 剩余距离 (m)
string message            # 状态描述文本
