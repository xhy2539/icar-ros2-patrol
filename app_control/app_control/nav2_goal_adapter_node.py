"""Bridge project /goal_pose messages to Nav2's NavigateToPose action."""

from action_msgs.msg import GoalStatus
from geometry_msgs.msg import PoseStamped
from icar_interfaces.msg import NavStatus
from nav2_msgs.action import NavigateToPose
import rclpy
from rclpy.action import ActionClient
from rclpy.node import Node


class Nav2GoalAdapterNode(Node):
    def __init__(self) -> None:
        super().__init__("nav2_goal_adapter")
        self.declare_parameter("action_name", "/navigate_to_pose")
        self.declare_parameter("server_timeout_sec", 3.0)
        self._client = ActionClient(
            self,
            NavigateToPose,
            str(self.get_parameter("action_name").value),
        )
        self._status_pub = self.create_publisher(NavStatus, "/nav_status", 10)
        self.create_subscription(PoseStamped, "/goal_pose", self._on_goal, 10)
        self._generation = 0
        self._initial_distance = {}
        self.get_logger().info("Nav2 goal adapter ready: /goal_pose -> NavigateToPose")

    def _publish(self, status, progress, distance, message):
        output = NavStatus()
        output.status = str(status)
        output.progress = min(1.0, max(0.0, float(progress)))
        output.distance_remain = max(0.0, float(distance))
        output.message = str(message)
        self._status_pub.publish(output)

    def _on_goal(self, pose: PoseStamped) -> None:
        self._generation += 1
        generation = self._generation
        timeout = float(self.get_parameter("server_timeout_sec").value)
        if not self._client.wait_for_server(timeout_sec=timeout):
            self._publish("FAILED", 0.0, 0.0, "Nav2 action server unavailable")
            return

        goal = NavigateToPose.Goal()
        goal.pose = pose
        future = self._client.send_goal_async(
            goal,
            feedback_callback=lambda feedback, current=generation: self._on_feedback(
                feedback, current
            ),
        )
        future.add_done_callback(
            lambda result, current=generation: self._on_goal_response(result, current)
        )
        self._publish("NAVIGATING", 0.0, 0.0, "goal sent to Nav2")

    def _on_goal_response(self, future, generation: int) -> None:
        if generation != self._generation:
            return
        try:
            goal_handle = future.result()
        except Exception as exc:  # pylint: disable=broad-except
            self._publish("FAILED", 0.0, 0.0, f"Nav2 rejected goal: {exc}")
            return
        if not goal_handle.accepted:
            self._publish("FAILED", 0.0, 0.0, "Nav2 rejected goal")
            return
        result_future = goal_handle.get_result_async()
        result_future.add_done_callback(
            lambda result, current=generation: self._on_result(result, current)
        )

    def _on_feedback(self, feedback_message, generation: int) -> None:
        if generation != self._generation:
            return
        feedback = feedback_message.feedback
        distance = max(0.0, float(feedback.distance_remaining))
        initial = max(distance, self._initial_distance.get(generation, 0.0))
        self._initial_distance[generation] = initial
        progress = 0.0 if initial <= 0.001 else 1.0 - distance / initial
        self._publish("NAVIGATING", progress, distance, "Nav2 is following path")

    def _on_result(self, future, generation: int) -> None:
        # A newer replan goal supersedes the previous result. Ignoring the old
        # cancellation prevents a deliberate replan from failing the task.
        if generation != self._generation:
            return
        try:
            status = int(future.result().status)
        except Exception as exc:  # pylint: disable=broad-except
            self._publish("FAILED", 0.0, 0.0, f"Nav2 result error: {exc}")
            return
        if status == GoalStatus.STATUS_SUCCEEDED:
            self._publish("ARRIVED", 1.0, 0.0, "Nav2 goal reached")
        else:
            self._publish("FAILED", 0.99, 0.0, f"Nav2 goal ended with status {status}")


def main(args=None) -> None:
    rclpy.init(args=args)
    node = Nav2GoalAdapterNode()
    try:
        rclpy.spin(node)
    except KeyboardInterrupt:
        pass
    finally:
        node.destroy_node()
        rclpy.shutdown()


if __name__ == "__main__":
    main()
