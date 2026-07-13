import json
from dataclasses import dataclass
from typing import Optional


ACTIVE_STATES = {
    "RUNNING",
    "NAVIGATING",
    "CHECKPOINT",
    "DETECTING",
    "COLLECTING",
}

RESETTABLE_STATES = {
    "COMPLETED",
    "FAILED",
    "CANCELLED",
}


@dataclass(frozen=True)
class TaskControlPlan:
    success: bool
    message: str
    task_id: str
    status: str
    data_json: str
    should_stop: bool = False
    next_state: Optional[str] = None
    emergency_stop_active: Optional[bool] = None
    event_type: str = "LLM_CONTROL"
    severity: str = "INFO"


def _status_payload(state, task_id, route, route_index, emergency_stop_active):
    return {
        "task_id": task_id,
        "status": state,
        "route": list(route),
        "current_step": route_index + 1 if route else 0,
        "total_steps": len(route),
        "emergency_stop_active": emergency_stop_active,
    }


def plan_task_control(
    action,
    state,
    task_id,
    route,
    route_index,
    emergency_stop_active,
):
    """Plan a safe task-manager control action for an external LLM gateway."""
    normalized_action = (action or "").strip().lower()
    normalized_state = (state or "").strip().upper()
    payload = _status_payload(
        normalized_state,
        task_id,
        route,
        route_index,
        emergency_stop_active,
    )

    if normalized_action in {"get_status", "status"}:
        return TaskControlPlan(
            success=True,
            message="status returned",
            task_id=task_id,
            status=normalized_state,
            data_json=json.dumps(payload, ensure_ascii=False),
        )

    if normalized_action in {"stop", "emergency_stop"}:
        payload["action"] = normalized_action
        return TaskControlPlan(
            success=True,
            message="stop command accepted",
            task_id=task_id,
            status=normalized_state,
            data_json=json.dumps(payload, ensure_ascii=False),
            should_stop=True,
            emergency_stop_active=True,
            severity="WARN",
        )

    if normalized_action == "cancel":
        if normalized_state not in ACTIVE_STATES:
            return TaskControlPlan(
                success=False,
                message=f"cannot cancel task while state is {normalized_state}",
                task_id=task_id,
                status=normalized_state,
                data_json=json.dumps(payload, ensure_ascii=False),
                severity="WARN",
            )

        payload["action"] = "cancel"
        return TaskControlPlan(
            success=True,
            message="cancel command accepted",
            task_id=task_id,
            status="CANCELLED",
            data_json=json.dumps(payload, ensure_ascii=False),
            should_stop=True,
            next_state="CANCELLED",
            emergency_stop_active=True,
        )

    if normalized_action == "reset":
        can_reset = normalized_state in RESETTABLE_STATES or (
            normalized_state == "PENDING" and emergency_stop_active
        )
        if not can_reset:
            return TaskControlPlan(
                success=False,
                message=f"cannot reset task while state is {normalized_state}",
                task_id=task_id,
                status=normalized_state,
                data_json=json.dumps(payload, ensure_ascii=False),
                severity="WARN",
            )

        payload["action"] = "reset"
        return TaskControlPlan(
            success=True,
            message="reset command accepted",
            task_id=task_id,
            status="PENDING",
            data_json=json.dumps(payload, ensure_ascii=False),
            next_state=None if normalized_state == "PENDING" else "PENDING",
            emergency_stop_active=False,
        )

    return TaskControlPlan(
        success=False,
        message=f"unsupported task control action: {normalized_action}",
        task_id=task_id,
        status=normalized_state,
        data_json=json.dumps(payload, ensure_ascii=False),
        severity="WARN",
    )
