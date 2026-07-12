"""llm_gateway — ROS2 LLM 网关包。

DeepSeek API 优先，规则兜底：
  - /llm/parse_task      自然语言 → 巡检任务 JSON
  - /llm/generate_report  任务日志 → 巡检报告文本

启动：ros2 run llm_gateway llm_gateway_node
参数：
  - provider: auto (默认) | deepseek | rule
  - default_route: ["A","B","C"]
  - max_logs_per_task: 200
"""
