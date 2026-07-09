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

class _ControlPageState extends State<ControlPage> {
  final CarController _ctrl = CarController.instance;
  late TextEditingController _ipController;

  @override
  void initState() {
    super.initState();
    _ipController = TextEditingController(text: _ctrl.host);
    _ctrl.addListener(_onControllerChanged);
  }

  @override
  void dispose() {
    _ctrl.removeListener(_onControllerChanged);
    _ipController.dispose();
    super.dispose();
  }

  void _onControllerChanged() {
    if (mounted) setState(() {});
  }

  void _toggleConnection() {
    if (_ctrl.isConnected) {
      _ctrl.disconnect();
    } else {
      _ctrl.connect(_ipController.text.trim());
    }
    HapticFeedback.mediumImpact();
  }

  void _sendCommand(String direction) {
    if (!_ctrl.isConnected) {
      ScaffoldMessenger.of(context).showSnackBar(
        const SnackBar(
          content: Text('请先连接小车'),
          backgroundColor: AppColors.orange,
          duration: Duration(seconds: 1),
        ),
      );
      return;
    }
    _ctrl.sendCommand(direction);
    HapticFeedback.heavyImpact();
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
    } else if (isConnected) {
      badgeText = '已连接';
      badgeColor = AppColors.successGreen;
    } else if (isError) {
      badgeText = '连接错误';
      badgeColor = AppColors.errorRed;
    } else {
      badgeText = '未连接';
      badgeColor = AppColors.blueGray;
    }

    return AppCard(
      title: '连接状态',
      icon: Icons.wifi,
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
                hintText: '小车 IP 地址',
                prefixIcon: const Icon(
                  Icons.dns,
                  size: 18,
                  color: AppColors.blueGray,
                ),
              ),
              enabled: !isConnected && !isConnecting,
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
                  : Text(isConnected ? '断开' : '连接'),
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
              const Icon(Icons.slow_motion_video,
                  color: AppColors.blueGray, size: 20),
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
                style: const TextStyle(
                  color: AppColors.darkNavy,
                  fontSize: 14,
                ),
              ),
              Text(
                '${(_ctrl.speed * 1.5).toStringAsFixed(1)} m/s',
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
      padding: const EdgeInsets.all(24),
      decoration: BoxDecoration(
        color: AppColors.surface,
        borderRadius: BorderRadius.circular(20),
        border: Border.all(
          color: AppColors.blueGray.withValues(alpha: 0.2),
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
        children: [
          Row(
            mainAxisAlignment: MainAxisAlignment.center,
            children: [
              Icon(Icons.gamepad, color: AppColors.bluePurple, size: 20),
              const SizedBox(width: 8),
              const Text(
                '方向控制',
                style: TextStyle(
                  color: AppColors.bluePurple,
                  fontSize: 14,
                  fontWeight: FontWeight.w600,
                ),
              ),
            ],
          ),
          const SizedBox(height: 20),
          Row(
            mainAxisAlignment: MainAxisAlignment.center,
            children: [
              _buildDirectionButton(
                icon: Icons.arrow_upward,
                label: '前进',
                direction: 'forward',
                isActive: _ctrl.currentDirection == 'forward',
              ),
            ],
          ),
          const SizedBox(height: 12),
          Row(
            mainAxisAlignment: MainAxisAlignment.center,
            children: [
              _buildDirectionButton(
                icon: Icons.arrow_back,
                label: '左转',
                direction: 'left',
                isActive: _ctrl.currentDirection == 'left',
              ),
              const SizedBox(width: 12),
              _buildStopButton(),
              const SizedBox(width: 12),
              _buildDirectionButton(
                icon: Icons.arrow_forward,
                label: '右转',
                direction: 'right',
                isActive: _ctrl.currentDirection == 'right',
              ),
            ],
          ),
          const SizedBox(height: 12),
          Row(
            mainAxisAlignment: MainAxisAlignment.center,
            children: [
              _buildDirectionButton(
                icon: Icons.arrow_downward,
                label: '后退',
                direction: 'backward',
                isActive: _ctrl.currentDirection == 'backward',
              ),
            ],
          ),
        ],
      ),
    );
  }

  Widget _buildDirectionButton({
    required IconData icon,
    required String label,
    required String direction,
    bool isActive = false,
  }) {
    return GestureDetector(
      onTap: () => _sendCommand(direction),
      onLongPress: () => _sendCommand(direction),
      child: Container(
        width: 80,
        height: 80,
        decoration: BoxDecoration(
          color: isActive
              ? AppColors.orange.withValues(alpha: 0.15)
              : AppColors.surfaceAlt,
          borderRadius: BorderRadius.circular(16),
          border: Border.all(
            color: isActive
                ? AppColors.orange
                : AppColors.blueGray.withValues(alpha: 0.3),
            width: isActive ? 2 : 1,
          ),
          boxShadow: isActive
              ? [
                  BoxShadow(
                    color: AppColors.orange.withValues(alpha: 0.2),
                    blurRadius: 12,
                    spreadRadius: 2,
                  ),
                ]
              : null,
        ),
        child: Column(
          mainAxisAlignment: MainAxisAlignment.center,
          children: [
            Icon(
              icon,
              color: isActive ? AppColors.orange : AppColors.darkNavy,
              size: 28,
            ),
            const SizedBox(height: 4),
            Text(
              label,
              style: TextStyle(
                color: isActive ? AppColors.orange : AppColors.blueGray,
                fontSize: 12,
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
      onTap: () => _sendCommand('stop'),
      child: Container(
        width: 80,
        height: 80,
        decoration: BoxDecoration(
          color: AppColors.orange,
          borderRadius: BorderRadius.circular(16),
          boxShadow: [
            BoxShadow(
              color: AppColors.orange.withValues(alpha: 0.3),
              blurRadius: 12,
              spreadRadius: 2,
            ),
          ],
        ),
        child: const Column(
          mainAxisAlignment: MainAxisAlignment.center,
          children: [
            Icon(Icons.stop_circle, color: Colors.white, size: 32),
            SizedBox(height: 2),
            Text(
              '停止',
              style: TextStyle(
                color: Colors.white,
                fontSize: 12,
                fontWeight: FontWeight.w700,
              ),
            ),
          ],
        ),
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
          if (_ctrl.currentDirection.isNotEmpty && _ctrl.isConnected)
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
              onTap: _ctrl.isConnected ? _ctrl.sendAutoReturn : null,
            ),
          ),
          const SizedBox(width: 12),
          Expanded(
            child: _buildQuickButton(
              icon: Icons.screenshot_monitor,
              label: '截图',
              onTap: _ctrl.isConnected ? _ctrl.sendScreenshot : null,
            ),
          ),
          const SizedBox(width: 12),
          Expanded(
            child: _buildQuickButton(
              icon: Icons.videocam,
              label: '录制',
              onTap: _ctrl.isConnected ? _ctrl.sendRecord : null,
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
                constraints: const BoxConstraints(
                  minWidth: 36,
                  minHeight: 36,
                ),
                padding: EdgeInsets.zero,
              ),
              const SizedBox(width: 4),
              // 清空日志
              IconButton(
                onPressed: logs.isEmpty ? null : _ctrl.clearMessages,
                icon: const Icon(Icons.delete_outline, size: 18),
                color: AppColors.blueGray,
                tooltip: '清空日志',
                constraints: const BoxConstraints(
                  minWidth: 36,
                  minHeight: 36,
                ),
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
                      style: TextStyle(
                        color: AppColors.blueGray,
                        fontSize: 12,
                      ),
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
