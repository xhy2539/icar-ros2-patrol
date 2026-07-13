import 'dart:async';
import 'dart:convert';
import 'package:web_socket_channel/web_socket_channel.dart';
import 'vision_models.dart';

/// 小车连接状态
enum CarConnectionState {
  disconnected,
  connecting,
  connected,
  error,
}

/// iCar 小车 WebSocket 通信服务
///
/// 通过 WebSocket 与小车 app.py Flask 后端通信。
/// 连接地址: `ws://<IP>:6500/ws/control`
/// 视频流:   `http://<IP>:6500/video_feed`
///
/// 用法：
/// ```dart
/// final service = CarWebSocketService();
/// await service.connect('192.168.137.117');
/// service.send('forward');
/// ```
class CarWebSocketService {
  // ═══════════════════════════════════════════
  // 配置
  // ═══════════════════════════════════════════

  /// 默认端口
  static const int defaultPort = 6500;

  /// WebSocket 路径
  static const String wsPath = '/ws/control';

  /// 连接超时（秒）
  static const int connectTimeoutSec = 5;

  /// 自动重连间隔（秒）
  static const int reconnectIntervalSec = 3;

  /// 最大重连次数（0 = 无限重连）
  static const int maxReconnectAttempts = 5;

  // ═══════════════════════════════════════════
  // 内部状态
  // ═══════════════════════════════════════════

  WebSocketChannel? _channel;
  StreamSubscription? _subscription;
  String _host = '';
  int _port = defaultPort;

  CarConnectionState _state = CarConnectionState.disconnected;
  CarConnectionState get state => _state;
  bool get isConnected => _state == CarConnectionState.connected;

  bool _autoReconnect = false;
  int _reconnectAttempts = 0;
  Timer? _reconnectTimer;

  /// 接收数据的 StreamController
  final _responseController = StreamController<String>.broadcast();

  /// 视觉检测结果流
  final _detectionController = StreamController<DetectionArray>.broadcast();

  /// 截图状态流
  final _captureStatusController = StreamController<CaptureStatus>.broadcast();

  /// 摄像头帧流（base64 编码的 JPEG）
  final _imageFrameController = StreamController<String>.broadcast();

  /// LLM parse_task 结果流
  final _parseTaskController = StreamController<Map<String, dynamic>>.broadcast();

  /// LLM generate_report 结果流
  final _reportController = StreamController<Map<String, dynamic>>.broadcast();

  /// ROS2 状态流（桥接节点推送）
  final _obstacleController = StreamController<Map<String, dynamic>>.broadcast();
  final _navStatusController = StreamController<Map<String, dynamic>>.broadcast();
  final _taskStatusController = StreamController<Map<String, dynamic>>.broadcast();
  final _taskLogController = StreamController<Map<String, dynamic>>.broadcast();
  final _sensorEnvController = StreamController<Map<String, dynamic>>.broadcast();
  final _sensorAlertController = StreamController<Map<String, dynamic>>.broadcast();
  final _trackingStatusController = StreamController<Map<String, dynamic>>.broadcast();

  /// 接收到的响应数据流
  Stream<String> get responseStream => _responseController.stream;

  /// 视觉检测结果流
  Stream<DetectionArray> get detectionStream => _detectionController.stream;

  /// 截图状态流
  Stream<CaptureStatus> get captureStatusStream =>
      _captureStatusController.stream;

  /// 摄像头帧流
  Stream<String> get imageFrameStream => _imageFrameController.stream;

  /// LLM parse_task 结果流
  Stream<Map<String, dynamic>> get parseTaskStream =>
      _parseTaskController.stream;

  /// LLM generate_report 结果流
  Stream<Map<String, dynamic>> get reportStream => _reportController.stream;

  Stream<Map<String, dynamic>> get obstacleStream => _obstacleController.stream;
  Stream<Map<String, dynamic>> get navStatusStream => _navStatusController.stream;
  Stream<Map<String, dynamic>> get taskStatusStream => _taskStatusController.stream;
  Stream<Map<String, dynamic>> get taskLogStream => _taskLogController.stream;
  Stream<Map<String, dynamic>> get sensorEnvStream => _sensorEnvController.stream;
  Stream<Map<String, dynamic>> get sensorAlertStream => _sensorAlertController.stream;
  Stream<Map<String, dynamic>> get trackingStatusStream => _trackingStatusController.stream;

  /// 状态变更回调
  void Function(CarConnectionState)? onStateChanged;

  /// 错误回调
  void Function(String)? onError;

  /// 调试日志回调（非错误信息）
  void Function(String)? onLog;

  // ═══════════════════════════════════════════
  // URL 构建
  // ═══════════════════════════════════════════

  /// 构建 WebSocket URL
  String buildWsUrl(String host, [int port = defaultPort]) {
    return 'ws://$host:$port$wsPath';
  }

  /// 构建视频流 URL
  static String buildVideoUrl(String host, [int port = defaultPort]) {
    return 'http://$host:$port/video_feed';
  }

  /// 构建 YOLO 视频流 URL
  static String buildYoloVideoUrl(String host, [int port = defaultPort]) {
    return 'http://$host:$port/yolo_video_feed';
  }

  /// 构建 YOLO 状态接口 URL
  static String buildYoloStatusUrl(String host, [int port = defaultPort]) {
    return 'http://$host:$port/yolo_detailed_status';
  }

  // ═══════════════════════════════════════════
  // 连接管理
  // ═══════════════════════════════════════════

  /// 连接到小车 WebSocket
  Future<bool> connect(String host, [int port = defaultPort]) async {
    final url = buildWsUrl(host, port);
    onLog?.call('connect() 被调用, url=$url, 当前状态=$_state');

    if (_state == CarConnectionState.connected ||
        _state == CarConnectionState.connecting) {
      onLog?.call('当前已连接/连接中，跳过');
      return true;
    }

    _host = host;
    _port = port;
    _setState(CarConnectionState.connecting);

    try {
      onLog?.call('正在创建 WebSocketChannel...');
      final uri = Uri.parse(url);
      _channel = WebSocketChannel.connect(uri);
      onLog?.call('WebSocketChannel 已创建, 等待握手...');

      // 等待连接就绪
      await _channel!.ready.timeout(
        Duration(seconds: connectTimeoutSec),
        onTimeout: () {
          throw TimeoutException('WebSocket 连接超时 (${connectTimeoutSec}s)');
        },
      );
      onLog?.call('握手完成 (ready), channel=$url');

      // 监听消息
      _subscription = _channel!.stream.listen(
        _onMessage,
        onError: _onWsError,
        onDone: _onWsDone,
        cancelOnError: false,
      );
      onLog?.call('消息监听已启动');

      _reconnectAttempts = 0;
      _setState(CarConnectionState.connected);
      return true;
    } catch (e) {
      onLog?.call('connect() 抛异常: $e');
      _setState(CarConnectionState.error);
      onError?.call('连接失败: $e');
      _tryReconnect();
      return false;
    }
  }

  /// 断开连接
  Future<void> disconnect() async {
    onLog?.call('disconnect() 被调用, 当前状态=$_state');
    _autoReconnect = false;
    _cancelReconnect();

    try {
      await _subscription?.cancel();
      _subscription = null;
      await _channel?.sink.close();
      onLog?.call('WebSocket sink 已关闭');
    } catch (e) {
      onLog?.call('disconnect() 异常: $e');
    }

    _channel = null;
    _setState(CarConnectionState.disconnected);
  }

  /// 启用自动重连
  void enableAutoReconnect() {
    _autoReconnect = true;
  }

  /// 禁用自动重连
  void disableAutoReconnect() {
    _autoReconnect = false;
    _cancelReconnect();
  }

  // ═══════════════════════════════════════════
  // 数据发送
  // ═══════════════════════════════════════════

  /// 发送文本指令
  bool send(String command) {
    if (!isConnected || _channel == null) {
      onError?.call('未连接，无法发送指令 (状态=$_state, channel=${_channel != null ? "非null" : "null"})');
      return false;
    }

    try {
      _channel!.sink.add(command);
      onLog?.call('→ 已发送: "$command" (${command.length} 字符)');
      return true;
    } catch (e) {
      onError?.call('发送失败: $e');
      return false;
    }
  }

  /// 发送 JSON 数据
  bool sendJson(Map<String, dynamic> data) {
    final jsonStr = jsonEncode(data);
    if (!isConnected || _channel == null) {
      onError?.call('未连接，无法发送 JSON');
      return false;
    }
    try {
      _channel!.sink.add(jsonStr);
      onLog?.call('→ JSON: $jsonStr');
      return true;
    } catch (e) {
      onError?.call('JSON 发送失败: $e');
      return false;
    }
  }

  /// 订阅视觉 Topic
  ///
  /// 向后端发送订阅请求。后端收到后应开始推送对应 Topic 的数据。
  /// 支持的 topic: detections, capture_status, camera, detections_json
  bool subscribeTopic(String topic) {
    return sendJson({'subscribe': topic});
  }

  /// 订阅所有视觉相关 Topic（连接成功后调用）
  void subscribeVisionTopics() {
    subscribeTopic('detections');
    subscribeTopic('capture_status');
  }

  /// 订阅车端 ROS2 状态。视频仍通过独立 MJPEG HTTP 流传输。
  void subscribeBridgeTopics() {
    for (final topic in const [
      'obstacle_status',
      'nav_status',
      'task_status',
      'task_log',
      'sensor_env_data',
      'sensor_alert',
      'tracking_status',
      'detections',
      'capture_status',
    ]) {
      subscribeTopic(topic);
    }
  }

  // ═══════════════════════════════════════════
  // 数据接收
  // ═══════════════════════════════════════════

  void _onMessage(dynamic data) {
    // 二进制帧 → 当作摄像头帧（base64）
    if (data is List<int>) {
      final b64 = base64Encode(data);
      _imageFrameController.add(b64);
      onLog?.call('← 收到二进制帧 (${data.length} bytes)');
      return;
    }

    final raw = data.toString().trim();
    if (raw.isEmpty) return;

    // 尝试 JSON 解析并按 topic 路由
    try {
      if (raw.startsWith('{')) {
        final json = jsonDecode(raw) as Map<String, dynamic>;
        final topic = json['topic']?.toString() ?? '';
        if (_routeJsonMessage(topic, json)) {
          return; // 已路由到专用流，不再进入 responseStream
        }
      }
    } catch (_) {
      // 非 JSON，走原有 responseStream
    }

    onLog?.call('← 收到消息: "$raw" (类型=${data.runtimeType}, 长度=${raw.length})');
    _responseController.add(raw);
  }

  /// 路由 JSON 消息到专用流，返回 true 表示已处理
  bool _routeJsonMessage(String topic, Map<String, dynamic> json) {
    switch (topic) {
      case 'detections':
      case '/vision/detections':
        _detectionController.add(DetectionArray.fromJson(json));
        return true;
      case 'capture_status':
      case '/vision/capture_status':
        _captureStatusController.add(CaptureStatus.fromJson(json));
        return true;
      case 'camera':
      case '/camera/color/image_raw':
        final b64 = json['data']?.toString() ?? '';
        if (b64.isNotEmpty) _imageFrameController.add(b64);
        return true;
      case 'detections_json':
      case '/vision/detections_json':
        onLog?.call('← [调试JSON] $json');
        _responseController.add('[vision_debug] $json');
        return true;
      case 'parse_task_result':
      case '/llm/parse_task':
        _parseTaskController.add(json);
        onLog?.call('← [LLM] parse_task 结果: success=${json['success']}');
        return true;
      case 'generate_report_result':
      case '/llm/generate_report':
        _reportController.add(json);
        onLog?.call('← [LLM] generate_report 结果: success=${json['success']}');
        return true;
      case 'obstacle_status':
        _obstacleController.add(json);
        return true;
      case 'nav_status':
        _navStatusController.add(json);
        return true;
      case 'task_status':
        _taskStatusController.add(json);
        return true;
      case 'task_log':
        _taskLogController.add(json);
        return true;
      case 'sensor_env_data':
        _sensorEnvController.add(json);
        return true;
      case 'sensor_alert':
        _sensorAlertController.add(json);
        return true;
      case 'tracking_status':
        _trackingStatusController.add(json);
        return true;
      case 'subscription':
      case 'command_ack':
        onLog?.call('← $json');
        return true;
      case 'error':
        onError?.call(json['error']?.toString() ?? '车端返回未知错误');
        return true;
      default:
        return false;
    }
  }

  void _onWsError(Object error) {
    onLog?.call('stream.onError 触发: $error (类型=${error.runtimeType})');
    onError?.call('WebSocket 错误: $error');
    _setState(CarConnectionState.error);
  }

  void _onWsDone() {
    onLog?.call('stream.onDone 触发 — 服务端关闭了连接 (当前状态=$_state)');
    _subscription = null;
    _channel = null;

    if (_state != CarConnectionState.disconnected) {
      _setState(CarConnectionState.disconnected);
      _tryReconnect();
    }
  }

  // ═══════════════════════════════════════════
  // 自动重连
  // ═══════════════════════════════════════════

  void _tryReconnect() {
    onLog?.call('_tryReconnect() autoReconnect=$_autoReconnect, attempts=$_reconnectAttempts/$maxReconnectAttempts');
    if (!_autoReconnect) {
      onLog?.call('自动重连已关闭，跳过');
      return;
    }
    if (_state == CarConnectionState.connecting) {
      onLog?.call('正在连接中，跳过重连');
      return;
    }
    if (maxReconnectAttempts > 0 &&
        _reconnectAttempts >= maxReconnectAttempts) {
      onError?.call('重连次数已达上限 ($maxReconnectAttempts)，停止重连');
      return;
    }

    _reconnectAttempts++;
    onError?.call('第 $_reconnectAttempts 次重连 (${reconnectIntervalSec}s 后)...');

    _reconnectTimer = Timer(
      Duration(seconds: reconnectIntervalSec),
      () {
        onLog?.call('重连定时器触发，开始重新 connect()');
        connect(_host, _port);
      },
    );
  }

  void _cancelReconnect() {
    _reconnectTimer?.cancel();
    _reconnectTimer = null;
    _reconnectAttempts = 0;
  }

  // ═══════════════════════════════════════════
  // 状态管理
  // ═══════════════════════════════════════════

  void _setState(CarConnectionState newState) {
    if (_state == newState) return;
    final old = _state;
    _state = newState;
    onLog?.call('状态变更: $old → $newState');
    onStateChanged?.call(newState);
  }

  // ═══════════════════════════════════════════
  // 释放
  // ═══════════════════════════════════════════

  /// 释放所有资源
  Future<void> dispose() async {
    await disconnect();
    await _responseController.close();
    await _detectionController.close();
    await _captureStatusController.close();
    await _imageFrameController.close();
    await _parseTaskController.close();
    await _reportController.close();
    await _obstacleController.close();
    await _navStatusController.close();
    await _taskStatusController.close();
    await _taskLogController.close();
    await _sensorEnvController.close();
    await _sensorAlertController.close();
    await _trackingStatusController.close();
  }
}
