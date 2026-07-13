# llm_gateway

ROS2 gateway for P2 LLM features.

Services:

- `/llm/parse_task` (`icar_interfaces/srv/ParseTask`)
- `/llm/generate_report` (`icar_interfaces/srv/GenerateReport`)

The first implementation uses deterministic rule fallback so integration tests
work without network access or a live model server. It does not publish
`/cmd_vel`; all movement decisions remain behind `task_manager`.

## Complex task continuation

Tool mode accepts a safe `execute_plan` containing up to 12 allowlisted steps.
`start_patrol` automatically waits for `/task/status=COMPLETED` before the next
step runs. `FAILED` or `CANCELLED` ends the plan, so follow-up audio, vision,
tracking, or status actions cannot run after a failed patrol.

Example:

```text
巡检 A、B 点，完成后播放完成提示音，然后查询视觉
```

The gateway never puts direct velocity commands in a complex plan.
