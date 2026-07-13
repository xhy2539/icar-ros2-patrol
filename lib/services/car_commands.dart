/// iCar 小车控制指令定义
///
/// 通信协议：WebSocket 纯文本指令
/// 连接地址：`ws://<小车IP>:6500/ws/control`
///
/// 指令列表：
///   forward   - 前进
///   backward  - 后退
///   left      - 左平移（麦轮横移）
///   right     - 右平移（麦轮横移）
///   turn_left - 左转（原地旋转）← 待确认指令名
///   turn_right- 右转（原地旋转）← 待确认指令名
///   stop      - 停止
///   start     - 启动
library;

class CarCommands {
  CarCommands._();

  /// 前进指令
  static const String forward = 'forward';

  /// 后退指令
  static const String backward = 'backward';

  /// 左平移指令（麦轮横移）
  static const String left = 'left';

  /// 右平移指令（麦轮横移）
  static const String right = 'right';

  /// 左转指令（原地旋转）— 指令名待确认
  static const String turnLeft = 'turn_left';

  /// 右转指令（原地旋转）— 指令名待确认
  static const String turnRight = 'turn_right';

  /// 停止指令
  static const String stop = 'stop';

  /// 启动指令
  static const String start = 'start';

  /// 根据方向名获取指令字符串
  ///
  /// [direction] 方向: 'forward' / 'backward' / 'left' / 'right' /
  ///                   'turn_left' / 'turn_right' / 'stop'
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
      case 'turn_left':
        return turnLeft;
      case 'turn_right':
        return turnRight;
      case 'stop':
        return stop;
      default:
        return stop;
    }
  }

  /// 获取所有可用指令
  static List<String> get all => [
    forward,
    backward,
    left,
    right,
    turnLeft,
    turnRight,
    stop,
    start,
  ];
}
