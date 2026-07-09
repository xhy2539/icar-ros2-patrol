# APP 控制改造指南

> 供李雨晨修改 `lib/pages/control_page.dart` 和 `lib/services/car_controller.dart`

## 一、长按移动，松手停止

每个方向按钮，`onTap` 改为 `onTapDown`/`onTapUp`：

```dart
// 之前
onTap: () => _sendCommand('forward'),

// 之后
onTapDown: (_) => _sendCommand('forward'),   // 按下 → 前进
onTapUp: (_) => _sendCommand('stop'),         // 松手 → 停止
onTapCancel: (_) => _sendCommand('stop'),     // 滑出 → 停止
```

## 二、多指令并行（前进同时转弯）

### 原理

多个按钮可以同时按住，APP 端合并为一条 `motion` 指令发给小车：

```
按住"前进" + 按住"左转" → motion:sx:0.4:sy:0:sz:0.3 → 前进+左转
松手"前进" → motion:sx:0:sy:0:sz:0.3 → 只剩左转
松手"左转" → stop → 全停
```

### 方向分类

| 组 | 按钮 | 互斥 |
|----|------|------|
| 前后 | `forward` / `backward` | 同一时间只能一个 |
| 平移 | `left` / `right` | 同一时间只能一个 |
| 旋转 | `turn_left` / `turn_right` | 同一时间只能一个 |

**不同组可以组合**：前进+左转 ✅，后退+右平移 ✅。

### 实现

```dart
// CarController 新增
String _activeFb = '';     // forward/backward
String _activeStrafe = ''; // left/right  
String _activeTurn = '';   // turn_left/turn_right

void pressCommand(String cmd) {
  // 更新活跃方向
  switch (cmd) {
    case 'forward': case 'backward':
      _activeFb = cmd; break;
    case 'left': case 'right':
      _activeStrafe = cmd; break;
    case 'turn_left': case 'turn_right':
      _activeTurn = cmd; break;
  }
  _sendMotion();
}

void releaseCommand(String cmd) {
  // 清除方向
  if (cmd == _activeFb) _activeFb = '';
  if (cmd == _activeStrafe) _activeStrafe = '';
  if (cmd == _activeTurn) _activeTurn = '';
  _sendMotion();
}

void _sendMotion() {
  double sx = 0, sy = 0, sz = 0;
  
  if (_activeFb == 'forward') sx = _speed;
  if (_activeFb == 'backward') sx = -_speed;
  if (_activeStrafe == 'left') sy = _speed;
  if (_activeStrafe == 'right') sy = -_speed;
  if (_activeTurn == 'turn_left') sz = _speed * 0.8;
  if (_activeTurn == 'turn_right') sz = -_speed * 0.8;
  
  if (sx == 0 && sy == 0 && sz == 0) {
    sendCommand('stop');
  } else {
    sendCommand('motion:${sx.toStringAsFixed(2)}:${sy.toStringAsFixed(2)}:${sz.toStringAsFixed(2)}');
  }
}
```

### 按钮改造

```dart
GestureDetector(
  onTapDown: (_) => _ctrl.pressCommand('forward'),
  onTapUp: (_) => _ctrl.releaseCommand('forward'),
  onTapCancel: (_) => _ctrl.releaseCommand('forward'),
  child: ...按钮...
)
```

## 三、速度控制

速度滑块已有，改为实时生效：

```dart
// speed slider onChanged:
onChanged: (value) {
  _ctrl.speed = value;
  _ctrl._sendMotion();  // 立刻更新运动指令
}
```

APP 发送 `speed:N` 同步到小车，范围 10-100。

## 四、小车端支持（熊浩宇）

小车 `app.py` 需新增 `motion` 指令，已在车上部署：

```python
elif cmd.startswith("motion:"):
    # 格式: motion:sx:0.4:sy:0:sz:-0.3
    parts = cmd.split(":")[1:]
    sx, sy, sz = float(parts[0]), float(parts[1]), float(parts[2])
    if sx == 0 and sy == 0 and sz == 0:
        myApp.g_bot.set_car_run(7, 100, adjust=False)
    else:
        myApp.g_bot.set_car_motion(sx, sy, sz)
```

## 五、完整指令表

| 指令 | 小车动作 | 说明 |
|------|---------|------|
| `forward` | 前进 | 单指令 |
| `backward` | 后退 | 单指令 |
| `left` | 左平移 | 单指令 |
| `right` | 右平移 | 单指令 |
| `turn_left` | 原地左转 | 单指令 |
| `turn_right` | 原地右转 | 单指令 |
| `stop` | 停止 | 清空所有运动 |
| `motion:sx:0.4:sy:0:sz:0` | 组合运动 | sx=前后 sy=平移 sz=旋转 |
| `speed:40` | 调速 | 范围 10-100 |

## 六、改造清单

| 文件 | 改动 |
|------|------|
| `control_page.dart` | 按钮改成 `onTapDown`/`onTapUp`，调用 `pressCommand`/`releaseCommand` |
| `car_controller.dart` | 新增 `pressCommand`/`releaseCommand`/`_sendMotion`，维护活跃方向状态 |
| `car_tcp_service.dart` | 发送 motion 指令格式 |

> 小车端 `app.py` 已部署完成，APP 改造完成后直接联调。
