# llm_gateway

ROS2 gateway for P2 LLM features.

Services:

- `/llm/parse_task` (`icar_interfaces/srv/ParseTask`)
- `/llm/generate_report` (`icar_interfaces/srv/GenerateReport`)

The first implementation uses deterministic rule fallback so integration tests
work without network access or a live model server. It does not publish
`/cmd_vel`; all movement decisions remain behind `task_manager`.
