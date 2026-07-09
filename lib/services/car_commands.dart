/// iCar 小车控制指令定义
///
/// 通信协议：WebSocket 纯文本指令
/// 连接地址：`ws://<小车IP>:6500/ws/control`
///
/// 指令列表（来自 app.py + APP接入指南.md 确认）：
///   forward  - 前进
///   backward - 后退
///   left     - 左转
///   right    - 右转
///   stop     - 停止
///   start    - 启动
library;

class CarCommands {
  CarCommands._();

  /// 前进指令
  static const String forward = 'forward';

  /// 后退指令
  static const String backward = 'backward';

  /// 左转指令
  static const String left = 'left';

  /// 右转指令
  static const String right = 'right';

  /// 停止指令
  static const String stop = 'stop';

  /// 启动指令
  static const String start = 'start';

  /// 根据方向名获取指令字符串
  ///
  /// [direction] 方向: 'forward' / 'backward' / 'left' / 'right' / 'stop'
  static String fromDirection(String direction) {
    switch (direction) {
      case 'forward':
        return forward;
      case 'backward':
        return backward;
      case 'left':
        return left;
      case 'right':
        return right;
      case 'stop':
        return stop;
      default:
        return stop;
    }
  }

  /// 获取所有可用指令
  static List<String> get all =>
      [forward, backward, left, right, stop, start];
}
