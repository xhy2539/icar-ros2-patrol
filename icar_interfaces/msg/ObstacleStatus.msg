# ObstacleStatus.msg — 障碍物检测状态
# 发布者: obstacle_avoid_node
# 订阅者: task_manager_node, app_control_node

bool is_obstacle           # 是否存在障碍物
float32 min_distance       # 最近障碍物距离 (m)
string direction           # 障碍物方位 (front/left/right/back)
string risk_level          # 风险等级 (safe/warning/danger)
string action              # 建议动作 (none/slow_down/stop/turn)
