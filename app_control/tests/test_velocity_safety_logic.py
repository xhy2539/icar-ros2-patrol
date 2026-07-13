import importlib.util
import unittest
from pathlib import Path


def load_logic_module():
    path = (
        Path(__file__).resolve().parents[1]
        / "app_control"
        / "velocity_safety_logic.py"
    )
    spec = importlib.util.spec_from_file_location("velocity_safety_logic", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class VelocitySafetyLogicTest(unittest.TestCase):
    def setUp(self):
        self.logic = load_logic_module()

    def test_front_danger_blocks_forward_but_allows_turn_and_reverse(self):
        forward = self.logic.constrain_for_obstacle(
            0.3, 0.0, 0.8, "danger", "stop", "front"
        )
        reverse = self.logic.constrain_for_obstacle(
            -0.2, 0.0, 0.4, "danger", "stop", "front"
        )
        self.assertEqual(forward.linear_x, 0.0)
        self.assertEqual(forward.angular_z, 0.8)
        self.assertEqual(reverse.linear_x, -0.2)
        self.assertEqual(reverse.angular_z, 0.4)

    def test_warning_slows_forward_without_stopping(self):
        result = self.logic.constrain_for_obstacle(
            0.4, 0.0, 0.0, "warning", "slow_down", "front", 0.12
        )
        self.assertEqual(result.linear_x, 0.12)

    def test_safe_motion_is_unchanged(self):
        result = self.logic.constrain_for_obstacle(
            0.3, 0.1, -0.5, "safe", "none", "front"
        )
        self.assertEqual(tuple(result[:3]), (0.3, 0.1, -0.5))
        self.assertFalse(result.limited)


if __name__ == "__main__":
    unittest.main()
