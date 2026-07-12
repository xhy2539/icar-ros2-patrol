"""
LLM Gateway Node - LLM模块主入口
=================================
功能：
  - 将用户自然语言指令通过DeepSeek API转换为结构化任务
  - 支持两种模式：
    1. 命令解析模式：解析为move/vision/complex/query/system类型的JSON命令
    2. 工具调用模式：调用车端安全接口（start_patrol/get_robot_status/stop_robot/cancel_task/reset_task）
  - 集成ROS2接口，订阅任务日志、状态、传感器数据
  - 发布结构化命令到/llm/command

前置条件：
  - 设置环境变量 DEEPSEEK_API_KEY
  - 或创建 .env 文件（参考 .env.example）

使用方式：
  python llm_gateway_node.py              # 命令解析模式
  python llm_gateway_node.py --tool       # 工具调用模式
  python llm_gateway_node.py --ros2       # ROS2模式
  python llm_gateway_node.py --ros2 --tool # ROS2+工具调用模式
"""
import os
import sys
import json
import argparse
from typing import Optional, Dict, Any

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

try:
    import rclpy
    from rclpy.node import Node
    from rclpy.qos import QoSProfile, ReliabilityPolicy
    from std_msgs.msg import String as ROSString
    HAS_ROS2 = True
except ImportError:
    HAS_ROS2 = False
    ROSString = None

from json_protocol import TaskCommand, extract_json_from_response, create_clarify_command
from deepseek_client import DeepSeekClient
from robot_tools import RobotTools


class LLMGatewayNode:
    def __init__(self, tool_mode: bool = False):
        self.tool_mode = tool_mode
        self.client = DeepSeekClient()
        
        self.task_logs = []
        self.is_running = False
        self.node = None
        self.robot_tools = None
        self.current_status = "PENDING"
        self.command_pub = None

    def parse_task(self, user_input: str) -> dict:
        try:
            response = self.client.parse_command(user_input)
            json_str = extract_json_from_response(response)
            command = TaskCommand.from_json(json_str)
            
            if command.is_valid():
                return {
                    "success": True,
                    "command": command.dict(),
                    "request_id": command.request_id,
                    "message": "Command parsed successfully"
                }
            else:
                return {
                    "success": False,
                    "error": "Invalid command format",
                    "raw_response": response
                }

        except Exception as e:
            fallback_cmd = create_clarify_command(f"指令解析失败: {str(e)}")
            return {
                "success": True,
                "command": fallback_cmd.dict(),
                "request_id": fallback_cmd.request_id,
                "message": f"Fallback due to error: {str(e)}"
            }

    def parse_tool_call(self, user_input: str) -> dict:
        try:
            response = self.client.parse_tool_call(user_input)
            json_str = extract_json_from_response(response)
            tool_call = json.loads(json_str)
            
            if "tool_name" in tool_call:
                return {
                    "success": True,
                    "tool_name": tool_call["tool_name"],
                    "arguments": tool_call.get("arguments", {}),
                    "message": "Tool call parsed successfully"
                }
            else:
                return {
                    "success": False,
                    "error": "Invalid tool call format",
                    "raw_response": response
                }

        except Exception as e:
            return {
                "success": True,
                "tool_name": "get_robot_status",
                "arguments": {},
                "message": f"Fallback due to error: {str(e)}"
            }

    def execute_tool_call(self, tool_name: str, arguments: Dict[str, Any]) -> dict:
        if self.robot_tools is None:
            self.robot_tools = RobotTools(self.node)

        tool_map = {
            "start_patrol": self.robot_tools.start_patrol,
            "get_robot_status": self.robot_tools.get_robot_status,
            "stop_robot": self.robot_tools.stop_robot,
            "cancel_task": self.robot_tools.cancel_task,
            "reset_task": self.robot_tools.reset_task,
            "send_command": self._execute_send_command,
        }

        if tool_name not in tool_map:
            return {"success": False, "tool_name": tool_name, "message": f"Unknown tool: {tool_name}"}

        try:
            result = tool_map[tool_name](**arguments)
            result["tool_name"] = tool_name
            
            if tool_name == "get_robot_status" and result.get("success"):
                try:
                    data = json.loads(result.get("data_json", "{}"))
                    self.current_status = data.get("status", result.get("status", "PENDING"))
                except:
                    self.current_status = result.get("status", "PENDING")

            return result
        except Exception as e:
            return {"success": False, "tool_name": tool_name, "message": f"Tool execution failed: {str(e)}"}

    def _execute_send_command(self, type: str, payload: Dict[str, Any]) -> dict:
        cmd = TaskCommand(
            type=type,
            payload=payload,
            mode="single",
            priority=5,
            timeout=30
        )

        if cmd.is_valid():
            cmd_json = json.dumps(cmd.dict(), ensure_ascii=False)
            
            if self.command_pub and ROSString:
                cmd_msg = ROSString()
                cmd_msg.data = cmd_json
                self.command_pub.publish(cmd_msg)

            return {
                "success": True,
                "message": f"Command sent: {type} -> {payload.get('command', payload.get('operation', ''))}",
                "type": type,
                "payload": payload,
                "command_json": cmd_json
            }
        else:
            return {
                "success": False,
                "message": f"Invalid command: {type}"
            }

    def process_user_input(self, user_input: str) -> dict:
        if self.tool_mode:
            parsed = self.parse_tool_call(user_input)
            
            if not parsed.get("success"):
                return parsed

            tool_name = parsed["tool_name"]
            arguments = parsed["arguments"]

            if tool_name == "get_robot_status":
                result = self.execute_tool_call("get_robot_status", {})
                
                if result.get("success") and self.current_status == "PENDING":
                    if "巡检" in user_input or "巡逻" in user_input:
                        import re
                        route_match = re.findall(r'([A-Za-z])', user_input)
                        route = route_match if route_match else ["A", "B", "C"]
                        patrol_result = self.execute_tool_call("start_patrol", {
                            "route": route,
                            "user_text": user_input
                        })
                        return {
                            "success": True,
                            "tool_name": "start_patrol",
                            "route": route,
                            "result": patrol_result,
                            "message": f"当前状态为PENDING，已启动巡检任务: {route}"
                        }
                    return result
                return result

            return self.execute_tool_call(tool_name, arguments)

        else:
            return self.parse_task(user_input)

    def generate_report(self, task_log: Optional[str] = None) -> dict:
        try:
            log_content = task_log or "\n".join(self.task_logs)
            report = self.client.generate_report(log_content)
            
            return {
                "success": True,
                "report": report,
                "message": "Report generated successfully"
            }

        except Exception as e:
            return {
                "success": False,
                "error": str(e),
                "report": f"报告生成失败: {str(e)}"
            }

    def add_task_log(self, log_entry: str):
        self.task_logs.append(log_entry)
        if len(self.task_logs) > 1000:
            self.task_logs = self.task_logs[-500:]

    def run_standalone(self):
        print("=" * 50)
        print("LLM Gateway Node (Standalone Mode)")
        print("=" * 50)
        print("DeepSeek API: Real")
        print(f"Mode: {'Tool Call' if self.tool_mode else 'Command Parse'}")
        print("Commands: report, logs, exit")
        print("=" * 50)

        self.is_running = True
        while self.is_running:
            try:
                user_input = input("\n>>> ").strip()
                
                if not user_input:
                    continue
                
                if user_input.lower() == "exit":
                    self.is_running = False
                    print("Exiting...")
                    break
                
                if user_input.lower() == "logs":
                    print("\n--- Task Logs ---")
                    for i, log in enumerate(self.task_logs[-10:], 1):
                        print(f"{i}. {log}")
                    print("----------------")
                    continue
                
                if user_input.lower() == "report":
                    result = self.generate_report()
                    print("\n--- Generated Report ---")
                    print(result.get("report", "No report available"))
                    print("-----------------------")
                    continue

                result = self.process_user_input(user_input)
                print("\n--- Result ---")
                print(json.dumps(result, indent=2, ensure_ascii=False))
                print("-------------")

                if result.get("success"):
                    if self.tool_mode and "tool_name" in result:
                        self.add_task_log(f"User: {user_input} -> Tool: {result['tool_name']}")
                    elif "command" in result:
                        self.add_task_log(f"User: {user_input} -> Type: {result['command']['type']}")

            except KeyboardInterrupt:
                self.is_running = False
                print("\nExiting...")
                break

    def run_ros2(self):
        if not HAS_ROS2:
            print("ROS2 not available, running in standalone mode")
            self.run_standalone()
            return

        rclpy.init()
        self.node = Node('llm_gateway_node')

        qos = QoSProfile(depth=10, reliability=ReliabilityPolicy.RELIABLE)

        self.robot_tools = RobotTools(self.node)

        self.task_log_sub = self.node.create_subscription(
            ROSString,
            '/task/log',
            self._task_log_callback,
            qos
        )

        self.task_status_sub = self.node.create_subscription(
            ROSString,
            '/task/status',
            self._task_status_callback,
            qos
        )

        self.sensor_data_sub = self.node.create_subscription(
            ROSString,
            '/sensor/env_data',
            self._sensor_data_callback,
            qos
        )

        self.command_pub = self.node.create_publisher(
            ROSString,
            '/llm/command',
            qos
        )

        self.node.get_logger().info("LLM Gateway Node started")
        self.node.get_logger().info("Using Real DeepSeek API")
        self.node.get_logger().info(f"Mode: {'Tool Call' if self.tool_mode else 'Command Parse'}")

        try:
            rclpy.spin(self.node)
        except KeyboardInterrupt:
            self.node.get_logger().info("LLM Gateway Node stopping")
        finally:
            self.node.destroy_node()
            rclpy.shutdown()

    def _task_log_callback(self, msg):
        log_entry = msg.data
        self.add_task_log(log_entry)
        self.node.get_logger().debug(f"Task log received: {log_entry[:50]}...")

    def _task_status_callback(self, msg):
        status_data = msg.data
        self.node.get_logger().debug(f"Task status received: {status_data[:50]}...")
        try:
            data = json.loads(status_data)
            self.current_status = data.get("status", "PENDING")
        except:
            pass

    def _sensor_data_callback(self, msg):
        sensor_data = msg.data
        self.node.get_logger().debug(f"Sensor data received: {sensor_data[:50]}...")


def main():
    parser = argparse.ArgumentParser(description='LLM Gateway Node')
    parser.add_argument('--ros2', action='store_true', help='Run as ROS2 node')
    parser.add_argument('--tool', action='store_true', help='Enable tool call mode (safe task control)')
    args = parser.parse_args()

    gateway = LLMGatewayNode(tool_mode=args.tool)

    if args.ros2:
        gateway.run_ros2()
    else:
        gateway.run_standalone()


if __name__ == '__main__':
    main()