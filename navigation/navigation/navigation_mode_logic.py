from dataclasses import dataclass


@dataclass(frozen=True)
class NavigationStatusPlan:
    status: str
    progress: float
    distance_remain: float
    message: str


def _clamp(value, minimum, maximum):
    return max(minimum, min(maximum, value))


def plan_navigation_status(
    mode,
    elapsed_sec,
    duration_sec,
    total_distance,
    obstacle_risk,
    danger_elapsed_sec=0.0,
    obstacle_fail_after_sec=999.0,
    fail_after_sec=None,
):
    mode = (mode or "mock").strip().lower()
    duration = max(float(duration_sec), 0.001)
    progress = _clamp(float(elapsed_sec) / duration, 0.0, 1.0)
    distance_remain = max(float(total_distance) * (1.0 - progress), 0.0)

    if obstacle_risk == "danger":
        if float(danger_elapsed_sec) >= float(obstacle_fail_after_sec):
            return NavigationStatusPlan(
                status="FAILED",
                progress=progress,
                distance_remain=distance_remain,
                message="navigation failed because obstacle remained danger too long",
            )
        return NavigationStatusPlan(
            status="NAVIGATING",
            progress=progress,
            distance_remain=distance_remain,
            message="obstacle detected, holding navigation state",
        )

    if mode == "real":
        real_progress = min(progress, 0.99)
        return NavigationStatusPlan(
            status="NAVIGATING",
            progress=real_progress,
            distance_remain=max(float(total_distance) * (1.0 - real_progress), 0.0),
            message="waiting for real navigation feedback",
        )

    if fail_after_sec is not None and float(elapsed_sec) >= float(fail_after_sec):
        return NavigationStatusPlan(
            status="FAILED",
            progress=progress,
            distance_remain=distance_remain,
            message="navigation timeout in mock scenario",
        )

    if progress >= 1.0:
        return NavigationStatusPlan(
            status="ARRIVED",
            progress=1.0,
            distance_remain=0.0,
            message="mock goal reached",
        )

    return NavigationStatusPlan(
        status="NAVIGATING",
        progress=progress,
        distance_remain=distance_remain,
        message="mock navigation in progress",
    )
