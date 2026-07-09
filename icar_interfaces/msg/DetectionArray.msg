# DetectionArray.msg — 视觉检测结果数组
# 发布者: vision_node
# 订阅者: task_manager_node, app_control_node, llm_gateway_node(P2)

std_msgs/Header header              # 时间戳
icar_interfaces/Detection[] detections  # 检测目标列表
