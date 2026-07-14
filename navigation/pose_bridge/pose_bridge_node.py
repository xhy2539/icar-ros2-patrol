#!/usr/bin/env python3
"""桥接 AMCL -> /pose

AMCL 输出: /amcl_pose (PoseWithCovarianceStamped)
系统需要: /pose (PoseStamped)

这个节点把 AMCL 的定位结果转成系统需要的格式。
"""
import rclpy
from geometry_msgs.msg import PoseStamped, PoseWithCovarianceStamped
from rclpy.node import Node


class PoseBridgeNode(Node):
    def __init__(self):
        super().__init__("pose_bridge_node")
        self.pub = self.create_publisher(PoseStamped, "/pose", 10)
        self.sub = self.create_subscription(
            PoseWithCovarianceStamped, "/amcl_pose", self._on_amcl_pose, 10
        )
        self.get_logger().info("pose_bridge: /amcl_pose → /pose")

    def _on_amcl_pose(self, msg: PoseWithCovarianceStamped):
        out = PoseStamped()
        out.header = msg.header
        out.pose = msg.pose.pose
        self.pub.publish(out)


def main():
    rclpy.init()
    node = PoseBridgeNode()
    try:
        rclpy.spin(node)
    except KeyboardInterrupt:
        pass
    finally:
        node.destroy_node()
        rclpy.shutdown()


if __name__ == "__main__":
    main()
