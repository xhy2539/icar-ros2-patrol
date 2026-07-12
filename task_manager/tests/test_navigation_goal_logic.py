import importlib.util
import unittest
from pathlib import Path


def load_goal_module():
    module_path = (
        Path(__file__).resolve().parents[1]
        / "task_manager"
        / "navigation_goal_logic.py"
    )
    spec = importlib.util.spec_from_file_location("navigation_goal_logic", module_path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class NavigationGoalLogicTest(unittest.TestCase):
    def setUp(self):
        self.logic = load_goal_module()
        self.checkpoints = {
            "A": {"x": 0.5, "y": 0.0, "yaw": 0.0},
            "B": {"x": 1.25, "y": 0.75, "yaw": 1.57},
            "C": {"x": 0.25, "y": 1.5, "yaw": 3.14},
        }

    def test_route_abc_resolves_to_ordered_goals(self):
        goals = self.logic.resolve_route_goals(["A", "B", "C"], self.checkpoints)

        self.assertEqual([goal.name for goal in goals], ["A", "B", "C"])
        self.assertAlmostEqual(goals[0].x, 0.5)
        self.assertAlmostEqual(goals[1].y, 0.75)
        self.assertAlmostEqual(goals[2].yaw, 3.14)

    def test_unknown_checkpoint_is_reported(self):
        with self.assertRaises(self.logic.UnknownCheckpointError) as context:
            self.logic.resolve_route_goals(["A", "Z"], self.checkpoints)

        self.assertEqual(context.exception.name, "Z")

    def test_goal_quaternion_uses_yaw(self):
        goal = self.logic.resolve_route_goals(["B"], self.checkpoints)[0]
        payload = self.logic.goal_to_pose_payload(goal)

        self.assertEqual(payload["frame_id"], "map")
        self.assertAlmostEqual(payload["position"]["x"], 1.25)
        self.assertAlmostEqual(payload["orientation"]["z"], 0.7068251811, places=6)
        self.assertAlmostEqual(payload["orientation"]["w"], 0.7073882691, places=6)


if __name__ == "__main__":
    unittest.main()
