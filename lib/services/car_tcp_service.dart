import 'dart:async';
import 'package:web_socket_channel/web_socket_channel.dart';

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
/// await service.connect('10.90.164.83');
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

  /// 接收到的响应数据流
  Stream<String> get responseStream => _responseController.stream;

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

  // ═══════════════════════════════════════════
  // 数据接收
  // ═══════════════════════════════════════════

  void _onMessage(dynamic data) {
    final raw = data.toString().trim();
    onLog?.call('← 收到消息: "$raw" (类型=${data.runtimeType}, 长度=${raw.length})');
    if (raw.isNotEmpty) {
      _responseController.add(raw);
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
  }
}
