import importlib.util
import unittest
from pathlib import Path


def load_alarm_module():
    module_path = (
        Path(__file__).resolve().parents[1]
        / "task_manager"
        / "obstacle_alarm_logic.py"
    )
    spec = importlib.util.spec_from_file_location("obstacle_alarm_logic", module_path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class ObstacleAlarmLogicTest(unittest.TestCase):
    def setUp(self):
        self.logic = load_alarm_module()
        self.controller = self.logic.ObstacleAlarmController(repeat_sec=5.0)

    def test_danger_starts_once_and_repeats_after_cooldown(self):
        first = self.controller.update("danger", "stop", now=10.0)
        quiet = self.controller.update("danger", "stop", now=12.0)
        repeated = self.controller.update("danger", "stop", now=15.0)

        self.assertEqual(first.event, "started")
        self.assertTrue(first.should_beep)
        self.assertEqual(quiet.event, "none")
        self.assertEqual(repeated.event, "repeated")

    def test_clear_stops_alarm_and_next_danger_restarts(self):
        self.controller.update("danger", "stop", now=1.0)
        cleared = self.controller.update("safe", "none", now=2.0)
        restarted = self.controller.update("danger", "stop", now=3.0)

        self.assertEqual(cleared.event, "cleared")
        self.assertFalse(cleared.active)
        self.assertEqual(restarted.event, "started")

    def test_stop_action_is_alarm_worthy_even_if_risk_label_is_stale(self):
        decision = self.controller.update("warning", "stop", now=1.0)
        self.assertEqual(decision.event, "started")


if __name__ == "__main__":
    unittest.main()
