import 'dart:async';
import 'package:flutter/foundation.dart';
import 'car_tcp_service.dart';
import 'car_commands.dart';

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
  String _host = '10.90.164.83';

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

  // ═══════════════════════════════════════════
  // URL 工具（供 UI 使用）
  // ═══════════════════════════════════════════

  /// 摄像头视频流 URL
  String get videoUrl => CarWebSocketService.buildVideoUrl(_host, _port);

  /// YOLO 视频流 URL
  String get yoloVideoUrl => CarWebSocketService.buildYoloVideoUrl(_host, _port);

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

  /// 发送截图
  bool sendScreenshot() {
    if (!isConnected) return false;
    // TODO: 确认截图指令
    final ok = _service.send('screenshot');
    if (ok) _addMessage('截图指令已发送');
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
    _addMessage('[收到] $raw');
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
