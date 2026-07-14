import 'dart:async';

import 'package:flutter/material.dart';
import 'package:flutter/services.dart';
import '../theme/app_theme.dart';
import '../services/car_controller.dart';
import '../services/car_tcp_service.dart';

class ControlPage extends StatefulWidget {
  const ControlPage({super.key});

  @override
  State<ControlPage> createState() => _ControlPageState();
}

class _ControlPageState extends State<ControlPage> with WidgetsBindingObserver {
  final CarController _ctrl = CarController.instance;
  late TextEditingController _ipController;

  /// 当前激活中的运动方向（空 = 未运动）
  String _activeDirection = '';
  Timer? _motionHeartbeat;

  @override
  void initState() {
    super.initState();
    WidgetsBinding.instance.addObserver(this);
    _ipController = TextEditingController(text: _ctrl.host);
    _ctrl.addListener(_onControllerChanged);
  }

  @override
  void dispose() {
    _motionHeartbeat?.cancel();
    if (_ctrl.isConnected) {
      _ctrl.sendCommand('stop');
    }
    WidgetsBinding.instance.removeObserver(this);
    _ctrl.removeListener(_onControllerChanged);
    _ipController.dispose();
    super.dispose();
  }

  @override
  void didChangeAppLifecycleState(AppLifecycleState state) {
    if (state != AppLifecycleState.resumed) {
      _stopMotion(sendStop: true);
    }
  }

  void _onControllerChanged() {
    final endpoint = _ctrl.isCloudMode ? _ctrl.mqttHost : _ctrl.host;
    if (_ipController.text != endpoint) {
      _ipController.text = endpoint;
    }
    if (mounted) setState(() {});
  }

  void _toggleConnection() {
    if (_ctrl.isConnected) {
      _ctrl.disconnect();
    } else if (_ctrl.isCloudMode) {
      _ctrl.connect();
    } else {
      _ctrl.connect(_ipController.text.trim());
    }
    HapticFeedback.mediumImpact();
  }

  /// 按下方向键：发送方向指令，持续运动
  void _onPress(String direction) {
    if (!_ctrl.canManualControl) {
      ScaffoldMessenger.of(context).showSnackBar(
        SnackBar(
          content: Text(
            _ctrl.isCloudMode && _ctrl.isConnected
                ? '云端已连接，但小车云桥尚未上线'
                : '请先连接小车',
          ),
          backgroundColor: AppColors.orange,
          duration: Duration(seconds: 1),
        ),
      );
      return;
    }
    if (!_ctrl.sendCommand(direction)) return;
    setState(() => _activeDirection = direction);
    _motionHeartbeat?.cancel();
    // 与网页一致：车端看门狗要求长按期间持续续租。
    _motionHeartbeat = Timer.periodic(const Duration(milliseconds: 100), (_) {
      if (_activeDirection.isNotEmpty && _ctrl.canManualControl) {
        _ctrl.sendCommand(_activeDirection);
      }
    });
    HapticFeedback.heavyImpact();
  }

  /// 松开方向键：发送 stop
  void _onRelease() {
    if (_activeDirection.isEmpty) return;
    _stopMotion(sendStop: true);
    HapticFeedback.lightImpact();
  }

  /// 单次点击 stop
  void _onStop() {
    _stopMotion(sendStop: true);
    HapticFeedback.heavyImpact();
  }

  void _stopMotion({required bool sendStop}) {
    _motionHeartbeat?.cancel();
    _motionHeartbeat = null;
    if (sendStop && _ctrl.isConnected) {
      _ctrl.sendCommand('stop');
    }
    if (_activeDirection.isNotEmpty && mounted) {
      setState(() => _activeDirection = '');
    } else {
      _activeDirection = '';
    }
  }

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      body: SafeArea(
        child: SingleChildScrollView(
          padding: const EdgeInsets.symmetric(vertical: 16),
          child: Column(
            children: [
              _buildConnectionBar(),
              _buildObstacleBanner(),
              const SizedBox(height: 16),
              _buildSpeedControl(),
              const SizedBox(height: 24),
              _buildDirectionPad(),
              const SizedBox(height: 24),
              _buildActionStatus(),
              const SizedBox(height: 24),
              _buildQuickActions(),
              // 通信日志
              if (_ctrl.messages.isNotEmpty) ...[
                const SizedBox(height: 24),
                _buildLogPanel(),
              ],
            ],
          ),
        ),
      ),
    );
  }

  Widget _buildConnectionBar() {
    final isConnecting = _ctrl.connectionState == CarConnectionState.connecting;
    final isConnected = _ctrl.isConnected;
    final isError = _ctrl.connectionState == CarConnectionState.error;

    String badgeText;
    Color badgeColor;
    if (isConnecting) {
      badgeText = '连接中';
      badgeColor = AppColors.warningOrange;
    } else if (isConnected && _ctrl.robotOnline) {
      badgeText = _ctrl.isCloudMode ? '远程已连接' : '已连接';
      badgeColor = AppColors.successGreen;
    } else if (isConnected && _ctrl.isCloudMode) {
      badgeText = '云已连/车离线';
      badgeColor = AppColors.warningOrange;
    } else if (isError) {
      badgeText = '连接错误';
      badgeColor = AppColors.errorRed;
    } else {
      badgeText = '未连接';
      badgeColor = AppColors.blueGray;
    }

    return AppCard(
      title: '连接状态',
      icon: _ctrl.isCloudMode ? Icons.cloud : Icons.wifi,
      child: Row(
        children: [
          StatusBadge(text: badgeText, color: badgeColor),
          const Spacer(),
          Expanded(
            flex: 2,
            child: TextField(
              controller: _ipController,
              style: const TextStyle(color: AppColors.darkNavy, fontSize: 14),
              decoration: InputDecoration(
                isDense: true,
                contentPadding: const EdgeInsets.symmetric(
                  horizontal: 12,
                  vertical: 10,
                ),
                hintText: _ctrl.isCloudMode ? 'MQTT 云服务器' : '小车 IP 地址',
                prefixIcon: const Icon(
                  Icons.dns,
                  size: 18,
                  color: AppColors.blueGray,
                ),
              ),
              enabled: !_ctrl.isCloudMode && !isConnected && !isConnecting,
            ),
          ),
          const SizedBox(width: 12),
          SizedBox(
            height: 42,
            child: ElevatedButton(
              onPressed: isConnecting ? null : _toggleConnection,
              style: ElevatedButton.styleFrom(
                backgroundColor: isConnected
                    ? AppColors.blueGray
                    : AppColors.orange,
                padding: const EdgeInsets.symmetric(horizontal: 20),
              ),
              child: isConnecting
                  ? const SizedBox(
                      width: 18,
                      height: 18,
                      child: CircularProgressIndicator(
                        strokeWidth: 2,
                        color: Colors.white,
                      ),
                    )
                  : Text(
                      isConnected ? '断开' : (_ctrl.isCloudMode ? '连云' : '连接'),
                    ),
            ),
          ),
        ],
      ),
    );
  }

  Widget _buildObstacleBanner() {
    final obs = _ctrl.latestObstacleStatus;
    if (!obs.isObstacle || obs.isSafe) return const SizedBox.shrink();

    final isDanger = obs.isDanger;

    if (isDanger) {
      HapticFeedback.vibrate();
    }

    return Container(
      margin: const EdgeInsets.symmetric(horizontal: 16, vertical: 4),
      padding: const EdgeInsets.symmetric(horizontal: 16, vertical: 10),
      decoration: BoxDecoration(
        color: isDanger
            ? AppColors.errorRed.withValues(alpha: 0.15)
            : AppColors.orange.withValues(alpha: 0.15),
        borderRadius: BorderRadius.circular(12),
        border: Border.all(
          color: isDanger ? AppColors.errorRed : AppColors.orange,
          width: 1.5,
        ),
      ),
      child: Row(
        children: [
          Icon(
            isDanger ? Icons.error : Icons.warning,
            color: isDanger ? AppColors.errorRed : AppColors.orange,
            size: 20,
          ),
          const SizedBox(width: 8),
          Expanded(
            child: Text(
              '${obs.directionZh} ${obs.minDistance.toStringAsFixed(1)}m 有障碍物${isDanger ? " — 紧急" : ""}',
              style: TextStyle(
                color: isDanger ? AppColors.errorRed : AppColors.orange,
                fontSize: 13,
                fontWeight: FontWeight.w600,
              ),
            ),
          ),
        ],
      ),
    );
  }

  Widget _buildSpeedControl() {
    return AppCard(
      title: '速度控制',
      icon: Icons.speed,
      child: Column(
        children: [
          Row(
            children: [
              const Icon(
                Icons.slow_motion_video,
                color: AppColors.blueGray,
                size: 20,
              ),
              Expanded(
                child: Slider(
                  value: _ctrl.speed,
                  min: 0.1,
                  max: 1.0,
                  divisions: 9,
                  label: '${(_ctrl.speed * 100).round()}%',
                  onChanged: (value) => _ctrl.speed = value,
                ),
              ),
              const Icon(Icons.flash_on, color: AppColors.orange, size: 20),
            ],
          ),
          const SizedBox(height: 4),
          Row(
            mainAxisAlignment: MainAxisAlignment.spaceBetween,
            children: [
              Text(
                '当前速度: ${(_ctrl.speed * 100).round()}%',
                style: const TextStyle(color: AppColors.darkNavy, fontSize: 14),
              ),
              Text(
                '${(_ctrl.speed * 0.45).toStringAsFixed(2)} m/s',
                style: const TextStyle(
                  color: AppColors.bluePurple,
                  fontSize: 14,
                  fontWeight: FontWeight.w600,
                ),
              ),
            ],
          ),
        ],
      ),
    );
  }

  Widget _buildDirectionPad() {
    return Container(
      margin: const EdgeInsets.symmetric(horizontal: 16),
      padding: const EdgeInsets.all(16),
      decoration: BoxDecoration(
        color: AppColors.surface,
        borderRadius: BorderRadius.circular(20),
        border: Border.all(color: AppColors.blueGray.withValues(alpha: 0.2)),
        boxShadow: [
          BoxShadow(
            color: Colors.black.withValues(alpha: 0.04),
            blurRadius: 8,
            offset: const Offset(0, 2),
          ),
        ],
      ),
      child: Column(
        children: [
          // 标题
          Row(
            mainAxisAlignment: MainAxisAlignment.center,
            children: [
              Icon(Icons.gamepad, color: AppColors.bluePurple, size: 20),
              const SizedBox(width: 8),
              const Text(
                '运动控制',
                style: TextStyle(
                  color: AppColors.bluePurple,
                  fontSize: 14,
                  fontWeight: FontWeight.w600,
                ),
              ),
            ],
          ),
          const SizedBox(height: 2),
          Text(
            '按住方向键运动，松手即停',
            style: TextStyle(
              color: AppColors.blueGray.withValues(alpha: 0.7),
              fontSize: 11,
            ),
          ),
          // ─── 移动区 ───
          const SizedBox(height: 12),
          _buildSectionLabel('移动', Icons.open_with),
          const SizedBox(height: 10),
          // 前进
          Center(
            child: _buildHoldButton(
              icon: Icons.arrow_upward,
              label: '前进',
              direction: 'forward',
              size: 60,
            ),
          ),
          const SizedBox(height: 6),
          // 左移 + 停止 + 右移
          Row(
            mainAxisAlignment: MainAxisAlignment.center,
            children: [
              _buildHoldButton(
                icon: Icons.arrow_back,
                label: '左移',
                direction: 'left',
                size: 56,
              ),
              const SizedBox(width: 10),
              _buildStopButton(),
              const SizedBox(width: 10),
              _buildHoldButton(
                icon: Icons.arrow_forward,
                label: '右移',
                direction: 'right',
                size: 56,
              ),
            ],
          ),
          const SizedBox(height: 6),
          // 后退
          Center(
            child: _buildHoldButton(
              icon: Icons.arrow_downward,
              label: '后退',
              direction: 'backward',
              size: 60,
            ),
          ),
          // ─── 分隔 ───
          const SizedBox(height: 16),
          Divider(color: AppColors.blueGray.withValues(alpha: 0.15)),
          const SizedBox(height: 12),
          // ─── 转向区 ───
          _buildSectionLabel('转向', Icons.rotate_90_degrees_ccw),
          const SizedBox(height: 10),
          Row(
            mainAxisAlignment: MainAxisAlignment.center,
            children: [
              _buildHoldButton(
                icon: Icons.rotate_left,
                label: '左转',
                direction: 'turn_left',
                size: 72,
                color: AppColors.bluePurple,
              ),
              const SizedBox(width: 24),
              _buildHoldButton(
                icon: Icons.rotate_right,
                label: '右转',
                direction: 'turn_right',
                size: 72,
                color: AppColors.bluePurple,
              ),
            ],
          ),
          // ─── 全停按钮 ───
          const SizedBox(height: 16),
          SizedBox(
            width: double.infinity,
            height: 44,
            child: ElevatedButton.icon(
              onPressed: _onStop,
              icon: const Icon(Icons.stop_circle, size: 20),
              label: const Text(
                '全部停止',
                style: TextStyle(fontSize: 14, fontWeight: FontWeight.w700),
              ),
              style: ElevatedButton.styleFrom(
                backgroundColor: AppColors.orange,
                foregroundColor: Colors.white,
                shape: RoundedRectangleBorder(
                  borderRadius: BorderRadius.circular(12),
                ),
              ),
            ),
          ),
        ],
      ),
    );
  }

  Widget _buildSectionLabel(String text, IconData icon) {
    return Row(
      mainAxisAlignment: MainAxisAlignment.center,
      children: [
        Icon(icon, color: AppColors.darkNavy, size: 14),
        const SizedBox(width: 4),
        Text(
          text,
          style: const TextStyle(
            color: AppColors.darkNavy,
            fontSize: 12,
            fontWeight: FontWeight.w600,
          ),
        ),
      ],
    );
  }

  /// 长按运动按钮：按下发送指令，松手发 stop
  Widget _buildHoldButton({
    required IconData icon,
    required String label,
    required String direction,
    double size = 72,
    Color? color,
  }) {
    final bool isActive = _activeDirection == direction;
    final Color activeColor = color ?? AppColors.orange;

    return GestureDetector(
      onTapDown: (_) => _onPress(direction),
      onTapUp: (_) => _onRelease(),
      onTapCancel: _onRelease,
      child: Container(
        width: size,
        height: size,
        decoration: BoxDecoration(
          color: isActive
              ? activeColor.withValues(alpha: 0.15)
              : AppColors.surfaceAlt,
          borderRadius: BorderRadius.circular(14),
          border: Border.all(
            color: isActive
                ? activeColor
                : AppColors.blueGray.withValues(alpha: 0.3),
            width: isActive ? 2 : 1,
          ),
          boxShadow: isActive
              ? [
                  BoxShadow(
                    color: activeColor.withValues(alpha: 0.2),
                    blurRadius: 10,
                    spreadRadius: 1,
                  ),
                ]
              : null,
        ),
        child: Column(
          mainAxisAlignment: MainAxisAlignment.center,
          children: [
            Icon(
              icon,
              color: isActive ? activeColor : AppColors.darkNavy,
              size: size > 70 ? 26 : 22,
            ),
            const SizedBox(height: 3),
            Text(
              label,
              style: TextStyle(
                color: isActive ? activeColor : AppColors.blueGray,
                fontSize: 11,
                fontWeight: FontWeight.w500,
              ),
            ),
          ],
        ),
      ),
    );
  }

  Widget _buildStopButton() {
    return GestureDetector(
      onTap: _onStop,
      child: Container(
        width: 56,
        height: 56,
        decoration: BoxDecoration(
          color: AppColors.orange,
          borderRadius: BorderRadius.circular(28),
          boxShadow: [
            BoxShadow(
              color: AppColors.orange.withValues(alpha: 0.3),
              blurRadius: 10,
              spreadRadius: 1,
            ),
          ],
        ),
        child: const Icon(Icons.stop, color: Colors.white, size: 28),
      ),
    );
  }

  Widget _buildActionStatus() {
    return AppCard(
      title: '当前动作',
      icon: Icons.info_outline,
      child: Row(
        mainAxisAlignment: MainAxisAlignment.spaceBetween,
        children: [
          Text(
            _ctrl.currentAction,
            style: const TextStyle(
              color: AppColors.darkNavy,
              fontSize: 18,
              fontWeight: FontWeight.w600,
            ),
          ),
          if (_ctrl.currentDirection.isNotEmpty && _ctrl.canManualControl)
            Container(
              padding: const EdgeInsets.all(8),
              decoration: BoxDecoration(
                color: AppColors.orange.withValues(alpha: 0.12),
                borderRadius: BorderRadius.circular(8),
              ),
              child: Icon(
                _getDirectionIcon(_ctrl.currentDirection),
                color: AppColors.orange,
                size: 24,
              ),
            ),
        ],
      ),
    );
  }

  IconData _getDirectionIcon(String direction) {
    switch (direction) {
      case 'forward':
        return Icons.north;
      case 'backward':
        return Icons.south;
      case 'left':
        return Icons.west;
      case 'right':
        return Icons.east;
      case 'turn_left':
        return Icons.rotate_left;
      case 'turn_right':
        return Icons.rotate_right;
      default:
        return Icons.stop;
    }
  }

  Widget _buildQuickActions() {
    return AppCard(
      title: '快捷操作',
      icon: Icons.bolt,
      child: Row(
        children: [
          Expanded(
            child: _buildQuickButton(
              icon: Icons.center_focus_strong,
              label: '自动归位',
              onTap: _ctrl.hasLocalMedia ? _ctrl.sendAutoReturn : null,
            ),
          ),
          const SizedBox(width: 12),
          Expanded(
            child: _buildQuickButton(
              icon: Icons.screenshot_monitor,
              label: '截图',
              onTap: _ctrl.hasLocalMedia ? _ctrl.sendScreenshot : null,
            ),
          ),
          const SizedBox(width: 12),
          Expanded(
            child: _buildQuickButton(
              icon: Icons.videocam,
              label: '录制',
              onTap: _ctrl.hasLocalMedia ? _ctrl.sendRecord : null,
            ),
          ),
        ],
      ),
    );
  }

  Widget _buildQuickButton({
    required IconData icon,
    required String label,
    VoidCallback? onTap,
  }) {
    bool enabled = onTap != null;
    return GestureDetector(
      onTap: onTap,
      child: Container(
        padding: const EdgeInsets.symmetric(vertical: 16),
        decoration: BoxDecoration(
          color: enabled ? AppColors.surfaceAlt : AppColors.background,
          borderRadius: BorderRadius.circular(12),
          border: Border.all(
            color: enabled
                ? AppColors.blueGray.withValues(alpha: 0.3)
                : AppColors.blueGray.withValues(alpha: 0.15),
          ),
        ),
        child: Column(
          children: [
            Icon(
              icon,
              color: enabled
                  ? AppColors.bluePurple
                  : AppColors.blueGray.withValues(alpha: 0.4),
              size: 24,
            ),
            const SizedBox(height: 6),
            Text(
              label,
              style: TextStyle(
                color: enabled
                    ? AppColors.darkNavy
                    : AppColors.blueGray.withValues(alpha: 0.4),
                fontSize: 12,
              ),
            ),
          ],
        ),
      ),
    );
  }

  Widget _buildLogPanel() {
    final logs = _ctrl.messages.reversed.take(50).toList();
    return Container(
      margin: const EdgeInsets.symmetric(horizontal: 16, vertical: 8),
      padding: const EdgeInsets.all(16),
      decoration: BoxDecoration(
        color: AppColors.surface,
        borderRadius: BorderRadius.circular(16),
        border: Border.all(
          color: AppColors.blueGray.withValues(alpha: 0.2),
          width: 1,
        ),
        boxShadow: [
          BoxShadow(
            color: Colors.black.withValues(alpha: 0.04),
            blurRadius: 8,
            offset: const Offset(0, 2),
          ),
        ],
      ),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          // 标题行：图标 + 标题 + 复制按钮 + 清空按钮
          Row(
            children: [
              const Icon(Icons.terminal, color: AppColors.bluePurple, size: 20),
              const SizedBox(width: 8),
              const Text(
                '通信日志',
                style: TextStyle(
                  color: AppColors.bluePurple,
                  fontSize: 14,
                  fontWeight: FontWeight.w600,
                ),
              ),
              const Spacer(),
              // 复制全部日志
              IconButton(
                onPressed: logs.isEmpty
                    ? null
                    : () {
                        final allLogs = _ctrl.messages.join('\n');
                        Clipboard.setData(ClipboardData(text: allLogs));
                        ScaffoldMessenger.of(context).showSnackBar(
                          const SnackBar(
                            content: Text('日志已复制到剪贴板'),
                            duration: Duration(seconds: 2),
                          ),
                        );
                      },
                icon: const Icon(Icons.copy, size: 18),
                color: AppColors.bluePurple,
                tooltip: '复制全部日志',
                constraints: const BoxConstraints(minWidth: 36, minHeight: 36),
                padding: EdgeInsets.zero,
              ),
              const SizedBox(width: 4),
              // 清空日志
              IconButton(
                onPressed: logs.isEmpty ? null : _ctrl.clearMessages,
                icon: const Icon(Icons.delete_outline, size: 18),
                color: AppColors.blueGray,
                tooltip: '清空日志',
                constraints: const BoxConstraints(minWidth: 36, minHeight: 36),
                padding: EdgeInsets.zero,
              ),
            ],
          ),
          const SizedBox(height: 12),
          // 日志内容
          Container(
            height: 180,
            decoration: BoxDecoration(
              color: AppColors.surfaceAlt,
              borderRadius: BorderRadius.circular(8),
            ),
            child: logs.isEmpty
                ? const Center(
                    child: Text(
                      '暂无日志',
                      style: TextStyle(color: AppColors.blueGray, fontSize: 12),
                    ),
                  )
                : ListView.builder(
                    reverse: true,
                    padding: const EdgeInsets.all(8),
                    itemCount: logs.length,
                    itemBuilder: (context, index) {
                      return Padding(
                        padding: const EdgeInsets.symmetric(vertical: 1),
                        child: Text(
                          logs[index],
                          style: TextStyle(
                            color: logs[index].contains('[错误]')
                                ? AppColors.errorRed
                                : logs[index].contains('[收到]')
                                ? AppColors.successGreen
                                : logs[index].contains('[调试]')
                                ? AppColors.blueGray
                                : AppColors.darkNavyLight,
                            fontSize: 11,
                            fontFamily: 'monospace',
                          ),
                        ),
                      );
                    },
                  ),
          ),
        ],
      ),
    );
  }
}
