/// 车端 ROS2 Topic 数据模型
///
/// 对应 icar_interfaces 的 .msg 定义，用于 WebSocket 桥接节点推送的 JSON 反序列化。
/// 当桥接节点就绪后，这些模型将从 JSON 自动填充。
library;

import 'package:flutter/material.dart';
import '../theme/app_theme.dart';

// ═══════════════════════════════════════════
// RobotPose — /pose / MQTT pose
// ═══════════════════════════════════════════

class RobotPose {
  final double x;
  final double y;
  final double z;
  final String frameId;
  final String timestamp;

  const RobotPose({
    this.x = 0.0,
    this.y = 0.0,
    this.z = 0.0,
    this.frameId = 'map',
    this.timestamp = '',
  });

  factory RobotPose.fromJson(Map<String, dynamic> json) {
    return RobotPose(
      x: (json['x'] as num?)?.toDouble() ?? 0.0,
      y: (json['y'] as num?)?.toDouble() ?? 0.0,
      z: (json['z'] as num?)?.toDouble() ?? 0.0,
      frameId: json['frame_id']?.toString() ?? 'map',
      timestamp: json['timestamp']?.toString() ?? '',
    );
  }
}

// ═══════════════════════════════════════════
// SafetyAlarm — /safety/alarm / MQTT alert
// ═══════════════════════════════════════════

class SafetyAlarm {
  final String hazardType;
  final String event;
  final bool active;
  final String action;
  final double confidence;
  final double distance;
  final String direction;
  final String className;
  final String imagePath;
  final String checkpoint;
  final String severity;
  final String message;
  final RobotPose pose;

  const SafetyAlarm({
    this.hazardType = '',
    this.event = '',
    this.active = false,
    this.action = '',
    this.confidence = 0.0,
    this.distance = 0.0,
    this.direction = '',
    this.className = '',
    this.imagePath = '',
    this.checkpoint = '',
    this.severity = 'WARN',
    this.message = '',
    this.pose = const RobotPose(),
  });

  factory SafetyAlarm.fromJson(Map<String, dynamic> json) {
    final rawPose = json['pose'];
    return SafetyAlarm(
      hazardType: json['hazard_type']?.toString() ?? '',
      event: json['event']?.toString() ?? '',
      active: json['active'] == true,
      action: json['action']?.toString() ?? '',
      confidence: (json['confidence'] as num?)?.toDouble() ?? 0.0,
      distance: (json['distance'] as num?)?.toDouble() ?? 0.0,
      direction: json['direction']?.toString() ?? '',
      className: json['class_name']?.toString() ?? '',
      imagePath: json['image_path']?.toString() ?? '',
      checkpoint: json['checkpoint']?.toString() ?? '',
      severity: json['severity']?.toString() ?? 'WARN',
      message: json['message']?.toString() ?? '',
      pose: rawPose is Map
          ? RobotPose.fromJson(Map<String, dynamic>.from(rawPose))
          : const RobotPose(),
    );
  }

  bool get isCritical => hazardType == 'fallen_person' || severity == 'ERROR';

  String get typeZh {
    switch (hazardType) {
      case 'water':
        return '积水';
      case 'visual_obstacle':
        return '视觉障碍物';
      case 'fallen_person':
        return '人员摔倒';
      case 'obstacle':
        return '雷达障碍物';
      default:
        return hazardType.isEmpty ? '安全告警' : hazardType;
    }
  }
}

// ═══════════════════════════════════════════
// ObstacleStatus — /obstacle_status
// ═══════════════════════════════════════════

class ObstacleStatus {
  final bool isObstacle;
  final double minDistance; // 米
  final String direction; // front | left | right | back
  final String riskLevel; // safe | warning | danger
  final String action; // none | slow_down | stop | turn

  const ObstacleStatus({
    this.isObstacle = false,
    this.minDistance = 99.0,
    this.direction = 'front',
    this.riskLevel = 'safe',
    this.action = 'none',
  });

  factory ObstacleStatus.fromJson(Map<String, dynamic> json) {
    return ObstacleStatus(
      isObstacle: json['is_obstacle'] == true,
      minDistance: (json['min_distance'] as num?)?.toDouble() ?? 99.0,
      direction: json['direction']?.toString() ?? 'front',
      riskLevel: json['risk_level']?.toString() ?? 'safe',
      action: json['action']?.toString() ?? 'none',
    );
  }

  bool get isSafe => riskLevel == 'safe';
  bool get isWarning => riskLevel == 'warning';
  bool get isDanger => riskLevel == 'danger';

  String get directionZh {
    switch (direction) {
      case 'front':
        return '前方';
      case 'left':
        return '左侧';
      case 'right':
        return '右侧';
      case 'back':
        return '后方';
      default:
        return direction;
    }
  }

  String get description {
    if (!isObstacle) return '无障的物';
    return '$directionZh ${minDistance.toStringAsFixed(1)}m 处有障碍物';
  }
}

// ═══════════════════════════════════════════
// NavStatus — /nav_status
// ═══════════════════════════════════════════

class NavStatus {
  final String status; // IDLE | NAVIGATING | ARRIVED | FAILED
  final double progress; // 0.0 ~ 1.0
  final double distanceRemain; // 米
  final String message;

  const NavStatus({
    this.status = 'IDLE',
    this.progress = 0.0,
    this.distanceRemain = 0.0,
    this.message = '',
  });

  factory NavStatus.fromJson(Map<String, dynamic> json) {
    return NavStatus(
      status: json['status']?.toString() ?? 'IDLE',
      progress: (json['progress'] as num?)?.toDouble() ?? 0.0,
      distanceRemain: (json['distance_remain'] as num?)?.toDouble() ?? 0.0,
      message: json['message']?.toString() ?? '',
    );
  }

  bool get isIdle => status == 'IDLE';
  bool get isNavigating => status == 'NAVIGATING';
  bool get isArrived => status == 'ARRIVED';
  bool get isFailed => status == 'FAILED';

  String get statusZh {
    switch (status) {
      case 'IDLE':
        return '空闲';
      case 'NAVIGATING':
        return '导航中';
      case 'ARRIVED':
        return '已到达';
      case 'FAILED':
        return '导航失败';
      default:
        return status;
    }
  }

  Color get statusColor {
    switch (status) {
      case 'NAVIGATING':
        return AppColors.orange;
      case 'ARRIVED':
        return AppColors.successGreen;
      case 'FAILED':
        return AppColors.errorRed;
      default:
        return AppColors.blueGray;
    }
  }
}

// ═══════════════════════════════════════════
// TaskStatus — /task/status
// ═══════════════════════════════════════════

class TaskStatus {
  final String taskId;
  final String status;
  final int currentStep;
  final int totalSteps;
  final String message;

  const TaskStatus({
    this.taskId = '',
    this.status = 'PENDING',
    this.currentStep = 0,
    this.totalSteps = 0,
    this.message = '',
  });

  factory TaskStatus.fromJson(Map<String, dynamic> json) {
    return TaskStatus(
      taskId: json['task_id']?.toString() ?? '',
      status: json['status']?.toString() ?? 'PENDING',
      currentStep: (json['current_step'] as num?)?.toInt() ?? 0,
      totalSteps: (json['total_steps'] as num?)?.toInt() ?? 0,
      message: json['message']?.toString() ?? '',
    );
  }

  bool get isCompleted => status == 'COMPLETED';
  bool get isFailed => status == 'FAILED';
  bool get isCancelled => status == 'CANCELLED';
  bool get isActive =>
      !isCompleted && !isFailed && !isCancelled && status != 'PENDING';

  double get progress => totalSteps > 0 ? currentStep / totalSteps : 0.0;

  String get statusZh {
    switch (status) {
      case 'PENDING':
        return '等待中';
      case 'RUNNING':
        return '执行中';
      case 'NAVIGATING':
        return '导航中';
      case 'CHECKPOINT':
        return '巡检点';
      case 'DETECTING':
        return '检测中';
      case 'COLLECTING':
        return '采集中';
      case 'COMPLETED':
        return '已完成';
      case 'FAILED':
        return '已失败';
      case 'CANCELLED':
        return '已取消';
      default:
        return status;
    }
  }

  Color get statusColor {
    switch (status) {
      case 'COMPLETED':
        return AppColors.successGreen;
      case 'FAILED':
        return AppColors.errorRed;
      case 'CANCELLED':
        return AppColors.blueGray;
      case 'NAVIGATING':
      case 'RUNNING':
        return AppColors.orange;
      default:
        return AppColors.bluePurple;
    }
  }
}

// ═══════════════════════════════════════════
// TaskLog — /task/log
// ═══════════════════════════════════════════

class TaskLog {
  final String taskId;
  final String timestamp;
  final String eventType;
  final String dataJson;
  final String severity; // INFO | WARN | ERROR

  const TaskLog({
    this.taskId = '',
    this.timestamp = '',
    this.eventType = '',
    this.dataJson = '',
    this.severity = 'INFO',
  });

  factory TaskLog.fromJson(Map<String, dynamic> json) {
    return TaskLog(
      taskId: json['task_id']?.toString() ?? '',
      timestamp: json['timestamp']?.toString() ?? '',
      eventType: json['event_type']?.toString() ?? '',
      dataJson: json['data_json']?.toString() ?? '',
      severity: json['severity']?.toString() ?? 'INFO',
    );
  }

  /// 映射到日志分类（用于筛选）
  String get category {
    switch (eventType) {
      case 'NAV_START':
      case 'NAV_GOAL_SENT':
      case 'NAV_END':
      case 'CHECKPOINT_REACHED':
        return '导航';
      case 'VISION_DETECT':
        return '检测';
      case 'SENSOR_READING':
        return '传感器';
      case 'ANOMALY':
        return '传感器';
      case 'TASK_RECEIVED':
      case 'TASK_START':
      case 'TASK_REJECTED':
      case 'TASK_END':
      default:
        return '系统';
    }
  }

  IconData get icon {
    switch (eventType) {
      case 'TASK_RECEIVED':
        return Icons.task_alt;
      case 'TASK_START':
        return Icons.play_circle;
      case 'TASK_REJECTED':
        return Icons.cancel;
      case 'TASK_END':
        return Icons.stop_circle;
      case 'NAV_START':
      case 'NAV_GOAL_SENT':
        return Icons.navigation;
      case 'NAV_END':
        return Icons.location_on;
      case 'CHECKPOINT_REACHED':
        return Icons.flag;
      case 'VISION_DETECT':
        return Icons.visibility;
      case 'SENSOR_READING':
        return Icons.sensors;
      case 'ANOMALY':
        return Icons.warning;
      default:
        return Icons.info;
    }
  }

  Color get color {
    if (severity == 'ERROR') return AppColors.errorRed;
    if (severity == 'WARN') return AppColors.orange;
    switch (eventType) {
      case 'NAV_START':
      case 'NAV_GOAL_SENT':
      case 'NAV_END':
      case 'CHECKPOINT_REACHED':
        return AppColors.successGreen;
      case 'VISION_DETECT':
        return AppColors.bluePurple;
      case 'SENSOR_READING':
      case 'ANOMALY':
        return AppColors.darkNavy;
      default:
        return AppColors.bluePurple;
    }
  }

  /// 中文标题
  String get titleZh {
    switch (eventType) {
      case 'TASK_RECEIVED':
        return '收到巡检任务';
      case 'TASK_START':
        return '任务开始执行';
      case 'TASK_REJECTED':
        return '任务被拒绝';
      case 'TASK_END':
        return '任务结束';
      case 'NAV_START':
        return '开始导航';
      case 'NAV_GOAL_SENT':
        return '发送导航目标';
      case 'NAV_END':
        return '导航结束';
      case 'CHECKPOINT_REACHED':
        return '到达巡检点';
      case 'VISION_DETECT':
        return '视觉检测';
      case 'SENSOR_READING':
        return '采集环境数据';
      case 'ANOMALY':
        return '异常告警';
      default:
        return eventType;
    }
  }

  /// 从 dataJson 中提取简要描述
  String get summary {
    if (dataJson.isEmpty) return '';
    try {
      // 尝试解析 data_json 中的关键信息
      // 由于 data_json 的内容因 event_type 而异，这里做简要展示
      final len = dataJson.length;
      if (len > 120) return '${dataJson.substring(0, 120)}...';
      return dataJson;
    } catch (_) {
      return dataJson;
    }
  }

  /// 提取时间部分（去掉日期）
  String get timeShort {
    if (timestamp.length > 11) {
      return timestamp.substring(11); // "HH:MM:SS"
    }
    return timestamp;
  }

  bool get isAlert => severity == 'ERROR' || severity == 'WARN';
}

// ═══════════════════════════════════════════
// EnvData — /sensor/env_data
// ═══════════════════════════════════════════

class EnvData {
  final double temperature;
  final double humidity;
  final double smoke;
  final double pm25;
  final double light;
  final double pressure;

  const EnvData({
    this.temperature = 0.0,
    this.humidity = 0.0,
    this.smoke = 0.0,
    this.pm25 = 0.0,
    this.light = 0.0,
    this.pressure = 0.0,
  });

  factory EnvData.fromJson(Map<String, dynamic> json) {
    return EnvData(
      temperature: (json['temperature'] as num?)?.toDouble() ?? 0.0,
      humidity: (json['humidity'] as num?)?.toDouble() ?? 0.0,
      smoke: (json['smoke'] as num?)?.toDouble() ?? 0.0,
      pm25: (json['pm25'] as num?)?.toDouble() ?? 0.0,
      light: (json['light'] as num?)?.toDouble() ?? 0.0,
      pressure: (json['pressure'] as num?)?.toDouble() ?? 0.0,
    );
  }

  /// 默认阈值
  static const Map<String, double> thresholds = {
    'temperature': 38.0,
    'humidity': 80.0,
    'pm25': 75.0,
    'smoke': 300.0,
    'light': 800.0,
    'pressure': 1050.0,
  };

  bool get isTempAlert => temperature > thresholds['temperature']!;
  bool get isHumidityAlert => humidity > thresholds['humidity']!;
  bool get isPm25Alert => pm25 > thresholds['pm25']!;
  bool get isSmokeAlert => smoke > thresholds['smoke']!;
  bool get isLightAlert => light > thresholds['light']!;
  bool get isPressureAlert => pressure > thresholds['pressure']!;

  bool get hasAlert =>
      isTempAlert ||
      isHumidityAlert ||
      isPm25Alert ||
      isSmokeAlert ||
      isLightAlert ||
      isPressureAlert;
}

// ═══════════════════════════════════════════
// SensorAlert — /sensor/alert
// ═══════════════════════════════════════════

class SensorAlert {
  final String sensorType;
  final double currentValue;
  final double threshold;
  final String severity; // WARN | ERROR
  final String message;

  const SensorAlert({
    this.sensorType = '',
    this.currentValue = 0.0,
    this.threshold = 0.0,
    this.severity = 'WARN',
    this.message = '',
  });

  factory SensorAlert.fromJson(Map<String, dynamic> json) {
    return SensorAlert(
      sensorType: json['sensor_type']?.toString() ?? '',
      currentValue: (json['current_value'] as num?)?.toDouble() ?? 0.0,
      threshold: (json['threshold'] as num?)?.toDouble() ?? 0.0,
      severity: json['severity']?.toString() ?? 'WARN',
      message: json['message']?.toString() ?? '',
    );
  }

  String get sensorTypeZh {
    switch (sensorType) {
      case 'temperature':
        return '温度';
      case 'humidity':
        return '湿度';
      case 'pm25':
        return 'PM2.5';
      case 'smoke':
        return '烟雾';
      case 'light':
        return '光照';
      case 'pressure':
        return '气压';
      default:
        return sensorType;
    }
  }

  bool get isError => severity == 'ERROR';
}

// ═══════════════════════════════════════════
// TrackingStatus — /vision/target_tracking/status
// ═══════════════════════════════════════════

class TrackingStatus {
  final String
  event; // ready | tracking_started | tracking | no_target | target_lost | tracking_stopped
  final bool enabled;
  final Map<String, dynamic> data;

  const TrackingStatus({
    this.event = 'ready',
    this.enabled = false,
    this.data = const {},
  });

  factory TrackingStatus.fromJson(Map<String, dynamic> json) {
    return TrackingStatus(
      event: json['event']?.toString() ?? 'ready',
      enabled: json['enabled'] == true,
      data: json['data'] is Map<String, dynamic>
          ? json['data'] as Map<String, dynamic>
          : const {},
    );
  }

  bool get isTracking => event == 'tracking_started' || event == 'tracking';
  bool get isLost => event == 'target_lost' || event == 'no_target';
  bool get isStopped => event == 'tracking_stopped' || event == 'ready';

  String get eventZh {
    switch (event) {
      case 'ready':
        return '待命';
      case 'tracking_started':
        return '跟踪已启动';
      case 'tracking':
        return '跟踪中';
      case 'no_target':
        return '未检测到目标';
      case 'target_lost':
        return '目标丢失';
      case 'tracking_stopped':
        return '已停止跟踪';
      default:
        return event;
    }
  }

  Color get statusColor {
    if (isTracking) return AppColors.successGreen;
    if (isLost) return AppColors.orange;
    return AppColors.blueGray;
  }
}
