#!/usr/bin/env python3
"""Nav2 → /nav_status bridge node.

Replaces navigation_node when the real Nav2 navigation stack is available.

Modes:
  --mode mock   Simulates navigation progress (same as navigation_node mock).
                Use for testing without Nav2.
  --mode real   Connects to Nav2 NavigateToPose action server, translates
                action feedback into project NavStatus messages on /nav_status.

Interface (unchanged from navigation_node):
  Subscriptions: /goal_pose  (PoseStamped)
  Publications:  /nav_status (icar_interfaces/NavStatus)
"""

import argparse
import math
import sys
import time
from pathlib import Path

import rclpy
from geometry_msgs.msg import PoseStamped
from icar_interfaces.msg import NavStatus
from rclpy.node import Node

# --- Nav2 action interface (available when nav2_msgs is installed) ---
try:
    from nav2_msgs.action import NavigateToPose
    from rclpy.action import ActionClient

    HAVE_NAV2 = True
except ImportError:
    NavigateToPose = None
    ActionClient = None
    HAVE_NAV2 = False

CURRENT_DIR = Path(__file__).resolve().parent
PARENT_DIR = CURRENT_DIR.parent
for path in (CURRENT_DIR, PARENT_DIR):
    if str(path) not in sys.path:
        sys.path.insert(0, str(path))

from navigation_utils import distance_between, load_checkpoints, quaternion_to_yaw

# Seconds to hold ARRIVED / FAILED before resetting to IDLE
HOLD_RESULT_SEC = 2.0
# Max time (seconds) to wait for Nav2 to accept a goal before giving up
NAV2_GOAL_TIMEOUT_SEC = 10.0


def _clamp(value, minimum, maximum):
    return max(minimum, min(maximum, value))


class Nav2BridgeNode(Node):
    """Bridge between Nav2 navigation stack and project NavStatus protocol."""

    def __init__(self, mode: str):
        super().__init__("nav2_bridge_node")
        self.mode = mode

        # --- state ---
        self.current_pose = {"x": 0.0, "y": 0.0, "yaw": 0.0}
        self.goal_start_pose = dict(self.current_pose)
        self.active_goal = None
        self.goal_start_time = None
        self.result_time = None
        self.result_status = None
        self.result_message = ""
        self.last_status_signature = None

        # --- Nav2 action client (real mode only) ---
        self._nav2_client = None
        self._nav2_goal_handle = None
        self._nav2_feedback = None

        if self.mode == "real" and HAVE_NAV2:
            self._nav2_client = ActionClient(self, NavigateToPose, "navigate_to_pose")
            self.get_logger().info("Nav2 action client ready")
        elif self.mode == "real" and not HAVE_NAV2:
            self.get_logger().warning(
                "nav2_msgs not available — real mode will fall back to "
                "NAVIGATING placeholder. Install nav2_msgs for full support."
            )

        # --- ROS2 interface ---
        self.status_publisher = self.create_publisher(NavStatus, "/nav_status", 10)
        self.create_subscription(PoseStamped, "/goal_pose", self._on_goal_pose, 10)
        self.create_subscription(PoseStamped, "/pose", self._on_pose, 10)
        self.create_timer(0.5, self._on_timer)

        self.get_logger().info(f"Nav2 bridge node started in {self.mode} mode")

    # ------------------------------------------------------------------
    # Goal management
    # ------------------------------------------------------------------

    def _on_goal_pose(self, message: PoseStamped):
        self.active_goal = {
            "x": float(message.pose.position.x),
            "y": float(message.pose.position.y),
            "yaw": quaternion_to_yaw(
                float(message.pose.orientation.z),
                float(message.pose.orientation.w),
            ),
        }
        self.goal_start_pose = dict(self.current_pose)
        self.goal_start_time = time.monotonic()
        self.result_time = None
        self.result_status = None
        self.result_message = ""

        total_distance = distance_between(self.goal_start_pose, self.active_goal)
        self.get_logger().info(
            f"Received goal ({self.active_goal['x']:.2f}, "
            f"{self.active_goal['y']:.2f}) — distance {total_distance:.2f}m"
        )

        # Send to Nav2 if in real mode
        if self.mode == "real" and self._nav2_client is not None:
            self._send_nav2_goal()

    def _send_nav2_goal(self):
        """Send the active goal to Nav2 NavigateToPose action server."""
        if self._nav2_client is None:
            return

        goal_msg = NavigateToPose.Goal()
        goal_msg.pose.header.stamp = self.get_clock().now().to_msg()
        goal_msg.pose.header.frame_id = "map"
        goal_msg.pose.pose.position.x = self.active_goal["x"]
        goal_msg.pose.pose.position.y = self.active_goal["y"]
        goal_msg.pose.pose.position.z = 0.0
        # orientation from active goal yaw
        half_yaw = self.active_goal["yaw"] / 2.0
        goal_msg.pose.pose.orientation.z = math.sin(half_yaw)
        goal_msg.pose.pose.orientation.w = math.cos(half_yaw)

        self.get_logger().info("Sending goal to Nav2 NavigateToPose...")
        self._nav2_feedback = None
        self._nav2_goal_handle = None

        send_goal_future = self._nav2_client.send_goal_async(
            goal_msg, feedback_callback=self._on_nav2_feedback
        )
        send_goal_future.add_done_callback(self._on_nav2_goal_response)

    def _on_nav2_goal_response(self, future):
        try:
            self._nav2_goal_handle = future.result()
        except Exception as exc:
            self.get_logger().error(f"Nav2 goal rejected: {exc}")
            self._finish_goal("FAILED", f"Nav2 rejected goal: {exc}", 0.0)
            return

        if not self._nav2_goal_handle.accepted:
            self.get_logger().error("Nav2 goal not accepted")
            self._finish_goal("FAILED", "Nav2 goal not accepted", 0.0)
            return

        self.get_logger().info("Nav2 goal accepted — navigating")
        result_future = self._nav2_goal_handle.get_result_async()
        result_future.add_done_callback(self._on_nav2_result)

    def _on_nav2_feedback(self, feedback_msg):
        self._nav2_feedback = feedback_msg.feedback

    def _on_nav2_result(self, future):
        try:
            result = future.result()
        except Exception as exc:
            self.get_logger().error(f"Nav2 result error: {exc}")
            self._finish_goal("FAILED", f"Nav2 error: {exc}", 0.0)
            return

        nav2_status = result.status
        if nav2_status == 4:  # SUCCEEDED
            self._finish_goal("ARRIVED", "Nav2 navigation succeeded", 1.0)
        else:
            self._finish_goal("FAILED", f"Nav2 status={nav2_status}", 0.0)

    # ------------------------------------------------------------------
    # Pose tracking
    # ------------------------------------------------------------------

    def _on_pose(self, message: PoseStamped):
        self.current_pose = {
            "x": float(message.pose.position.x),
            "y": float(message.pose.position.y),
            "yaw": quaternion_to_yaw(
                float(message.pose.orientation.z),
                float(message.pose.orientation.w),
            ),
        }

    # ------------------------------------------------------------------
    # Status publishing
    # ------------------------------------------------------------------

    def _publish_status(self, status: str, progress: float,
                        distance_remain: float, message_text: str):
        signature = (
            status,
            round(progress, 3),
            round(distance_remain, 3),
            message_text,
        )
        if signature == self.last_status_signature:
            return
        ros_msg = NavStatus()
        ros_msg.status = status
        ros_msg.progress = round(progress, 3)
        ros_msg.distance_remain = round(distance_remain, 3)
        ros_msg.message = message_text
        self.status_publisher.publish(ros_msg)
        self.last_status_signature = signature

    def _finish_goal(self, status: str, message_text: str, progress: float):
        self.result_status = status
        self.result_message = message_text
        self.result_time = time.monotonic()
        if self.active_goal and status == "ARRIVED":
            self.current_pose = dict(self.active_goal)

    # ------------------------------------------------------------------
    # Main loop
    # ------------------------------------------------------------------

    def _on_timer(self):
        # ---- idle ----
        if not self.active_goal and not self.result_status:
            self._publish_status("IDLE", 0.0, 0.0, "waiting for /goal_pose")
            return

        # ---- hold result for a moment ----
        if self.result_status:
            if time.monotonic() - self.result_time > HOLD_RESULT_SEC:
                self.active_goal = None
                self.result_status = None
                self.result_message = ""
                self.goal_start_time = None
                self._publish_status("IDLE", 0.0, 0.0, "ready for next goal")
            else:
                progress = 1.0 if self.result_status == "ARRIVED" else 0.99
                self._publish_status(
                    self.result_status, progress, 0.0, self.result_message
                )
            return

        # ---- active navigation ----
        total_distance = distance_between(self.goal_start_pose, self.active_goal)

        if self.mode == "real" and HAVE_NAV2 and self._nav2_feedback is not None:
            # Use real Nav2 feedback
            fb = self._nav2_feedback
            distance_remain = float(fb.distance_remaining)
            progress = _clamp(
                1.0 - (distance_remain / max(total_distance, 0.001)), 0.0, 0.99
            )
            self._publish_status(
                "NAVIGATING", progress, distance_remain,
                "Nav2 navigating",
            )
            return

        if self.mode == "real":
            # Real mode without Nav2 feedback — hold at NAVIGATING
            elapsed = time.monotonic() - self.goal_start_time
            # Cap progress; Nav2 feedback will take over once available
            progress = min(elapsed / 30.0, 0.95)
            self._publish_status(
                "NAVIGATING", progress, total_distance * (1.0 - progress),
                "waiting for Nav2 navigation feedback",
            )
            return

        # ---- mock mode ----
        elapsed = time.monotonic() - self.goal_start_time
        duration_sec = 8.0
        progress = _clamp(elapsed / duration_sec, 0.0, 1.0)
        distance_remain = total_distance * (1.0 - progress)

        if progress >= 1.0:
            self._finish_goal("ARRIVED", "mock goal reached", 1.0)
            self._publish_status("ARRIVED", 1.0, 0.0, "mock goal reached")
            return

        self._publish_status(
            "NAVIGATING", progress, distance_remain, "mock navigation in progress"
        )


# ------------------------------------------------------------------
# Entry point
# ------------------------------------------------------------------

def main():
    parser = argparse.ArgumentParser(
        description="Nav2 bridge node — translates Nav2 feedback to /nav_status"
    )
    parser.add_argument(
        "--mode",
        choices=["mock", "real"],
        default="mock",
        help="mock simulates results; real connects to Nav2 action server",
    )
    args = parser.parse_args()

    rclpy.init()
    node = Nav2BridgeNode(args.mode)
    try:
        rclpy.spin(node)
    except KeyboardInterrupt:
        pass
    finally:
        node.destroy_node()
        rclpy.shutdown()


if __name__ == "__main__":
    main()
