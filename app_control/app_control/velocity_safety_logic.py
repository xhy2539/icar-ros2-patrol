"""Directional velocity limits used by the runtime velocity mux."""

from typing import NamedTuple


class SafeVelocity(NamedTuple):
    linear_x: float
    linear_y: float
    angular_z: float
    limited: bool


def constrain_for_obstacle(
    linear_x,
    linear_y,
    angular_z,
    risk_level,
    action,
    direction,
    warning_max_linear=0.12,
):
    """Block motion toward danger while preserving escape directions.

    A front obstacle must not prevent Nav2 from rotating or backing away; a
    full zero-velocity override would deadlock static-obstacle recovery.
    """
    x = float(linear_x)
    y = float(linear_y)
    z = float(angular_z)
    original = (x, y, z)
    risk = str(risk_level).strip().lower()
    action = str(action).strip().lower()
    direction = str(direction).strip().lower() or "front"
    warning_limit = max(0.0, float(warning_max_linear))

    if risk == "warning":
        if direction in ("front", "front_left", "front_right") and x > warning_limit:
            x = warning_limit
        return SafeVelocity(x, y, z, (x, y, z) != original)

    if risk != "danger":
        return SafeVelocity(x, y, z, False)

    if direction in ("front", "front_left", "front_right"):
        x = min(x, 0.0)
    elif direction in ("back", "rear"):
        x = max(x, 0.0)
    elif direction == "left":
        y = min(y, 0.0)
        z = min(z, 0.0)
    elif direction == "right":
        y = max(y, 0.0)
        z = max(z, 0.0)
    else:
        # Unknown direction is treated as front, the sensor's primary sector.
        x = min(x, 0.0)
    return SafeVelocity(x, y, z, (x, y, z) != original)
