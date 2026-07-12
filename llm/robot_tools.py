"""
机器人工具封装
==============
功能：
  - 封装车端ROS2接口，提供安全的任务控制能力
  - get_robot_status(): 查询当前任务状态
  - stop_robot(): 立即停车，进入安全停止状态
  - cancel_task(): 取消当前巡检任务并停车
  - reset_task(): 复位任务状态，使小车可以接收新任务
  - start_patrol(): 启动巡检任务

ROS2接口映射：
  - /task/control (Service): 任务控制接口
  - /task/request (Topic): 任务请求发布

注意：需要ROS2环境和icar_interfaces包
"""
import json
from typing import Optional, List, Dict, Any


class RobotTools:
    def __init__(self, node=None):
        self.node = node
        self.task_control_client = None
        self.task_request_publisher = None
        self._init_ros2()

    def _init_ros2(self):
        if self.node is None:
            return

        try:
            from icar_interfaces.srv import TaskControl
            from icar_interfaces.msg import TaskRequest
            from rclpy.qos import QoSProfile, ReliabilityPolicy

            qos = QoSProfile(depth=10, reliability=ReliabilityPolicy.RELIABLE)

            self.task_control_client = self.node.create_client(
                TaskControl, '/task/control'
            )

            self.task_request_publisher = self.node.create_publisher(
                TaskRequest, '/task/request', qos
            )

            self.node.get_logger().info("Robot tools initialized")

        except ImportError as e:
            if self.node:
                self.node.get_logger().warn(f"icar_interfaces not available: {e}")

    def call_task_control(self, action: str, reason: str, payload_json: str = "{}") -> dict:
        if self.task_control_client is None:
            return {"success": False, "message": "ROS2 node not initialized, cannot call /task/control"}

        from icar_interfaces.srv import TaskControl
        import rclpy

        req = TaskControl.Request()
        req.action = action
        req.reason = reason
        req.payload_json = payload_json

        if not self.task_control_client.wait_for_service(timeout_sec=2.0):
            return {"success": False, "message": "Service /task/control not available"}

        future = self.task_control_client.call_async(req)
        rclpy.spin_until_future_complete(self.node, future)

        try:
            response = future.result()
            return {
                "success": response.success,
                "message": response.message,
                "task_id": response.task_id,
                "status": response.status,
                "data_json": response.data_json
            }
        except Exception as e:
            return {"success": False, "message": f"Service call failed: {str(e)}"}

    def get_robot_status(self) -> dict:
        return self.call_task_control(
            action="get_status",
            reason="LLM status query",
            payload_json="{}"
        )

    def stop_robot(self, reason: str = "user requested emergency stop") -> dict:
        return self.call_task_control(
            action="stop",
            reason=reason,
            payload_json=json.dumps({"source": "llm"})
        )

    def cancel_task(self, reason: str = "user cancelled patrol") -> dict:
        return self.call_task_control(
            action="cancel",
            reason=reason,
            payload_json=json.dumps({"source": "llm"})
        )

    def reset_task(self, reason: str = "operator confirmed reset") -> dict:
        return self.call_task_control(
            action="reset",
            reason=reason,
            payload_json=json.dumps({"source": "llm"})
        )

    def start_patrol(self, route: List[str], user_text: str = "") -> dict:
        if self.task_request_publisher is None:
            return {"success": False, "message": "ROS2 node not initialized, cannot publish /task/request"}

        from icar_interfaces.msg import TaskRequest

        req = TaskRequest()
        req.task_type = "patrol"
        req.route = route
        req.params = json.dumps({
            "source": "llm",
            "user_text": user_text
        }, ensure_ascii=False)

        self.task_request_publisher.publish(req)

        return {
            "success": True,
            "message": f"Patrol task sent: {route}",
            "task_type": "patrol",
            "route": route
        }

    # ── 信息查询工具（读取节点缓存的最新数据）─────────────────

    def query_environment(self) -> dict:
        """查询环境传感器数据。"""
        if self.node and hasattr(self.node, '_latest_sensor'):
            data = self.node._latest_sensor
            if data:
                return {"success": True, "message": "environment data", "data": data}
        return {"success": False, "message": "no sensor data available", "data": {}}

    def query_vision(self) -> dict:
        """查询最近的视觉检测结果。"""
        if self.node and hasattr(self.node, '_latest_detections'):
            data = self.node._latest_detections
            if data:
                return {"success": True, "message": "vision data", "data": data}
        return {"success": False, "message": "no vision data available", "data": {}}

    def query_navigation(self) -> dict:
        """查询当前导航状态。"""
        if self.node and hasattr(self.node, '_latest_nav_status'):
            data = self.node._latest_nav_status
            if data:
                return {"success": True, "message": "navigation status", "data": data}
        return {"success": False, "message": "no navigation data available", "data": {}}

    def check_safety(self) -> dict:
        """查询障碍物状态和安全风险。"""
        if self.node and hasattr(self.node, '_latest_obstacle'):
            data = self.node._latest_obstacle
            if data:
                return {"success": True, "message": "safety status", "data": data}
        return {"success": False, "message": "no obstacle data available", "data": {}}

    TOOLS_DEF = [
        {
            "tool_name": "start_patrol",
            "description": "启动巡检任务，让小车按指定路线巡检",
            "parameters": {
                "route": {
                    "type": "array",
                    "items": {"type": "string"},
                    "required": True,
                    "description": "巡检点名称数组，如 ['A', 'B', 'C']"
                },
                "user_text": {
                    "type": "string",
                    "required": False,
                    "description": "原始用户输入文本"
                }
            }
        },
        {
            "tool_name": "get_robot_status",
            "description": "查询小车当前任务状态",
            "parameters": {}
        },
        {
            "tool_name": "stop_robot",
            "description": "立即停车，进入安全停止状态",
            "parameters": {
                "reason": {
                    "type": "string",
                    "required": False,
                    "description": "停车原因"
                }
            }
        },
        {
            "tool_name": "cancel_task",
            "description": "取消当前巡检任务并停车",
            "parameters": {
                "reason": {
                    "type": "string",
                    "required": False,
                    "description": "取消原因"
                }
            }
        },
        {
            "tool_name": "reset_task",
            "description": "复位任务状态，使小车可以接收新任务",
            "parameters": {
                "reason": {
                    "type": "string",
                    "required": False,
                    "description": "复位原因"
                }
            }
        },
        {
            "tool_name": "query_environment",
            "description": "查询环境传感器实时数据（温度/湿度/烟雾/PM2.5/光照/气压）",
            "parameters": {}
        },
        {
            "tool_name": "query_vision",
            "description": "查询最近的视觉检测结果（摄像头看到了什么目标）",
            "parameters": {}
        },
        {
            "tool_name": "query_navigation",
            "description": "查询当前导航状态、位置和进度",
            "parameters": {}
        },
        {
            "tool_name": "check_safety",
            "description": "查询障碍物状态和安全风险等级",
            "parameters": {}
        },
    ]