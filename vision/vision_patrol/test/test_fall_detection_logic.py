import importlib.util
import unittest
from pathlib import Path


def load_logic_module():
    path = (
        Path(__file__).resolve().parents[1]
        / "vision_patrol"
        / "fall_detection_logic.py"
    )
    spec = importlib.util.spec_from_file_location("fall_detection_logic", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class FallDetectionLogicTest(unittest.TestCase):
    def setUp(self):
        self.logic = load_logic_module()

    def test_custom_fall_label_is_normalized(self):
        result = self.logic.classify_person_fall(
            "person lying", "person lying", [10, 20, 100, 80], 640, 480
        )
        self.assertEqual(result[:2], ("fallen_person", True))

    def test_wide_person_box_is_a_fall_candidate(self):
        result = self.logic.classify_person_fall(
            "person", "person", [10, 20, 210, 100], 640, 480
        )
        self.assertEqual(result[0], "fallen_person")
        self.assertTrue(result[1])

    def test_horizontal_pose_torso_is_a_fall_candidate(self):
        points = [[0, 0, 0] for _ in range(17)]
        points[5] = [100, 100, 0.9]
        points[6] = [105, 120, 0.9]
        points[11] = [200, 105, 0.9]
        points[12] = [205, 125, 0.9]
        result = self.logic.classify_person_fall(
            "person", "person", [80, 80, 230, 180], 640, 480,
            keypoints=points,
        )
        self.assertEqual(result[2], "horizontal_torso")
        self.assertTrue(result[1])

    def test_upright_person_is_not_fallen(self):
        result = self.logic.classify_person_fall(
            "person", "person", [100, 40, 180, 330], 640, 480
        )
        self.assertEqual(result[0], "person")
        self.assertFalse(result[1])


if __name__ == "__main__":
    unittest.main()
