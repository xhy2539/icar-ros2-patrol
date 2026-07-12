#!/usr/bin/env python3
"""
task_manager_node.py — ICAR Patrol 任务调度核心节点

巡检状态机:
  PENDING → RUNNING → NAVIGATING → CHECKPOINT → DETECTING → COLLECTING
                                                              │
                                                    ┌─────────┴──────────┐
                                                    ▼                    ▼
                                              COMPLETED              FAILED
                                              (正常结束)            (异常终止)

安全约束:
  - LLM 不直接发布 /cmd_vel
  - 紧急情况下 obstacle_avoid_node 和 task_manager_node 可 override /cmd_vel
  - 遇到障碍物/烟雾异常/通信异常/人工停止时，小车进入安全状态

负责人: 熊浩宇
"""

import json
import time
import uuid
from enum import Enum

import rclpy
from rclpy.node import Node
from builtin_interfaces.msg import Time as RosTime

# 自定义消息接口
from icar_interfaces.msg import (
    TaskRequest,
    TaskStatus,
    TaskLog,
    NavStatus,
    ObstacleStatus,
    DetectionArray,
    EnvData,
    SensorAlert,
)
from task_manager.navigation_goal_logic import (
    UnknownCheckpointError,
    goal_to_pose_payload,
    load_navigation_checkpoints,
    resolve_route_goals,
)
from icar_interfaces.srv import TaskControl
from task_manager.task_control_logic import plan_task_control


# ---------------------------------------------------------------------------
# 状态机定义
# ---------------------------------------------------------------------------

class PatrolState(Enum):
    PENDING = "PENDING"           # 等待任务
    RUNNING = "RUNNING"           # 任务已接收，准备执行
    NAVIGATING = "NAVIGATING"     # 前往巡检点
    CHECKPOINT = "CHECKPOINT"     # 到达巡检点，记录打卡
    DETECTING = "DETECTING"       # 视觉检测
    COLLECTING = "COLLECTING"     # 传感器采集
    COMPLETED = "COMPLETED"       # 任务正常结束
    FAILED = "FAILED"             # 任务异常终止
    CANCELLED = "CANCELLED"       # 人工取消


# 允许的状态转换
ALLOWED_TRANSITIONS = {
    PatrolState.PENDING:    [PatrolState.RUNNING, PatrolState.CANCELLED],
    PatrolState.RUNNING:    [PatrolState.NAVIGATING, PatrolState.CANCELLED, PatrolState.FAILED],
    PatrolState.NAVIGATING: [PatrolState.CHECKPOINT, PatrolState.CANCELLED, PatrolState.FAILED],
    PatrolState.CHECKPOINT: [PatrolState.DETECTING, PatrolState.COLLECTING, PatrolState.CANCELLED, PatrolState.FAILED],
    PatrolState.DETECTING:  [PatrolState.COLLECTING, PatrolState.CANCELLED, PatrolState.FAILED],
    PatrolState.COLLECTING: [PatrolState.NAVIGATING, PatrolState.COMPLETED, PatrolState.CANCELLED, PatrolState.FAILED],
    PatrolState.COMPLETED:  [PatrolState.PENDING],   # 允许复位接受新任务
    PatrolState.FAILED:     [PatrolState.PENDING],   # 允许复位接受新任务
    PatrolState.CANCELLED:  [PatrolState.PENDING],   # 允许复位接受新任务
}


# 异常阈值（与文档 IF-07 对齐）
EMERGENCY_THRESHOLDS = {
    "temperature": 50.0,    # ℃, >50 触发 ERROR
    "smoke": 100.0,         # ppm, >100 触发 ERROR
    "pm25": 150.0,          # μg/m³, >150 触发 WARN
    "humidity": 20.0,       # %, <20 触发 WARN (低湿)
}

OBSTACLE_DANGER_DISTANCE = 0.3   # 米, ≤0.3 紧急停止
OBSTACLE_WARN_DISTANCE = 0.5     # 米, ≤0.5 减速观察


# ---------------------------------------------------------------------------
# TaskManagerNode
# ---------------------------------------------------------------------------

class TaskManagerNode(Node):
    """任务调度核心节点"""

    def __init__(self):
        super().__init__('task_manager_node')

        # ---- 状态 ----
        self.state = PatrolState.PENDING
        self.current_task_id = ""
        self.route = []                # ["A", "B", "C"]
        self.route_index = 0           # 当前巡检点索引
        self.checkpoint_data = {}      # 打卡数据缓存
        self.last_env_data = None      # 最新传感器数据
        self.last_detections = None    # 最新检测结果
        self.emergency_stop_active = False
        self.checkpoints = load_navigation_checkpoints()
        self.route_goals = []
        self.goal_sent_for_index = None

        # ---- QoS ----
        reliable_qos = QoSProfile(
            depth=10,
            reliability=ReliabilityPolicy.RELIABLE,
        )
        best_effort_qos = QoSProfile(
            depth=10,
            reliability=ReliabilityPolicy.BEST_EFFORT,
        )
        transient_local_qos = QoSProfile(
            depth=1,
            reliability=ReliabilityPolicy.RELIABLE,
            durability=DurabilityPolicy.TRANSIENT_LOCAL,
        )

        # ---- 订阅者 ----
        self.task_request_sub = self.create_subscription(
            TaskRequest, '/task/request', self._on_task_request, reliable_qos)

        self.nav_status_sub = self.create_subscription(
            NavStatus, '/nav_status', self._on_nav_status, reliable_qos)

        self.obstacle_sub = self.create_subscription(
            ObstacleStatus, '/obstacle_status', self._on_obstacle_status, reliable_qos)

        self.vision_sub = self.create_subscription(
            DetectionArray, '/vision/detections', self._on_detections, best_effort_qos)

        self.sensor_sub = self.create_subscription(
            EnvData, '/sensor/env_data', self._on_env_data, reliable_qos)

        self.alert_sub = self.create_subscription(
            SensorAlert, '/sensor/alert', self._on_sensor_alert, reliable_qos)


        # ---- 发布者 ----
        self.status_pub = self.create_publisher(
            TaskStatus, '/task/status', reliable_qos)

        self.log_pub = self.create_publisher(
            TaskLog, '/task/log', reliable_qos)

        self.cmd_vel_pub = self.create_publisher(
            Twist, '/cmd_vel', reliable_qos)

        self.goal_pose_pub = self.create_publisher(
            PoseStamped, '/goal_pose', reliable_qos)

        # ---- 定时器：状态机主循环 (10 Hz) ----
        self.loop_timer = self.create_timer(0.1, self._state_machine_loop)

        self.get_logger().info("task_manager_node 已启动 — 状态: PENDING")

    # -----------------------------------------------------------------------
    # 状态管理
    # -----------------------------------------------------------------------

    def _transition_to(self, new_state: PatrolState):
        """状态切换，带合法性检查"""
        if new_state in ALLOWED_TRANSITIONS.get(self.state, []):
            old = self.state
            self.state = new_state
            self.get_logger().info(f"状态转换: {old.value} → {new_state.value}")
            self._publish_status()
        else:
            self.get_logger().warn(
                f"非法的状态转换: {self.state.value} → {new_state.value}，已忽略")

    def _publish_status(self):
        """发布当前任务状态"""
        msg = TaskStatus()
        msg.task_id = self.current_task_id
        msg.status = self.state.value
        msg.current_step = self.route_index + 1 if self.route else 0
        msg.total_steps = len(self.route)
        msg.message = self._status_message()
        self.status_pub.publish(msg)

    def _status_message(self) -> str:
        """生成当前状态的可读描述"""
        msgs = {
            PatrolState.PENDING: "等待任务下发",
            PatrolState.RUNNING: f"任务 {self.current_task_id} 启动",
            PatrolState.NAVIGATING: f"前往巡检点 {self._current_checkpoint()}",
            PatrolState.CHECKPOINT: f"到达巡检点 {self._current_checkpoint()}，记录打卡",
            PatrolState.DETECTING: "正在执行视觉检测",
            PatrolState.COLLECTING: "正在采集传感器数据",
            PatrolState.COMPLETED: "巡检任务完成",
            PatrolState.FAILED: "任务异常终止",
            PatrolState.CANCELLED: "任务已取消",
        }
        return msgs.get(self.state, "未知状态")

    def _current_checkpoint(self) -> str:
        """当前巡检点名称"""
        if self.route and self.route_index < len(self.route):
            return self.route[self.route_index]
        return "?"

    # -----------------------------------------------------------------------
    # 任务日志
    # -----------------------------------------------------------------------

    def _log_event(self, event_type: str, data: dict = None,
                   severity: str = "INFO"):
        """发布任务日志事件"""
        msg = TaskLog()
        msg.task_id = self.current_task_id
        msg.timestamp = self.get_clock().now().to_msg()
        msg.event_type = event_type
        msg.data_json = json.dumps(data or {}, ensure_ascii=False)
        msg.severity = severity
        self.log_pub.publish(msg)

        # 同时输出到 ROS2 日志
        self.get_logger().info(
            f"[{msg.event_type}] severity={severity} data={msg.data_json}")

    # -----------------------------------------------------------------------
    # 紧急停止
    # -----------------------------------------------------------------------

    def _emergency_stop(self, reason: str):
        """发布紧急停止指令"""
        self.get_logger().error(f"紧急停止: {reason}")
        stop_msg = Twist()
        stop_msg.linear.x = 0.0
        stop_msg.angular.z = 0.0
        self.cmd_vel_pub.publish(stop_msg)
        self.emergency_stop_active = True

    def _check_safety(self) -> bool:
        """
        安全检查，返回 True 表示可以继续。
        子检查:
          1. 障碍物距离 < 0.3m → 紧急停止
          2. 传感器告警(ERROR) → 紧急停止
        """
        # 障碍物检查由 _on_obstacle_status 实时处理
        # 传感器告警由 _on_sensor_alert 实时处理
        # 这里做兜底检查
        if self.emergency_stop_active:
            return False
        return True

    # -----------------------------------------------------------------------
    # 回调: 订阅数据处理
    # -----------------------------------------------------------------------

    def _on_task_request(self, msg: TaskRequest):
        """接收 APP 下发的任务请求"""
        if self.state != PatrolState.PENDING:
            self.get_logger().warn(
                f"当前状态 {self.state.value}，无法接受新任务")
            return

        self.current_task_id = f"task_{uuid.uuid4().hex[:8]}"
        self.route = list(msg.route) if msg.route else []
        self.route_index = 0
        self.emergency_stop_active = False
        self.route_goals = []
        self.goal_sent_for_index = None

        self._log_event("TASK_RECEIVED", {
            "task_type": msg.task_type,
            "route": self.route,
            "params": msg.params,
        })

        self._transition_to(PatrolState.RUNNING)


    def _on_nav_status(self, msg: NavStatus):
        """导航状态更新"""
        if self.state != PatrolState.NAVIGATING:
            return

        if msg.status == "ARRIVED":
            self._log_event("NAV_END", {
                "checkpoint": self._current_checkpoint(),
                "result": "ARRIVED",
            })
            self._transition_to(PatrolState.CHECKPOINT)

        elif msg.status == "FAILED":
            self._log_event("NAV_END", {
                "checkpoint": self._current_checkpoint(),
                "result": "FAILED",
                "message": msg.message,
            }, severity="ERROR")
            self._emergency_stop(f"导航失败: {msg.message}")
            self._transition_to(PatrolState.FAILED)

    def _on_obstacle_status(self, msg: ObstacleStatus):
        """障碍物检测回调 — 紧急情况直接停止"""
        if msg.risk_level == "danger" and msg.min_distance <= OBSTACLE_DANGER_DISTANCE:
            self._emergency_stop(
                f"障碍物距离 {msg.min_distance:.2f}m, 方位 {msg.direction}")
            if self.state == PatrolState.NAVIGATING:
                self._log_event("ANOMALY", {
                    "type": "obstacle_danger",
                    "distance": msg.min_distance,
                    "direction": msg.direction,
                }, severity="ERROR")
                self._transition_to(PatrolState.FAILED)

        elif msg.risk_level == "warning":
            self._log_event("ANOMALY", {
                "type": "obstacle_warning",
                "distance": msg.min_distance,
                "direction": msg.direction,
                "action": msg.action,
            }, severity="WARN")

    def _on_detections(self, msg: DetectionArray):
        """视觉检测结果缓存"""
        self.last_detections = msg

    def _on_env_data(self, msg: EnvData):
        """传感器数据缓存"""
        self.last_env_data = msg

    def _on_sensor_alert(self, msg: SensorAlert):
        """传感器异常告警"""
        self._log_event("ANOMALY", {
            "type": "sensor_alert",
            "sensor_type": msg.sensor_type,
            "current_value": msg.current_value,
            "threshold": msg.threshold,
            "severity": msg.severity,
            "message": msg.message,
        }, severity=msg.severity)

        if msg.severity == "ERROR":
            self._emergency_stop(
                f"传感器异常: {msg.sensor_type}={msg.current_value}, "
                f"阈值={msg.threshold}")
            if self.state in (PatrolState.NAVIGATING, PatrolState.CHECKPOINT,
                              PatrolState.DETECTING, PatrolState.COLLECTING):
                self._transition_to(PatrolState.FAILED)

    # -----------------------------------------------------------------------
    # 状态机主循环 (10 Hz)
    # -----------------------------------------------------------------------

    def _state_machine_loop(self):
        """状态机主循环，按当前状态执行对应动作"""
        if not self._check_safety():
            return  # 紧急停止状态，不执行任何动作

        state_handlers = {
            PatrolState.PENDING:    self._handle_pending,
            PatrolState.RUNNING:   self._handle_running,
            PatrolState.NAVIGATING: self._handle_navigating,
            PatrolState.CHECKPOINT: self._handle_checkpoint,
            PatrolState.DETECTING:  self._handle_detecting,
            PatrolState.COLLECTING: self._handle_collecting,
            PatrolState.COMPLETED:  self._handle_completed,
            PatrolState.FAILED:     self._handle_failed,
            PatrolState.CANCELLED:  self._handle_cancelled,
        }

        handler = state_handlers.get(self.state)
        if handler:
            handler()

    def _handle_pending(self):
        """等待任务下发 — 什么都不做"""
        pass

    def _handle_running(self):
        """
        RUNNING → NAVIGATING:
          收到任务后，开始前往第一个巡检点
        """
        if not self.route:
            self.get_logger().error("无巡检路线，任务终止")
            self._transition_to(PatrolState.FAILED)
            return

        try:
            self.route_goals = resolve_route_goals(self.route, self.checkpoints)
        except UnknownCheckpointError as error:
            self._log_event("TASK_REJECTED", {
                "reason": "unknown_checkpoint",
                "checkpoint": error.name,
                "route": self.route,
            }, severity="ERROR")
            self._transition_to(PatrolState.FAILED)
            return

        self._log_event("TASK_START", {
            "route": self.route,
            "total_checkpoints": len(self.route),
        })
        self.route_index = 0
        self.goal_sent_for_index = None
        self._transition_to(PatrolState.NAVIGATING)

    def _handle_navigating(self):
        """
        NAVIGATING → CHECKPOINT (由 _on_nav_status 触发)
        这里只做首次进入时的目标点下发
        """
        if self.route_index >= len(self.route_goals):
            self._transition_to(PatrolState.FAILED)
            return
        if self.goal_sent_for_index == self.route_index:
            return

        goal = self.route_goals[self.route_index]
        payload = goal_to_pose_payload(goal)
        message = PoseStamped()
        message.header.stamp = self.get_clock().now().to_msg()
        message.header.frame_id = payload["frame_id"]
        message.pose.position.x = payload["position"]["x"]
        message.pose.position.y = payload["position"]["y"]
        message.pose.position.z = payload["position"]["z"]
        message.pose.orientation.x = payload["orientation"]["x"]
        message.pose.orientation.y = payload["orientation"]["y"]
        message.pose.orientation.z = payload["orientation"]["z"]
        message.pose.orientation.w = payload["orientation"]["w"]
        self.goal_pose_pub.publish(message)
        self.goal_sent_for_index = self.route_index
        self._log_event("NAV_GOAL_SENT", {
            "checkpoint": goal.name,
            "x": goal.x,
            "y": goal.y,
            "yaw": goal.yaw,
        })

    def _handle_checkpoint(self):
        """
        CHECKPOINT → DETECTING:
          到达巡检点，记录打卡数据（时间/坐标），然后开始视觉检测
        """
        checkpoint_name = self._current_checkpoint()

        # 打卡记录
        checkpoint_record = {
            "checkpoint": checkpoint_name,
            "time": time.strftime("%Y-%m-%d %H:%M:%S"),
            "index": self.route_index,
        }

        # 附加传感器快照
        if self.last_env_data:
            env = self.last_env_data
            checkpoint_record["env_snapshot"] = {
                "temperature": env.temperature,
                "humidity": env.humidity,
                "smoke": env.smoke,
                "pm25": env.pm25,
                "light": env.light,
                "pressure": env.pressure,
            }

        self.checkpoint_data[checkpoint_name] = checkpoint_record
        self._log_event("CHECKPOINT_REACHED", checkpoint_record)
        self._transition_to(PatrolState.DETECTING)

    def _handle_detecting(self):
        """
        DETECTING → COLLECTING:
          视觉检测（等待/缓存检测结果），然后转入传感器采集
        """
        # 将最新检测结果写入日志
        detections_info = []
        if self.last_detections and self.last_detections.detections:
            for d in self.last_detections.detections:
                detections_info.append({
                    "class": d.class_name,
                    "confidence": round(d.confidence, 3),
                    "bbox": [d.x_min, d.y_min, d.x_max, d.y_max],
                    "image_path": d.image_path,
                })

        self._log_event("VISION_DETECT", {
            "checkpoint": self._current_checkpoint(),
            "detections": detections_info,
        })

        # 给视觉模块一点处理时间（模拟异步等待）
        self._transition_to(PatrolState.COLLECTING)

    def _handle_collecting(self):
        """
        COLLECTING → NAVIGATING (下一个点) 或 COMPLETED:
          采集传感器数据，判断是否还有剩余巡检点
        """
        checkpoint_name = self._current_checkpoint()

        # 传感器数据快照
        sensor_snapshot = {}
        if self.last_env_data:
            env = self.last_env_data
            sensor_snapshot = {
                "temperature": env.temperature,
                "humidity": env.humidity,
                "smoke": env.smoke,
                "pm25": env.pm25,
                "light": env.light,
                "pressure": env.pressure,
            }

        self._log_event("SENSOR_READING", {
            "checkpoint": checkpoint_name,
            "sensor_data": sensor_snapshot,
        })

        # 判断是否还有下一个巡检点
        self.route_index += 1
        if self.route_index < len(self.route):
            # 前往下一个巡检点
            self.goal_sent_for_index = None
            self._transition_to(PatrolState.NAVIGATING)
        else:
            # 所有巡检点已完成
            self._log_event("TASK_END", {
                "checkpoints_visited": len(self.route),
                "checkpoint_data": self.checkpoint_data,
            })
            self._transition_to(PatrolState.COMPLETED)

    def _handle_completed(self):
        """巡检完成 — 等待复位接受新任务"""
        self.get_logger().info(
            f"任务 {self.current_task_id} 已完成，等待新任务...")
        self._transition_to(PatrolState.PENDING)

    def _handle_failed(self):
        """异常终止 — 等待人工复位"""
        self.get_logger().info(
            f"任务 {self.current_task_id} 异常终止，等待人工复位...")

    def _handle_cancelled(self):
        """人工取消 — 等待复位"""
        self.get_logger().info(
            f"任务 {self.current_task_id} 已取消，等待新任务...")
        self._transition_to(PatrolState.PENDING)


# ---------------------------------------------------------------------------
# 入口
# ---------------------------------------------------------------------------

def main(args=None):
    rclpy.init(args=args)
    node = TaskManagerNode()
    try:
        rclpy.spin(node)
    except KeyboardInterrupt:
        node.get_logger().info("task_manager_node 收到中断信号，正在关闭...")
    finally:
        node.destroy_node()
        rclpy.shutdown()


if __name__ == "__main__":
    main()


if __name__ == '__main__':
    main()
