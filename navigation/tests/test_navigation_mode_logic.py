import importlib.util
import unittest
from pathlib import Path


def load_mode_module():
    module_path = (
        Path(__file__).resolve().parents[1]
        / "navigation"
        / "navigation_mode_logic.py"
    )
    spec = importlib.util.spec_from_file_location("navigation_mode_logic", module_path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class NavigationModeLogicTest(unittest.TestCase):
    def setUp(self):
        self.logic = load_mode_module()

    def test_mock_mode_reaches_goal_after_duration(self):
        result = self.logic.plan_navigation_status(
            mode="mock",
            elapsed_sec=8.0,
            duration_sec=8.0,
            total_distance=2.0,
            obstacle_risk="safe",
        )

        self.assertEqual(result.status, "ARRIVED")
        self.assertEqual(result.progress, 1.0)
        self.assertEqual(result.distance_remain, 0.0)

    def test_real_mode_does_not_auto_arrive_without_external_feedback(self):
        result = self.logic.plan_navigation_status(
            mode="real",
            elapsed_sec=80.0,
            duration_sec=8.0,
            total_distance=2.0,
            obstacle_risk="safe",
        )

        self.assertEqual(result.status, "NAVIGATING")
        self.assertLess(result.progress, 1.0)
        self.assertIn("waiting for real navigation feedback", result.message)

    def test_real_mode_reports_failed_when_obstacle_stays_danger(self):
        result = self.logic.plan_navigation_status(
            mode="real",
            elapsed_sec=5.0,
            duration_sec=8.0,
            total_distance=2.0,
            obstacle_risk="danger",
            danger_elapsed_sec=5.0,
            obstacle_fail_after_sec=3.0,
        )

        self.assertEqual(result.status, "FAILED")
        self.assertIn("obstacle", result.message)


if __name__ == "__main__":
    unittest.main()
