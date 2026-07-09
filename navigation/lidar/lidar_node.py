import rclpy
from rclpy.duration import Duration
from rclpy.node import Node
from sensor_msgs.msg import LaserScan


class LidarNode(Node):
    def __init__(self):
        super().__init__("lidar_node")
        self.last_scan_time = None
        self.last_frame_id = ""
        self.last_range_count = 0
        self.scan_count = 0
        self.real_scan_logged = False
        self.scan_ready = False
        self.waiting_logged = False
        self.timeout_logged = False
        self.scan_timeout = Duration(seconds=2.0)

        self.create_subscription(LaserScan, "/scan", self.on_scan, 10)
        self.create_timer(1.0, self.check_scan_health)
        self.get_logger().info("Lidar node started in formal mode, waiting for real /scan")

    def on_scan(self, message: LaserScan):
        self.last_scan_time = self.get_clock().now()
        self.last_frame_id = message.header.frame_id
        self.last_range_count = len(message.ranges)
        self.scan_count += 1

        if not self.real_scan_logged:
            self.get_logger().info(
                "Real /scan connected: frame_id=%s, sample_count=%d"
                % (self.last_frame_id or "<empty>", self.last_range_count)
            )
            self.real_scan_logged = True
        self.scan_ready = True
        self.waiting_logged = False
        self.timeout_logged = False

    def check_scan_health(self):
        if self.last_scan_time is None:
            if self.scan_ready:
                self.scan_ready = False
            if not self.waiting_logged:
                self.get_logger().warning("Waiting for real /scan from the vehicle lidar chain")
                self.waiting_logged = True
            return

        elapsed = self.get_clock().now() - self.last_scan_time
        if elapsed > self.scan_timeout:
            self.scan_ready = False
            if not self.timeout_logged:
                self.get_logger().warning(
                    "Real /scan timed out: last frame_id=%s, sample_count=%d"
                    % (self.last_frame_id or "<empty>", self.last_range_count)
                )
                self.timeout_logged = True
            return

        if not self.scan_ready:
            age_seconds = elapsed.nanoseconds / 1_000_000_000.0
            self.get_logger().info(
                "Real /scan healthy again: total_messages=%d, last_frame_id=%s, sample_count=%d, age=%.2fs"
                % (
                    self.scan_count,
                    self.last_frame_id or "<empty>",
                    self.last_range_count,
                    age_seconds,
                )
            )
            self.scan_ready = True
        self.waiting_logged = False
        self.timeout_logged = False


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
