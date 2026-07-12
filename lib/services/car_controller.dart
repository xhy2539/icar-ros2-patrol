import 'dart:async';
import 'package:flutter/foundation.dart';
import 'car_tcp_service.dart';
import 'car_commands.dart';
import 'vision_models.dart';

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
    _service.onStateChanged = _onStateChanged;
    _service.onError = _onError;
    _service.onLog = _onLog;
    _service.responseStream.listen(_onResponse);
    _service.detectionStream.listen(_onDetection);
    _service.captureStatusStream.listen(_onCaptureStatus);
    _service.parseTaskStream.listen(_onParseTaskResult);
    _service.reportStream.listen(_onReportResult);
  }

  final CarWebSocketService _service = CarWebSocketService();

  // ═══════════════════════════════════════════
  // 状态（UI 可直接读取）
  // ═══════════════════════════════════════════

  /// 连接状态
  CarConnectionState get connectionState => _service.state;
  bool get isConnected => _service.isConnected;

  /// 当前 IP
  String get host => _host;
  String _host = '192.168.137.218';

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

  /// 从设置页批量更新配置
  ///
  /// 如果当前未连接，只保存配置；如果已连接且 IP/端口变化，会断开旧连接并用新地址重连。
  Future<void> updateSettings({
    String? host,
    int? port,
    double? speed,
    bool? autoReconnect,
    bool? hapticEnabled,
  }) async {
    bool needReconnect = false;

    if (host != null && host.isNotEmpty && host != _host) {
      _host = host;
      needReconnect = true;
    }
    if (port != null && port != _port) {
      _port = port;
      needReconnect = true;
    }
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

    // 如果已连接且地址变了，重连
    if (needReconnect && isConnected) {
      await disconnect();
      await connect(_host, _port);
    }

    notifyListeners();
  }

  // ═══════════════════════════════════════════
  // 视觉状态
  // ═══════════════════════════════════════════

  /// 最新检测结果
  DetectionArray _latestDetections = DetectionArray(detections: []);
  DetectionArray get latestDetections => _latestDetections;

  /// 最新截图状态
  CaptureStatus? _latestCaptureStatus;
  CaptureStatus? get latestCaptureStatus => _latestCaptureStatus;

  /// 视觉检测流
  Stream<DetectionArray> get detectionStream => _service.detectionStream;

  /// 截图状态流
  Stream<CaptureStatus> get captureStatusStream =>
      _service.captureStatusStream;

  /// 摄像头帧流（base64 JPEG）
  Stream<String> get imageFrameStream => _service.imageFrameStream;

  // ═══════════════════════════════════════════
  // LLM 状态
  // ═══════════════════════════════════════════

  /// LLM parse_task 流
  Stream<Map<String, dynamic>> get parseTaskStream =>
      _service.parseTaskStream;

  /// LLM generate_report 流
  Stream<Map<String, dynamic>> get reportStream => _service.reportStream;

  /// 最新 parse_task 结果
  Map<String, dynamic>? _latestParseResult;
  Map<String, dynamic>? get latestParseResult => _latestParseResult;

  /// 最新巡检报告
  String _latestReport = '';
  String get latestReport => _latestReport;

  /// LLM 请求是否正在等待响应
  bool _llmLoading = false;
  bool get llmLoading => _llmLoading;

  // ═══════════════════════════════════════════
  // URL 工具（供 UI 使用）
  // ═══════════════════════════════════════════

  /// 摄像头视频流 URL
  String get videoUrl => CarWebSocketService.buildVideoUrl(_host, _port);

  /// YOLO 视频流 URL
  String get yoloVideoUrl => CarWebSocketService.buildYoloVideoUrl(_host, _port);

  /// 带标注的视频流 URL（YOLO 检测框叠加）
  String get annotatedVideoUrl => yoloVideoUrl;

  /// WebSocket 连接 URL
  String get wsUrl => _service.buildWsUrl(_host, _port);

  // ═══════════════════════════════════════════
  // 操作
  // ═══════════════════════════════════════════

  /// 连接小车
  Future<bool> connect([String? host, int? port]) async {
    _host = host ?? _host;
    _port = port ?? _port;

    if (_autoReconnect) {
      _service.enableAutoReconnect();
    }

    _addMessage('正在连接 ${_service.buildWsUrl(_host, _port)} ...');
    final ok = await _service.connect(_host, _port);

    if (ok) {
      _currentAction = '已连接';
      _addMessage('WebSocket 连接成功');
      // 自动订阅视觉 Topic
      _service.subscribeVisionTopics();
      _addMessage('已订阅视觉 Topic (detections, capture_status, camera)');
    } else {
      _currentAction = '连接失败';
      _addMessage('WebSocket 连接失败');
    }

    notifyListeners();
    return ok;
  }

  /// 断开连接
  Future<void> disconnect() async {
    await _service.disconnect();
    _currentAction = '待机';
    _currentDirection = '';
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
    if (!isConnected) {
      _addMessage('未连接，无法发送指令');
      notifyListeners();
      return false;
    }

    // 发送纯文本指令
    final cmd = CarCommands.fromDirection(direction);
    final ok = _service.send(cmd);

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
    if (!isConnected) return false;
    // TODO: 确认是否有专用归位指令，当前发 stop
    final ok = _service.send(CarCommands.stop);
    if (ok) _addMessage('自动归位指令已发送');
    notifyListeners();
    return ok;
  }

  /// 发送截图（单次）
  bool sendScreenshot() {
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
    if (!isConnected) {
      _addMessage('未连接，无法发送截图命令');
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
    if (!isConnected) return false;
    // TODO: 确认录制指令
    final ok = _service.send('record');
    if (ok) _addMessage('录制指令已发送');
    notifyListeners();
    return ok;
  }

  /// 发送 LLM parse_task 请求（自然语言 → 结构化任务 JSON）
  bool sendParseTask(String inputText) {
    if (!isConnected) {
      _addMessage('未连接，无法发送 LLM 请求');
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

  /// 发送 LLM generate_report 请求（任务日志 → 巡检报告）
  bool sendGenerateReport(String taskId) {
    if (!isConnected) {
      _addMessage('未连接，无法生成报告');
      notifyListeners();
      return false;
    }
    _llmLoading = true;
    _addMessage('[LLM] 请求生成报告: task_id=$taskId');
    final ok = _service.sendJson({
      'action': 'generate_report',
      'task_id': taskId,
    });
    if (!ok) {
      _llmLoading = false;
    }
    notifyListeners();
    return ok;
  }

  /// 发送已解析的任务给 task_manager（/task/request）
  bool sendParsedTaskToManager(Map<String, dynamic> taskJson) {
    if (!isConnected) return false;
    _addMessage('[LLM] 发送任务到 task_manager: ${taskJson['task_type']}');
    final ok = _service.sendJson({
      'action': 'task_request',
      'task': taskJson,
    });
    if (ok) {
      _currentAction = '任务下发中';
    }
    notifyListeners();
    return ok;
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
        _addMessage('[状态] → 已连接 (ws://$_host:$_port)');
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

  void _addMessage(String msg) {
    final time = DateTime.now();
    final ts =
        '${time.hour.toString().padLeft(2, '0')}:${time.minute.toString().padLeft(2, '0')}:${time.second.toString().padLeft(2, '0')}';
    _messages.add('[$ts] $msg');
    if (_messages.length > 200) {
      _messages.removeRange(0, _messages.length - 200);
    }
  }

  @override
  void dispose() {
    _service.dispose();
    super.dispose();
  }
}
