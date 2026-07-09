import importlib.util
import math
import sys
import types
import unittest
from pathlib import Path


def install_ros_stubs():
    geometry_msgs = types.ModuleType("geometry_msgs")
    geometry_msgs_msg = types.ModuleType("geometry_msgs.msg")
    geometry_msgs_msg.Twist = type("Twist", (), {})
    geometry_msgs.msg = geometry_msgs_msg

    icar_interfaces = types.ModuleType("icar_interfaces")
    icar_interfaces_msg = types.ModuleType("icar_interfaces.msg")
    icar_interfaces_msg.ObstacleStatus = type("ObstacleStatus", (), {})
    icar_interfaces.msg = icar_interfaces_msg

    rclpy = types.ModuleType("rclpy")
    rclpy_node = types.ModuleType("rclpy.node")
    rclpy_node.Node = type("Node", (), {})
    rclpy.node = rclpy_node

    sensor_msgs = types.ModuleType("sensor_msgs")
    sensor_msgs_msg = types.ModuleType("sensor_msgs.msg")
    sensor_msgs_msg.LaserScan = type("LaserScan", (), {})
    sensor_msgs.msg = sensor_msgs_msg

    sys.modules.setdefault("geometry_msgs", geometry_msgs)
    sys.modules.setdefault("geometry_msgs.msg", geometry_msgs_msg)
    sys.modules.setdefault("icar_interfaces", icar_interfaces)
    sys.modules.setdefault("icar_interfaces.msg", icar_interfaces_msg)
    sys.modules.setdefault("rclpy", rclpy)
    sys.modules.setdefault("rclpy.node", rclpy_node)
    sys.modules.setdefault("sensor_msgs", sensor_msgs)
    sys.modules.setdefault("sensor_msgs.msg", sensor_msgs_msg)


def load_obstacle_module():
    install_ros_stubs()
    module_path = (
        Path(__file__).resolve().parents[1]
        / "obstacle_avoid"
        / "obstacle_avoid_node.py"
    )
    spec = importlib.util.spec_from_file_location("obstacle_avoid_node", module_path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class ObstacleScanLogicTest(unittest.TestCase):
    def setUp(self):
        self.module = load_obstacle_module()

    def classify(self, ranges, angle_min=-math.pi, angle_increment=math.radians(10)):
        return self.module.classify_front_scan(
            ranges=ranges,
            angle_min=angle_min,
            angle_increment=angle_increment,
            range_min=0.15,
            range_max=12.0,
        )

    def test_front_obstacle_at_035m_is_danger_stop(self):
        result = self.classify([2.0] * 16 + [0.35] + [2.0] * 20)

        self.assertTrue(result["is_obstacle"])
        self.assertAlmostEqual(result["min_distance"], 0.35)
        self.assertEqual(result["direction"], "front")
        self.assertEqual(result["risk_level"], "danger")
        self.assertEqual(result["action"], "stop")

    def test_front_obstacle_at_08m_is_warning_slow_down(self):
        result = self.classify([2.0] * 17 + [0.8] + [2.0] * 19)

        self.assertTrue(result["is_obstacle"])
        self.assertAlmostEqual(result["min_distance"], 0.8)
        self.assertEqual(result["risk_level"], "warning")
        self.assertEqual(result["action"], "slow_down")

    def test_front_clear_distance_is_safe_none(self):
        result = self.classify([1.5] * 37)

        self.assertFalse(result["is_obstacle"])
        self.assertAlmostEqual(result["min_distance"], 1.5)
        self.assertEqual(result["risk_level"], "safe")
        self.assertEqual(result["action"], "none")

    def test_side_obstacle_does_not_trigger_front_avoidance(self):
        result = self.classify([0.25] + [2.0] * 35 + [0.25])

        self.assertFalse(result["is_obstacle"])
        self.assertAlmostEqual(result["min_distance"], 2.0)
        self.assertEqual(result["risk_level"], "safe")
        self.assertEqual(result["action"], "none")

    def test_invalid_and_out_of_range_values_are_filtered(self):
        ranges = [2.0] * 37
        ranges[15] = float("nan")
        ranges[16] = float("inf")
        ranges[17] = 0.1
        ranges[18] = 20.0
        ranges[19] = 0.8

        result = self.classify(ranges)

        self.assertTrue(result["is_obstacle"])
        self.assertAlmostEqual(result["min_distance"], 0.8)
        self.assertEqual(result["risk_level"], "warning")
        self.assertEqual(result["action"], "slow_down")

    def test_no_valid_front_ranges_falls_back_to_safe_range_max(self):
        ranges = [2.0] * 37
        for index in range(15, 22):
            ranges[index] = float("nan")

        result = self.classify(ranges)

        self.assertFalse(result["is_obstacle"])
        self.assertAlmostEqual(result["min_distance"], 12.0)
        self.assertEqual(result["risk_level"], "safe")
        self.assertEqual(result["action"], "none")


if __name__ == "__main__":
    unittest.main()
