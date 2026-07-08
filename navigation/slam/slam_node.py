import sys
from pathlib import Path

import rclpy
from geometry_msgs.msg import PoseStamped
from nav_msgs.msg import OccupancyGrid
from rclpy.node import Node
from rclpy.qos import DurabilityPolicy, QoSProfile, ReliabilityPolicy
from std_msgs.msg import String
CURRENT_DIR = Path(__file__).resolve().parent
PARENT_DIR = CURRENT_DIR.parent
for path in (CURRENT_DIR, PARENT_DIR):
    if str(path) not in sys.path:
        sys.path.insert(0, str(path))

from navigation_utils import (
    interpolate_pose,
    load_checkpoints,
    load_map_metadata,
    parse_json_message,
    yaw_to_quaternion,
)


def parse_ascii_pgm(file_path: Path):
    tokens = []
    with file_path.open("r", encoding="ascii") as file:
        for line in file:
            line = line.strip()
            if not line or line.startswith("#"):
                continue
            tokens.extend(line.split())

    if len(tokens) < 4 or tokens[0] != "P2":
        raise ValueError(f"Unsupported PGM format in {file_path}")

    width = int(tokens[1])
    height = int(tokens[2])
    max_value = int(tokens[3])
    raw_values = [int(value) for value in tokens[4:]]
    if len(raw_values) != width * height:
        raise ValueError(f"PGM size mismatch in {file_path}")

    occupancy = []
    for pixel in raw_values:
        normalized = pixel / max_value
        if normalized >= 0.65:
            occupancy.append(100)
        elif normalized <= 0.2:
            occupancy.append(0)
        else:
            occupancy.append(-1)
    return width, height, occupancy


class SlamNode(Node):
    def __init__(self):
        super().__init__("slam_node")
        self.map_metadata = load_map_metadata()
        _, checkpoints = load_checkpoints()
        self.current_pose = dict(checkpoints.get("HOME", {"x": 0.0, "y": 0.0, "yaw": 0.0}))
        self.start_pose = dict(self.current_pose)
        self.target_pose = None
        self.nav_status = {"status": "IDLE", "progress": 0.0}

        map_yaml_path = self.map_metadata.get("map_yaml", "config/navigation/maps/mock_lab.yaml")
        self.map_yaml_file = (PARENT_DIR / map_yaml_path).resolve()
        self.pgm_file = self.map_yaml_file.parent / "mock_lab.pgm"

        width, height, occupancy = parse_ascii_pgm(self.pgm_file)
        self.map_width = width
        self.map_height = height
        self.map_occupancy = occupancy

        map_qos = QoSProfile(depth=1)
        map_qos.reliability = ReliabilityPolicy.RELIABLE
        map_qos.durability = DurabilityPolicy.TRANSIENT_LOCAL
        self.map_publisher = self.create_publisher(OccupancyGrid, "/map", map_qos)
        self.pose_publisher = self.create_publisher(PoseStamped, "/pose", 10)
        self.create_subscription(PoseStamped, "/goal_pose", self.on_goal_pose, 10)
        self.create_subscription(String, "/nav_status", self.on_nav_status, 10)

        self.create_timer(2.0, self.publish_map)
        self.create_timer(0.25, self.publish_pose)

        self.publish_map()
        self.get_logger().info("SLAM node started in mock data mode")

    def on_goal_pose(self, message: PoseStamped):
        self.start_pose = dict(self.current_pose)
        self.target_pose = {
            "x": float(message.pose.position.x),
            "y": float(message.pose.position.y),
            "yaw": 0.0,
        }

    def on_nav_status(self, message: String):
        payload = parse_json_message(message.data)
        if payload.get("current_goal"):
            self.target_pose = dict(payload["current_goal"])
        self.nav_status = payload

    def publish_map(self):
        map_message = OccupancyGrid()
        map_message.header.stamp = self.get_clock().now().to_msg()
        map_message.header.frame_id = self.map_metadata.get("frame_id", "map")
        map_message.info.resolution = float(self.map_metadata.get("resolution", 0.25))
        map_message.info.width = self.map_width
        map_message.info.height = self.map_height
        map_message.info.origin.position.x = float(self.map_metadata["origin"]["x"])
        map_message.info.origin.position.y = float(self.map_metadata["origin"]["y"])
        map_message.info.origin.position.z = 0.0
        origin_orientation = yaw_to_quaternion(float(self.map_metadata["origin"].get("yaw", 0.0)))
        map_message.info.origin.orientation.x = origin_orientation["x"]
        map_message.info.origin.orientation.y = origin_orientation["y"]
        map_message.info.origin.orientation.z = origin_orientation["z"]
        map_message.info.origin.orientation.w = origin_orientation["w"]
        map_message.data = self.map_occupancy
        self.map_publisher.publish(map_message)

    def publish_pose(self):
        status = self.nav_status.get("status", "IDLE")
        progress = float(self.nav_status.get("progress", 0.0))

        if self.target_pose and status == "NAVIGATING":
            self.current_pose = interpolate_pose(self.start_pose, self.target_pose, progress)
        elif self.target_pose and status == "ARRIVED":
            self.current_pose = dict(self.target_pose)
            self.start_pose = dict(self.current_pose)
        elif self.target_pose and status == "FAILED":
            self.current_pose = interpolate_pose(self.start_pose, self.target_pose, progress)
            self.start_pose = dict(self.current_pose)

        pose_message = PoseStamped()
        pose_message.header.stamp = self.get_clock().now().to_msg()
        pose_message.header.frame_id = self.map_metadata.get("frame_id", "map")
        pose_message.pose.position.x = self.current_pose["x"]
        pose_message.pose.position.y = self.current_pose["y"]
        pose_message.pose.position.z = 0.0
        orientation = yaw_to_quaternion(self.current_pose["yaw"])
        pose_message.pose.orientation.x = orientation["x"]
        pose_message.pose.orientation.y = orientation["y"]
        pose_message.pose.orientation.z = orientation["z"]
        pose_message.pose.orientation.w = orientation["w"]
        self.pose_publisher.publish(pose_message)


def main():
    rclpy.init()
    node = SlamNode()
    try:
        rclpy.spin(node)
    except KeyboardInterrupt:
        pass
    finally:
        node.destroy_node()
        rclpy.shutdown()


if __name__ == "__main__":
    main()
