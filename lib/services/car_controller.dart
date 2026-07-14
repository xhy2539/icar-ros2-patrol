import 'dart:async';
import 'package:flutter/foundation.dart';
import 'package:flutter/services.dart';
import 'car_tcp_service.dart';
import 'car_commands.dart';
import 'cloud_mqtt_service.dart';
import 'cloud_protocol.dart';
import 'vision_models.dart';
import 'data_models.dart';

/// 小车控制器 - 全局状态管理
///
/// 使用 ChangeNotifier 驱动 UI 更新，无需额外状态管理库。
/// 通过 CarController.instance 单例访问。
///
/// 通信方式：WebSocket → `ws://<IP>:6500/ws/control`
/// 指令格式：纯文本字符串 (forward/backward/left/right/stop/start)
class CarController extends ChangeNotifier {
  // ═══════════════════════════════════════════
  // 单例
  // ═══════════════════════════════════════════

  static final CarController instance = CarController._();
  CarController._() {
    _service.onStateChanged = (state) {
      if (_connectionMode == CarConnectionMode.local) {
        _onStateChanged(state);
      }
    };
    _service.onError = _onError;
    _service.onLog = _onLog;
    _service.responseStream.listen(_onResponse);
    _service.detectionStream.listen(_onDetection);
    _service.captureStatusStream.listen(_onCaptureStatus);
    _service.parseTaskStream.listen(_forwardParseTaskResult);
    _service.reportStream.listen(_forwardReportResult);
    _service.llmCommandStream.listen(_forwardLlmCommandResult);
    _service.obstacleStream.listen(_onObstacleStatus);
    _service.navStatusStream.listen(_onNavStatus);
    _service.taskStatusStream.listen(_onTaskStatus);
    _service.taskLogStream.listen(_onTaskLog);
    _service.envDataStream.listen(_onEnvData);
    _service.sensorAlertStream.listen(_onSensorAlert);
    _service.safetyAlarmStream.listen(_onSafetyAlarm);
    _service.trackingStream.listen(_onTrackingStatus);
    _service.imageFrameStream.listen(_imageFrameEvents.add);

    _cloudService.onStateChanged = (state) {
      if (_connectionMode == CarConnectionMode.cloud) {
        _onStateChanged(state);
      }
    };
    _cloudService.onError = _onError;
    _cloudService.onLog = _onLog;
    _cloudService.taskStatusStream.listen(_onTaskStatus);
    _cloudService.navStatusStream.listen(_onNavStatus);
    _cloudService.obstacleStream.listen(_onObstacleStatus);
    _cloudService.envDataStream.listen(_onEnvData);
    _cloudService.sensorAlertStream.listen(_onSensorAlert);
    _cloudService.safetyAlarmStream.listen(_onSafetyAlarm);
    _cloudService.taskLogStream.listen(_onTaskLog);
    _cloudService.llmCommandStream.listen(_forwardLlmCommandResult);
    _cloudService.reportStream.listen(_forwardReportResult);
    _cloudService.ackStream.listen(_onCloudAck);
    _cloudService.onlineStream.listen(_onRobotOnline);
    _cloudService.snapshotStream.listen(_onRemoteSnapshot);
  }

  final CarWebSocketService _service = CarWebSocketService();
  final CloudMqttService _cloudService = CloudMqttService();
  final _parseTaskEvents = StreamController<Map<String, dynamic>>.broadcast();
  final _reportEvents = StreamController<Map<String, dynamic>>.broadcast();
  final _llmCommandEvents = StreamController<Map<String, dynamic>>.broadcast();
  final _imageFrameEvents = StreamController<String>.broadcast();

  // ═══════════════════════════════════════════
  // 状态（UI 可直接读取）
  // ═══════════════════════════════════════════

  /// 连接状态
  CarConnectionState get connectionState =>
      isCloudMode ? _cloudService.state : _service.state;
  bool get isConnected =>
      isCloudMode ? _cloudService.isConnected : _service.isConnected;

  CarConnectionMode _connectionMode = CarConnectionMode.local;
  CarConnectionMode get connectionMode => _connectionMode;
  bool get isCloudMode => _connectionMode == CarConnectionMode.cloud;
  bool get robotOnline => !isCloudMode || _cloudService.robotOnline;
  bool get canSendCommands => isConnected && robotOnline;
  bool get canManualControl => canSendCommands;
  bool get hasLocalMedia => !isCloudMode && _service.isConnected;

  String _mqttHost = CloudMqttConfig.defaults.host;
  int _mqttPort = CloudMqttConfig.defaults.port;
  String _mqttUser = CloudMqttConfig.defaults.username;
  String _mqttPassword = CloudMqttConfig.defaults.password;
  String _mqttTopicPrefix = CloudMqttConfig.defaults.topicPrefix;
  String _deviceId = CloudMqttConfig.defaults.deviceId;
  bool _mqttTls = CloudMqttConfig.defaults.useTls;

  String get mqttHost => _mqttHost;
  int get mqttPort => _mqttPort;
  String get mqttUser => _mqttUser;
  String get mqttPassword => _mqttPassword;
  String get mqttTopicPrefix => _mqttTopicPrefix;
  String get deviceId => _deviceId;
  bool get mqttTls => _mqttTls;

  /// 当前 IP
  String get host => _host;
  String _host = '10.247.5.83';

  /// 当前端口
  int get port => _port;
  int _port = CarWebSocketService.defaultPort;

  /// 当前速度 (0.0 ~ 1.0)，用于 UI 显示
  double _speed = 0.5;
  double get speed => _speed;
  set speed(double v) {
    _speed = v.clamp(0.0, 1.0);
    notifyListeners();
  }

  /// 当前动作描述
  String _currentAction = '待机';
  String get currentAction => _currentAction;

  /// 当前方向 (空 = 静止)
  String _currentDirection = '';
  String get currentDirection => _currentDirection;

  /// 最近的响应消息
  String _lastResponse = '';
  String get lastResponse => _lastResponse;

  /// 错误/日志消息列表
  final List<String> _messages = [];
  List<String> get messages => List.unmodifiable(_messages);

  /// 自动重连开关
  bool _autoReconnect = true;
  bool get autoReconnect => _autoReconnect;

  /// 触觉反馈开关
  bool _hapticEnabled = true;
  bool get hapticEnabled => _hapticEnabled;
  set hapticEnabled(bool v) {
    _hapticEnabled = v;
    notifyListeners();
  }

  /// 告警提示音开关。仅影响本机 App 的提示音，不影响车端避障或急停。
  bool _alertSoundEnabled = true;
  bool get alertSoundEnabled => _alertSoundEnabled;

  bool _obstacleAvoidanceEnabled = true;
  bool get obstacleAvoidanceEnabled => _obstacleAvoidanceEnabled;

  DateTime? _lastAlertSoundAt;

  void _playAlertSound() {
    if (!_alertSoundEnabled) return;
    final now = DateTime.now();
    // 避障和传感器状态可能高频发布；限制频率以免持续刺耳响铃。
    if (_lastAlertSoundAt != null &&
        now.difference(_lastAlertSoundAt!) < const Duration(seconds: 2)) {
      return;
    }
    _lastAlertSoundAt = now;
    SystemSound.play(SystemSoundType.alert);
  }

  /// 从设置页批量更新配置
  ///
  /// 如果当前未连接，只保存配置；如果已连接且 IP/端口变化，会断开旧连接并用新地址重连。
  Future<void> updateSettings({
    CarConnectionMode? connectionMode,
    String? host,
    int? port,
    String? mqttHost,
    int? mqttPort,
    String? mqttUser,
    String? mqttPassword,
    String? mqttTopicPrefix,
    String? deviceId,
    bool? mqttTls,
    double? speed,
    bool? autoReconnect,
    bool? hapticEnabled,
    bool? alertSoundEnabled,
    bool? obstacleAvoidanceEnabled,
  }) async {
    final oldMode = _connectionMode;
    final wasConnected = isConnected;
    final needReconnect =
        (connectionMode != null && connectionMode != _connectionMode) ||
        (host != null && host.isNotEmpty && host != _host) ||
        (port != null && port != _port) ||
        (mqttHost != null && mqttHost.isNotEmpty && mqttHost != _mqttHost) ||
        (mqttPort != null && mqttPort != _mqttPort) ||
        (mqttUser != null && mqttUser != _mqttUser) ||
        (mqttPassword != null && mqttPassword != _mqttPassword) ||
        (mqttTopicPrefix != null && mqttTopicPrefix != _mqttTopicPrefix) ||
        (deviceId != null && deviceId != _deviceId) ||
        (mqttTls != null && mqttTls != _mqttTls);

    if (wasConnected && needReconnect) {
      if (oldMode == CarConnectionMode.cloud) {
        await _cloudService.disconnect();
      } else {
        await _service.disconnect();
      }
    }

    _connectionMode = connectionMode ?? _connectionMode;
    if (host != null && host.isNotEmpty && host != _host) {
      _host = host;
    }
    if (port != null && port != _port) {
      _port = port;
    }
    if (mqttHost != null && mqttHost.isNotEmpty) _mqttHost = mqttHost;
    if (mqttPort != null) _mqttPort = mqttPort;
    if (mqttUser != null) _mqttUser = mqttUser;
    if (mqttPassword != null) _mqttPassword = mqttPassword;
    if (mqttTopicPrefix != null && mqttTopicPrefix.isNotEmpty) {
      _mqttTopicPrefix = mqttTopicPrefix;
    }
    if (deviceId != null) _deviceId = deviceId;
    if (mqttTls != null) _mqttTls = mqttTls;
    if (speed != null) {
      _speed = speed.clamp(0.0, 1.0);
    }
    if (autoReconnect != null) {
      _autoReconnect = autoReconnect;
      if (autoReconnect) {
        _service.enableAutoReconnect();
      } else {
        _service.disableAutoReconnect();
      }
    }
    if (hapticEnabled != null) {
      _hapticEnabled = hapticEnabled;
    }
    if (alertSoundEnabled != null) {
      _alertSoundEnabled = alertSoundEnabled;
      if (isCloudMode && _cloudService.isConnected) {
        _cloudService.publishAlertSound(enabled: alertSoundEnabled);
      } else if (!isCloudMode && _service.isConnected) {
        _service.sendJson({
          'action': 'set_alert_sound',
          'enabled': alertSoundEnabled,
        });
      }
    }
    if (obstacleAvoidanceEnabled != null) {
      _obstacleAvoidanceEnabled = obstacleAvoidanceEnabled;
      if (!isCloudMode && _service.isConnected) {
        _service.sendJson({
          'action': 'set_obstacle_avoidance',
          'enabled': obstacleAvoidanceEnabled,
        });
      }
    }

    if (wasConnected && needReconnect) {
      await connect();
    }

    notifyListeners();
  }

  CloudMqttConfig get _cloudConfig => CloudMqttConfig(
    host: _mqttHost,
    port: _mqttPort,
    username: _mqttUser,
    password: _mqttPassword,
    topicPrefix: _mqttTopicPrefix,
    deviceId: _deviceId,
    useTls: _mqttTls,
    autoReconnect: _autoReconnect,
  );

  // ═══════════════════════════════════════════
  // 视觉状态
  // ═══════════════════════════════════════════

  /// 最新检测结果
  DetectionArray _latestDetections = DetectionArray(detections: []);
  DetectionArray get latestDetections => _latestDetections;

  /// 最新截图状态
  CaptureStatus? _latestCaptureStatus;
  CaptureStatus? get latestCaptureStatus => _latestCaptureStatus;

  /// Latest structured safety event, including automatic hazard evidence.
  SafetyAlarm? _latestSafetyAlarm;
  SafetyAlarm? get latestSafetyAlarm => _latestSafetyAlarm;

  /// 视觉检测流
  Stream<DetectionArray> get detectionStream => _service.detectionStream;

  /// 截图状态流
  Stream<CaptureStatus> get captureStatusStream => _service.captureStatusStream;

  /// 摄像头帧流（base64 JPEG）
  Stream<String> get imageFrameStream => _imageFrameEvents.stream;

  // ═══════════════════════════════════════════
  // LLM 状态
  // ═══════════════════════════════════════════

  /// LLM parse_task 流
  Stream<Map<String, dynamic>> get parseTaskStream => _parseTaskEvents.stream;

  /// LLM generate_report 流
  Stream<Map<String, dynamic>> get reportStream => _reportEvents.stream;

  /// 可执行 LLM 指挥结果流
  Stream<Map<String, dynamic>> get llmCommandStream => _llmCommandEvents.stream;

  /// 最新 parse_task 结果
  Map<String, dynamic>? _latestParseResult;
  Map<String, dynamic>? get latestParseResult => _latestParseResult;

  /// 最新巡检报告
  String _latestReport = '';
  String get latestReport => _latestReport;

  /// 最新可执行工具结果
  Map<String, dynamic>? _latestLlmCommandResult;
  Map<String, dynamic>? get latestLlmCommandResult => _latestLlmCommandResult;

  /// LLM 请求是否正在等待响应
  bool _llmLoading = false;
  bool get llmLoading => _llmLoading;

  // ═══════════════════════════════════════════
  // 导航与避障状态
  // ═══════════════════════════════════════════

  /// 最新避障状态
  ObstacleStatus _latestObstacle = const ObstacleStatus();
  ObstacleStatus get latestObstacleStatus => _latestObstacle;

  /// 最新导航状态
  NavStatus _latestNavStatus = const NavStatus();
  NavStatus get latestNavStatus => _latestNavStatus;

  /// 最新任务状态
  TaskStatus _latestTaskStatus = const TaskStatus();
  TaskStatus get latestTaskStatus => _latestTaskStatus;

  /// 任务日志列表
  final List<TaskLog> _taskLogs = [];
  List<TaskLog> get taskLogs => List.unmodifiable(_taskLogs);

  // ═══════════════════════════════════════════
  // 传感器状态
  // ═══════════════════════════════════════════

  /// 最新环境数据
  EnvData _latestEnvData = const EnvData();
  EnvData get latestEnvData => _latestEnvData;

  /// 最新传感器告警
  SensorAlert? _latestSensorAlert;
  SensorAlert? get latestSensorAlert => _latestSensorAlert;

  // ═══════════════════════════════════════════
  // 人员跟踪状态
  // ═══════════════════════════════════════════

  /// 最新跟踪状态
  TrackingStatus _latestTracking = const TrackingStatus();
  TrackingStatus get latestTrackingStatus => _latestTracking;

  // ═══════════════════════════════════════════
  // URL 工具（供 UI 使用）
  // ═══════════════════════════════════════════

  /// 摄像头视频流 URL
  String get videoUrl => CarWebSocketService.buildVideoUrl(_host, _port);

  /// YOLO 视频流 URL
  String get yoloVideoUrl =>
      CarWebSocketService.buildYoloVideoUrl(_host, _port);

  /// 带标注的视频流 URL（YOLO 检测框叠加）
  String get annotatedVideoUrl => yoloVideoUrl;

  /// WebSocket 连接 URL
  String get wsUrl => _service.buildWsUrl(_host, _port);
  String get connectionLabel => isCloudMode
      ? 'mqtt${_mqttTls ? 's' : ''}://$_mqttHost:$_mqttPort'
      : wsUrl;

  // ═══════════════════════════════════════════
  // 操作
  // ═══════════════════════════════════════════

  /// 连接小车
  Future<bool> connect([String? host, int? port]) async {
    _host = host ?? _host;
    _port = port ?? _port;

    if (isCloudMode) {
      _addMessage('正在连接云端 $connectionLabel ...');
      final ok = await _cloudService.connect(_cloudConfig);
      _currentAction = ok ? '云端已连接' : '云端连接失败';
      _addMessage(ok ? 'MQTT 连接成功，等待小车上线' : 'MQTT 连接失败');
      notifyListeners();
      return ok;
    }

    if (_autoReconnect) {
      _service.enableAutoReconnect();
    }

    _addMessage('正在连接 ${_service.buildWsUrl(_host, _port)} ...');
    final ok = await _service.connect(_host, _port);

    if (ok) {
      _currentAction = '已连接';
      _addMessage('WebSocket 连接成功');
      _service.subscribeAllTopics();
    } else {
      _currentAction = '连接失败';
      _addMessage('WebSocket 连接失败');
    }

    notifyListeners();
    return ok;
  }

  /// 断开连接
  Future<void> disconnect() async {
    if (isCloudMode) {
      if (_cloudService.isConnected && _cloudService.robotOnline) {
        _cloudService.publishManualControl('stop', 0.0);
      }
      await _cloudService.disconnect();
    } else {
      await _service.disconnect();
    }
    _currentAction = '待机';
    _currentDirection = '';
    // 清空实时状态（桥接节点数据不再推送）
    _latestObstacle = const ObstacleStatus();
    _latestNavStatus = const NavStatus();
    _latestTaskStatus = const TaskStatus();
    _latestTracking = const TrackingStatus();
    _addMessage('已断开连接');
    notifyListeners();
  }

  /// 设置自动重连
  void setAutoReconnect(bool enabled) {
    _autoReconnect = enabled;
    if (enabled) {
      _service.enableAutoReconnect();
    } else {
      _service.disableAutoReconnect();
    }
    notifyListeners();
  }

  /// 发送方向指令
  bool sendCommand(String direction) {
    if (!canSendCommands) {
      _addMessage(isCloudMode && isConnected ? '小车云桥离线，无法发送指令' : '未连接，无法发送指令');
      notifyListeners();
      return false;
    }

    final cmd = CarCommands.fromDirection(direction);
    // 两种链路都使用心跳续租。云端指令还会经过 cloud_bridge 的
    // 1 秒租约和 velocity_mux 的 0.4 秒源超时双重保护。
    final ok = isCloudMode
        ? _cloudService.publishManualControl(cmd, _speed)
        : _service.sendJson({'command': cmd, 'speed': _speed});

    if (ok) {
      _currentDirection = direction == 'stop' ? '' : direction;
      _addMessage('发送指令: $cmd');
      switch (direction) {
        case 'forward':
          _currentAction = '前进中';
          break;
        case 'backward':
          _currentAction = '后退中';
          break;
        case 'left':
          _currentAction = '左平移中';
          break;
        case 'right':
          _currentAction = '右平移中';
          break;
        case 'turn_left':
          _currentAction = '左转中';
          break;
        case 'turn_right':
          _currentAction = '右转中';
          break;
        case 'stop':
          _currentAction = '已停止';
          break;
      }
    } else {
      _currentAction = '发送失败';
    }

    notifyListeners();
    return ok;
  }

  /// 发送自动归位
  bool sendAutoReturn() {
    if (!isConnected || isCloudMode) return false;
    // TODO: 确认是否有专用归位指令，当前发 stop
    final ok = _service.send(CarCommands.stop);
    if (ok) _addMessage('自动归位指令已发送');
    notifyListeners();
    return ok;
  }

  /// 发送截图（单次）
  bool sendScreenshot({bool annotated = false}) {
    if (isCloudMode) {
      if (!canSendCommands) {
        _addMessage('小车云桥离线，无法请求远程截图');
        notifyListeners();
        return false;
      }
      final ok = _cloudService.publishSnapshotRequest(annotated: annotated);
      _addMessage(ok ? '已请求远程${annotated ? "标注" : "原始"}截图' : '远程截图请求发送失败');
      notifyListeners();
      return ok;
    }
    return sendCaptureCommand({'action': 'capture_once', 'tag': 'manual'});
  }

  /// 发送截图控制命令
  ///
  /// 支持的 action:
  ///   - `capture_once` + `tag`: 单次截图
  ///   - `set_interval` + `interval_sec`: 定时截图
  ///   - `stop`: 停止定时截图
  ///   - `set_max_images` + `max_images`: 设置最大保存数
  bool sendCaptureCommand(Map<String, dynamic> command) {
    if (!isConnected || isCloudMode) {
      _addMessage(isCloudMode ? '远程模式暂不传输视频/截图' : '未连接，无法发送截图命令');
      notifyListeners();
      return false;
    }
    final ok = _service.sendJson(command);
    if (ok) {
      _addMessage('截图命令: $command');
    }
    notifyListeners();
    return ok;
  }

  /// 发送录制
  bool sendRecord() {
    if (!isConnected || isCloudMode) return false;
    // TODO: 确认录制指令
    final ok = _service.send('record');
    if (ok) _addMessage('录制指令已发送');
    notifyListeners();
    return ok;
  }

  /// 发送 LLM parse_task 请求（自然语言 → 结构化任务 JSON）
  bool sendParseTask(String inputText) {
    if (!isConnected || isCloudMode) {
      _addMessage(isCloudMode ? '远程模式请使用 LLM 指挥入口' : '未连接，无法发送 LLM 请求');
      notifyListeners();
      return false;
    }
    _llmLoading = true;
    _addMessage('[LLM] 发送 parse_task: "$inputText"');
    final ok = _service.sendJson({
      'action': 'parse_task',
      'input_text': inputText,
    });
    if (!ok) {
      _llmLoading = false;
    }
    notifyListeners();
    return ok;
  }

  /// 发送自然语言到 LLM 工具通道；结果会带相同 request_id 返回。
  String? sendLlmCommand(String inputText) {
    final text = inputText.trim();
    if (!canSendCommands || text.isEmpty) {
      _addMessage(!canSendCommands ? '小车不可达，无法发送 LLM 指挥' : 'LLM 指令不能为空');
      notifyListeners();
      return null;
    }
    final requestId =
        'app_${DateTime.now().microsecondsSinceEpoch.toRadixString(16)}';
    _llmLoading = true;
    _addMessage('[LLM 指挥] $text');
    final ok = isCloudMode
        ? _cloudService.publishLlmCommand(text, requestId)
        : _service.sendJson({
            'action': 'llm_command',
            'request_id': requestId,
            'input_text': text,
          });
    if (!ok) {
      _llmLoading = false;
      notifyListeners();
      return null;
    }
    notifyListeners();
    return requestId;
  }

  /// 发送 LLM generate_report 请求（任务日志 → 巡检报告）
  bool sendGenerateReport(String taskId) {
    if (!canSendCommands) {
      _addMessage('小车不可达，无法生成报告');
      notifyListeners();
      return false;
    }
    _llmLoading = true;
    _addMessage('[LLM] 请求生成报告: task_id=$taskId');
    final ok = isCloudMode
        ? _cloudService.publishReportRequest(taskId)
        : _service.sendJson({'action': 'generate_report', 'task_id': taskId});
    if (!ok) {
      _llmLoading = false;
    }
    notifyListeners();
    return ok;
  }

  /// 发送已解析的任务给 task_manager（/task/request）
  bool sendParsedTaskToManager(Map<String, dynamic> taskJson) {
    if (!canSendCommands) return false;
    _addMessage('[LLM] 发送任务到 task_manager: ${taskJson['task_type']}');
    bool ok;
    if (isCloudMode) {
      final taskType = taskJson['task_type']?.toString() ?? '';
      final rawRoute = taskJson['route'];
      if (taskType != 'patrol' || rawRoute is! List || rawRoute.isEmpty) {
        _addMessage('[云端] 目前只允许非空路线的 patrol 任务');
        notifyListeners();
        return false;
      }
      final route = rawRoute.map((point) => point.toString()).toList();
      final rawParams = taskJson['params'];
      final params = rawParams is Map
          ? Map<String, dynamic>.from(rawParams)
          : <String, dynamic>{'actions': taskJson['actions'] ?? []};
      ok = _cloudService.publishPatrol(route: route, params: params);
    } else {
      ok = _service.sendJson({'action': 'task_request', 'task': taskJson});
    }
    if (ok) {
      _currentAction = '任务下发中';
    }
    notifyListeners();
    return ok;
  }

  // ═══════════════════════════════════════════
  // 导航与跟踪指令
  // ═══════════════════════════════════════════

  /// 发送导航目标点
  bool sendGoalPose(double x, double y, [double yaw = 0.0]) {
    if (!isConnected || isCloudMode) {
      _addMessage(isCloudMode ? '远程模式请通过巡检任务下发导航' : '未连接，无法发送导航目标');
      notifyListeners();
      return false;
    }
    _addMessage('[导航] 发送目标: ($x, $y, yaw=$yaw)');
    final ok = _service.sendGoalPose(x, y, yaw);
    if (ok) {
      _currentAction = '导航中';
    }
    notifyListeners();
    return ok;
  }

  /// 启动人员跟踪（局域网/云端双模式）
  bool sendTrackingStart([List<String> targetClasses = const ['person']]) {
    if (!canSendCommands) {
      _addMessage('小车不可达，无法启动跟踪');
      notifyListeners();
      return false;
    }
    _addMessage('[跟踪] 启动跟踪: ${targetClasses.join(",")}');
    final ok = isCloudMode
        ? _cloudService.publishLlmCommand('启动跟踪，跟踪前面的人', '')
        : _service.sendTrackingCommand({
            'command': 'start',
            'target_classes': targetClasses,
          });
    if (ok) {
      _currentAction = '跟踪中';
    }
    notifyListeners();
    return ok;
  }

  /// 停止人员跟踪（局域网/云端双模式）
  bool sendTrackingStop() {
    if (!canSendCommands) {
      _addMessage('小车不可达，无法停止跟踪');
      notifyListeners();
      return false;
    }
    _addMessage('[跟踪] 停止跟踪');
    final ok = isCloudMode
        ? _cloudService.publishLlmCommand('停止跟踪', '')
        : _service.sendTrackingCommand({'command': 'stop'});
    notifyListeners();
    return ok;
  }

  /// 清空任务日志
  void clearTaskLogs() {
    _taskLogs.clear();
    notifyListeners();
  }

  /// 清空消息日志
  void clearMessages() {
    _messages.clear();
    notifyListeners();
  }

  // ═══════════════════════════════════════════
  // 内部回调
  // ═══════════════════════════════════════════

  void _onStateChanged(CarConnectionState state) {
    switch (state) {
      case CarConnectionState.connected:
        _currentAction = '已连接';
        _addMessage('[状态] → 已连接 ($connectionLabel)');
        break;
      case CarConnectionState.disconnected:
        _currentAction = '已断开';
        _currentDirection = '';
        _addMessage('[状态] → 已断开');
        break;
      case CarConnectionState.connecting:
        _currentAction = '连接中...';
        _addMessage('[状态] → 连接中...');
        break;
      case CarConnectionState.error:
        _currentAction = '连接错误';
        _addMessage('[状态] → 连接错误');
        break;
    }
    notifyListeners();
  }

  void _onError(String error) {
    _addMessage('[错误] $error');
    notifyListeners();
  }

  void _onLog(String msg) {
    _addMessage('[调试] $msg');
    notifyListeners();
  }

  void _onResponse(String raw) {
    _lastResponse = raw;
    // 截断过长的消息，避免日志刷屏
    final display = raw.length > 200 ? '${raw.substring(0, 200)}...' : raw;
    _addMessage('[收到] $display');
    notifyListeners();
  }

  void _onDetection(DetectionArray arr) {
    _latestDetections = arr;
    notifyListeners();
    // 不写入日志面板，避免高频刷新
  }

  void _onCaptureStatus(CaptureStatus status) {
    _latestCaptureStatus = status;
    _addMessage('[截图] ${status.description}');
    notifyListeners();
  }

  void _onParseTaskResult(Map<String, dynamic> result) {
    _llmLoading = false;
    _latestParseResult = result;
    final success = result['success'] == true;
    if (success) {
      _addMessage('[LLM] parse_task 成功');
    } else {
      _addMessage('[LLM] parse_task 失败: ${result['error_msg'] ?? '未知错误'}');
    }
    notifyListeners();
  }

  void _forwardParseTaskResult(Map<String, dynamic> result) {
    _onParseTaskResult(result);
    _parseTaskEvents.add(result);
  }

  void _onReportResult(Map<String, dynamic> result) {
    _llmLoading = false;
    final success = result['success'] == true;
    if (success) {
      _latestReport = result['report_text']?.toString() ?? '';
      _addMessage('[LLM] 报告生成成功');
    } else {
      _addMessage('[LLM] 报告生成失败: ${result['error_msg'] ?? '未知错误'}');
    }
    notifyListeners();
  }

  void _forwardReportResult(Map<String, dynamic> result) {
    _onReportResult(result);
    _reportEvents.add(result);
  }

  void _onLlmCommandResult(Map<String, dynamic> result) {
    _llmLoading = false;
    _latestLlmCommandResult = result;
    final success = result['success'] == true;
    final reply = result['reply'] ?? result['message'] ?? result['error_msg'];
    _addMessage(
      success ? '[LLM 执行] ${reply ?? '完成'}' : '[LLM 失败] ${reply ?? '未知错误'}',
    );
    notifyListeners();
  }

  void _forwardLlmCommandResult(Map<String, dynamic> result) {
    _onLlmCommandResult(result);
    _llmCommandEvents.add(result);
  }

  void _onCloudAck(Map<String, dynamic> ack) {
    final accepted = ack['accepted'] == true;
    final message = ack['message']?.toString() ?? '';
    _addMessage('[云端确认] ${accepted ? '已接受' : '已拒绝'} $message');
    notifyListeners();
  }

  void _onRobotOnline(bool online) {
    _currentAction = online ? '小车云桥在线' : '小车云桥离线';
    _addMessage(online ? '[云端] 小车已上线' : '[云端] 小车已离线');
    notifyListeners();
  }

  // ═══════════════════════════════════════════
  // 导航 / 避障 / 任务 / 传感器 / 跟踪 回调
  // ═══════════════════════════════════════════

  void _onObstacleStatus(ObstacleStatus obs) {
    _latestObstacle = obs;
    if (obs.isDanger) {
      _playAlertSound();
      _addMessage(
        '[避障] ${obs.directionZh} ${obs.minDistance.toStringAsFixed(1)}m — 危险',
      );
    } else if (obs.isWarning) {
      _playAlertSound();
      _addMessage(
        '[避障] ${obs.directionZh} ${obs.minDistance.toStringAsFixed(1)}m — 警告',
      );
    }
    notifyListeners();
  }

  void _onNavStatus(NavStatus nav) {
    _latestNavStatus = nav;
    if (nav.isArrived) {
      _addMessage('[导航] 已到达目标点');
    } else if (nav.isFailed) {
      _addMessage('[导航] 导航失败: ${nav.message}');
    }
    notifyListeners();
  }

  void _onTaskStatus(TaskStatus task) {
    _latestTaskStatus = task;
    _addMessage(
      '[任务] ${task.statusZh} (${task.currentStep}/${task.totalSteps})',
    );
    notifyListeners();
  }

  void _onTaskLog(TaskLog log) {
    _taskLogs.add(log);
    if (_taskLogs.length > 500) {
      _taskLogs.removeRange(0, _taskLogs.length - 500);
    }
    _addMessage('[日志] ${log.titleZh}');
    notifyListeners();
  }

  void _onEnvData(EnvData data) {
    _latestEnvData = data;
    notifyListeners();
    // 不写入日志面板，避免高频刷新
  }

  void _onSensorAlert(SensorAlert alert) {
    _latestSensorAlert = alert;
    _playAlertSound();
    _addMessage(
      '[告警] ${alert.sensorTypeZh}: ${alert.currentValue} > ${alert.threshold}',
    );
    notifyListeners();
  }

  void _onSafetyAlarm(SafetyAlarm alarm) {
    _latestSafetyAlarm = alarm;
    if (!alarm.active) return;
    _playAlertSound();
    _addMessage(
      '[安全告警] ${alarm.typeZh}${alarm.message.isEmpty ? '' : ': ${alarm.message}'}',
    );
    notifyListeners();
  }

  void _onTrackingStatus(TrackingStatus tracking) {
    _latestTracking = tracking;
    if (tracking.event == 'tracking_started') {
      _addMessage('[跟踪] 已启动');
    } else if (tracking.event == 'target_lost') {
      _addMessage('[跟踪] 目标丢失');
    } else if (tracking.event == 'tracking_stopped') {
      _addMessage('[跟踪] 已停止');
    }
    notifyListeners();
  }

  void _onRemoteSnapshot(CloudSnapshot snapshot) {
    if (snapshot.ok) {
      _imageFrameEvents.add(snapshot.imageBase64);
      _addMessage('[远程截图] 已接收${snapshot.annotated ? "标注" : "原始"}画面');
    } else {
      _addMessage('[远程截图] 失败: ${snapshot.error}');
    }
    notifyListeners();
  }

  void _addMessage(String msg) {
    final time = DateTime.now();
    final ts =
        '${time.hour.toString().padLeft(2, '0')}:${time.minute.toString().padLeft(2, '0')}:${time.second.toString().padLeft(2, '0')}';
    _messages.add('[$ts] $msg');
    if (_messages.length > 200) {
      _messages.removeRange(0, _messages.length - 200);
    }
  }

  /// 公开的日志写入接口，供页面层调用
  void addMessage(String msg) => _addMessage(msg);

  @override
  void dispose() {
    _service.dispose();
    unawaited(_cloudService.dispose());
    unawaited(_parseTaskEvents.close());
    unawaited(_reportEvents.close());
    unawaited(_llmCommandEvents.close());
    unawaited(_imageFrameEvents.close());
    super.dispose();
  }
}
