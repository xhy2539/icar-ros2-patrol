import importlib.util
import unittest
from pathlib import Path


def load_logic_module():
    module_path = (
        Path(__file__).resolve().parents[1]
        / "task_manager"
        / "hazard_response_logic.py"
    )
    spec = importlib.util.spec_from_file_location("hazard_response_logic", module_path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class ObstacleDetourLogicTest(unittest.TestCase):
    def setUp(self):
        self.logic = load_logic_module()

    def test_danger_requests_replan_immediately_then_tracks_clearance(self):
        controller = self.logic.ObstacleDetourController(
            clear_sec=1.0, max_block_sec=10.0, max_replans=3
        )
        blocked = controller.update(danger=True, clear=False, now=1.0)
        clearing = controller.update(danger=False, clear=True, now=2.0)
        resumed = controller.update(danger=False, clear=True, now=3.0)

        self.assertEqual(blocked.event, "blocked")
        self.assertTrue(blocked.hold)
        self.assertTrue(blocked.should_replan)
        self.assertTrue(clearing.hold)
        self.assertEqual(resumed.event, "cleared")
        self.assertFalse(resumed.should_replan)
        self.assertEqual(resumed.retry_count, 1)

    def test_warning_does_not_release_an_active_hold(self):
        controller = self.logic.ObstacleDetourController(clear_sec=0.5)
        controller.update(danger=True, clear=False, now=1.0)
        warning = controller.update(danger=False, clear=False, now=2.0)
        self.assertTrue(warning.hold)
        self.assertFalse(warning.should_replan)

    def test_persistent_obstacle_fails_after_timeout(self):
        controller = self.logic.ObstacleDetourController(max_block_sec=5.0)
        controller.update(danger=True, clear=False, now=10.0)
        failed = controller.update(danger=True, clear=False, now=15.0)
        self.assertEqual(failed.event, "failed")
        self.assertTrue(failed.failed)


class WaterHazardLogicTest(unittest.TestCase):
    def setUp(self):
        self.logic = load_logic_module()

    def test_water_requires_consecutive_confident_frames_and_auto_clears(self):
        controller = self.logic.WaterHazardController(
            min_confidence=0.7,
            confirm_frames=2,
            clear_frames=2,
            repeat_sec=30.0,
        )
        detection = {"class_name": "puddle", "confidence": 0.85}

        first = controller.update([detection], now=1.0)
        confirmed = controller.update([detection], now=2.0)
        missing_once = controller.update([], now=3.0)
        cleared = controller.update([], now=4.0)

        self.assertEqual(first.event, "none")
        self.assertEqual(confirmed.event, "started")
        self.assertTrue(confirmed.should_report)
        self.assertTrue(missing_once.active)
        self.assertEqual(cleared.event, "cleared")
        self.assertFalse(cleared.active)

    def test_low_confidence_water_and_non_water_are_ignored(self):
        controller = self.logic.WaterHazardController(
            min_confidence=0.7, confirm_frames=1
        )
        result = controller.update(
            [
                {"class_name": "water", "confidence": 0.4},
                {"class_name": "person", "confidence": 0.99},
            ],
            now=1.0,
        )
        self.assertFalse(result.active)
        self.assertFalse(result.should_report)

    def test_explicit_reset_also_clears_water_state(self):
        controller = self.logic.WaterHazardController(confirm_frames=1)
        controller.update([{"class_name": "积水", "confidence": 0.9}], now=1.0)
        controller.reset()
        self.assertFalse(controller.active)
        self.assertEqual(controller.consecutive, 0)

    def test_visual_obstacle_uses_same_confirm_and_clear_edges(self):
        controller = self.logic.VisualHazardController(
            min_confidence=0.7,
            confirm_frames=1,
            clear_frames=1,
            class_keys=self.logic.VISUAL_OBSTACLE_CLASS_KEYS,
        )
        started = controller.update(
            [{"class_name": "obstacle", "confidence": 0.9}], now=1.0
        )
        cleared = controller.update([], now=2.0)
        self.assertEqual(started.event, "started")
        self.assertTrue(started.should_report)
        self.assertEqual(cleared.event, "cleared")

    def test_fall_hazard_stays_active_until_reset(self):
        controller = self.logic.VisualHazardController(
            min_confidence=0.7,
            confirm_frames=1,
            clear_frames=1,
            class_keys=self.logic.FALLEN_PERSON_CLASS_KEYS,
            latch_until_reset=True,
        )
        controller.update(
            [{"class_name": "fallen_person", "confidence": 0.95}], now=1.0
        )
        absent = controller.update([], now=2.0)
        self.assertTrue(absent.active)
        self.assertEqual(absent.event, "none")
        controller.reset()
        self.assertFalse(controller.active)


if __name__ == "__main__":
    unittest.main()
