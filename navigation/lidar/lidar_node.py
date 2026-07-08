import math
import sys
from pathlib import Path

import rclpy
from rclpy.node import Node
from sensor_msgs.msg import LaserScan
from std_msgs.msg import String

CURRENT_DIR = Path(__file__).resolve().parent
PARENT_DIR = CURRENT_DIR.parent
for path in (CURRENT_DIR, PARENT_DIR):
    if str(path) not in sys.path:
        sys.path.insert(0, str(path))

from navigation_utils import parse_json_message


class LidarNode(Node):
    def __init__(self):
        super().__init__("lidar_node")
        self.current_obstacle = {
            "is_obstacle": False,
            "min_distance": 2.5,
            "direction": "front",
        }
        self.publisher = self.create_publisher(LaserScan, "/scan", 10)
        self.create_subscription(String, "/obstacle_status", self.on_obstacle_status, 10)
        self.create_timer(0.2, self.publish_scan)
        self.get_logger().info("Lidar node started in mock data mode")

    def on_obstacle_status(self, message: String):
        self.current_obstacle = parse_json_message(message.data)

    def publish_scan(self):
        sample_count = 360
        scan = LaserScan()
        scan.header.stamp = self.get_clock().now().to_msg()
        scan.header.frame_id = "laser"
        scan.angle_min = -math.pi
        scan.angle_max = math.pi
        scan.angle_increment = (2.0 * math.pi) / sample_count
        scan.time_increment = 0.0
        scan.scan_time = 0.2
        scan.range_min = 0.12
        scan.range_max = 8.0

        ranges = [2.5] * sample_count
        if self.current_obstacle.get("is_obstacle"):
            front_distance = max(0.15, float(self.current_obstacle.get("min_distance", 0.8)))
            for offset in range(-15, 16):
                index = (180 + offset) % sample_count
                ranges[index] = front_distance
        scan.ranges = ranges
        scan.intensities = [100.0] * sample_count
        self.publisher.publish(scan)


def main():
    rclpy.init()
    node = LidarNode()
    try:
        rclpy.spin(node)
    except KeyboardInterrupt:
        pass
    finally:
        node.destroy_node()
        rclpy.shutdown()


if __name__ == "__main__":
    main()
