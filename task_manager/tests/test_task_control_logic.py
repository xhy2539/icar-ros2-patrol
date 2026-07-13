import importlib.util
import unittest
from pathlib import Path


def load_control_module():
    module_path = (
        Path(__file__).resolve().parents[1]
        / "task_manager"
        / "task_control_logic.py"
    )
    spec = importlib.util.spec_from_file_location("task_control_logic", module_path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class TaskControlLogicTest(unittest.TestCase):
    def setUp(self):
        self.logic = load_control_module()

    def test_get_status_returns_snapshot_without_stop(self):
        result = self.logic.plan_task_control(
            action="get_status",
            state="NAVIGATING",
            task_id="task_001",
            route=["A", "B"],
            route_index=0,
            emergency_stop_active=False,
        )

        self.assertTrue(result.success)
        self.assertFalse(result.should_stop)
        self.assertIsNone(result.next_state)
        self.assertEqual(result.status, "NAVIGATING")
        self.assertEqual(result.task_id, "task_001")

    def test_cancel_running_task_stops_and_enters_cancelled(self):
        result = self.logic.plan_task_control(
            action="cancel",
            state="NAVIGATING",
            task_id="task_001",
            route=["A", "B"],
            route_index=0,
            emergency_stop_active=False,
        )

        self.assertTrue(result.success)
        self.assertTrue(result.should_stop)
        self.assertEqual(result.next_state, "CANCELLED")
        self.assertTrue(result.emergency_stop_active)
        self.assertEqual(result.event_type, "LLM_CONTROL")

    def test_stop_from_pending_still_publishes_safe_stop(self):
        result = self.logic.plan_task_control(
            action="stop",
            state="PENDING",
            task_id="",
            route=[],
            route_index=0,
            emergency_stop_active=False,
        )

        self.assertTrue(result.success)
        self.assertTrue(result.should_stop)
        self.assertIsNone(result.next_state)
        self.assertEqual(result.status, "PENDING")

    def test_reset_failed_task_allows_new_request(self):
        result = self.logic.plan_task_control(
            action="reset",
            state="FAILED",
            task_id="task_001",
            route=["A"],
            route_index=0,
            emergency_stop_active=True,
        )

        self.assertTrue(result.success)
        self.assertFalse(result.should_stop)
        self.assertEqual(result.next_state, "PENDING")
        self.assertFalse(result.emergency_stop_active)

    def test_reset_pending_estop_requires_explicit_reset_but_no_state_change(self):
        result = self.logic.plan_task_control(
            action="reset",
            state="PENDING",
            task_id="",
            route=[],
            route_index=0,
            emergency_stop_active=True,
        )

        self.assertTrue(result.success)
        self.assertIsNone(result.next_state)
        self.assertFalse(result.emergency_stop_active)

    def test_reset_pending_without_estop_is_rejected(self):
        result = self.logic.plan_task_control(
            action="reset",
            state="PENDING",
            task_id="",
            route=[],
            route_index=0,
            emergency_stop_active=False,
        )

        self.assertFalse(result.success)

    def test_invalid_action_is_rejected(self):
        result = self.logic.plan_task_control(
            action="dance",
            state="PENDING",
            task_id="",
            route=[],
            route_index=0,
            emergency_stop_active=False,
        )

        self.assertFalse(result.success)
        self.assertIn("unsupported", result.message)


if __name__ == "__main__":
    unittest.main()
