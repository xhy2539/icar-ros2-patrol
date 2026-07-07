import 'package:flutter/material.dart';
import 'package:flutter/services.dart';
import '../theme/app_theme.dart';

class ControlPage extends StatefulWidget {
  const ControlPage({super.key});

  @override
  State<ControlPage> createState() => _ControlPageState();
}

class _ControlPageState extends State<ControlPage> {
  bool _isConnected = false;
  String _carIp = '192.168.43.1';
  double _speed = 0.5;
  String _currentAction = '待机';
  String _currentDirection = '';

  // 模拟连接
  void _toggleConnection() {
    setState(() {
      _isConnected = !_isConnected;
      if (!_isConnected) {
        _currentAction = '待机';
        _currentDirection = '';
      } else {
        _currentAction = '已连接';
      }
    });
    HapticFeedback.mediumImpact();
  }

  // 发送控制指令
  void _sendCommand(String direction) {
    if (!_isConnected) {
      ScaffoldMessenger.of(context).showSnackBar(
        const SnackBar(
          content: Text('请先连接小车'),
          backgroundColor: AppColors.orange,
          duration: Duration(seconds: 1),
        ),
      );
      return;
    }

    setState(() {
      _currentDirection = direction;
      switch (direction) {
        case 'forward':
          _currentAction = '前进中';
          break;
        case 'backward':
          _currentAction = '后退中';
          break;
        case 'left':
          _currentAction = '左转中';
          break;
        case 'right':
          _currentAction = '右转中';
          break;
        case 'stop':
          _currentAction = '已停止';
          _currentDirection = '';
          break;
      }
    });
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
              // 连接状态栏
              _buildConnectionBar(),
              const SizedBox(height: 16),
              // 速度控制
              _buildSpeedControl(),
              const SizedBox(height: 24),
              // 方向控制
              _buildDirectionPad(),
              const SizedBox(height: 24),
              // 当前状态
              _buildActionStatus(),
              const SizedBox(height: 24),
              // 快捷操作
              _buildQuickActions(),
            ],
          ),
        ),
      ),
    );
  }

  Widget _buildConnectionBar() {
    return AppCard(
      title: '连接状态',
      icon: Icons.wifi,
      child: Row(
        children: [
          StatusBadge(
            text: _isConnected ? '已连接' : '未连接',
            color: _isConnected ? AppColors.successGreen : AppColors.blueGray,
          ),
          const Spacer(),
          // IP 地址输入
          Expanded(
            flex: 2,
            child: TextField(
              controller: TextEditingController(text: _carIp),
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
              onChanged: (value) => _carIp = value,
              enabled: !_isConnected,
            ),
          ),
          const SizedBox(width: 12),
          // 连接按钮
          SizedBox(
            height: 42,
            child: ElevatedButton(
              onPressed: _toggleConnection,
              style: ElevatedButton.styleFrom(
                backgroundColor:
                    _isConnected ? AppColors.blueGray : AppColors.orange,
                padding: const EdgeInsets.symmetric(horizontal: 20),
              ),
              child: Text(_isConnected ? '断开' : '连接'),
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
              const Icon(Icons.slow_motion_video, color: AppColors.blueGray, size: 20),
              Expanded(
                child: Slider(
                  value: _speed,
                  min: 0.1,
                  max: 1.0,
                  divisions: 9,
                  label: '${(_speed * 100).round()}%',
                  onChanged: (value) => setState(() => _speed = value),
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
                '当前速度: ${(_speed * 100).round()}%',
                style: const TextStyle(
                  color: AppColors.darkNavy,
                  fontSize: 14,
                ),
              ),
              Text(
                '${(_speed * 1.5).toStringAsFixed(1)} m/s',
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
          // 方向控制标题
          Row(
            mainAxisAlignment: MainAxisAlignment.center,
            children: [
              Icon(
                Icons.gamepad,
                color: AppColors.bluePurple,
                size: 20,
              ),
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
          // 前进按钮
          Row(
            mainAxisAlignment: MainAxisAlignment.center,
            children: [
              _buildDirectionButton(
                icon: Icons.arrow_upward,
                label: '前进',
                direction: 'forward',
                isActive: _currentDirection == 'forward',
              ),
            ],
          ),
          const SizedBox(height: 12),
          // 左转、停止、右转
          Row(
            mainAxisAlignment: MainAxisAlignment.center,
            children: [
              _buildDirectionButton(
                icon: Icons.arrow_back,
                label: '左转',
                direction: 'left',
                isActive: _currentDirection == 'left',
              ),
              const SizedBox(width: 12),
              _buildStopButton(),
              const SizedBox(width: 12),
              _buildDirectionButton(
                icon: Icons.arrow_forward,
                label: '右转',
                direction: 'right',
                isActive: _currentDirection == 'right',
              ),
            ],
          ),
          const SizedBox(height: 12),
          // 后退按钮
          Row(
            mainAxisAlignment: MainAxisAlignment.center,
            children: [
              _buildDirectionButton(
                icon: Icons.arrow_downward,
                label: '后退',
                direction: 'backward',
                isActive: _currentDirection == 'backward',
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
            color: isActive ? AppColors.orange : AppColors.blueGray.withValues(alpha: 0.3),
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
            Icon(
              Icons.stop_circle,
              color: Colors.white,
              size: 32,
            ),
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
            _currentAction,
            style: const TextStyle(
              color: AppColors.darkNavy,
              fontSize: 18,
              fontWeight: FontWeight.w600,
            ),
          ),
          if (_currentDirection.isNotEmpty && _isConnected)
            Container(
              padding: const EdgeInsets.all(8),
              decoration: BoxDecoration(
                color: AppColors.orange.withValues(alpha: 0.12),
                borderRadius: BorderRadius.circular(8),
              ),
              child: Icon(
                _getDirectionIcon(_currentDirection),
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
              onTap: _isConnected
                  ? () {
                      ScaffoldMessenger.of(context).showSnackBar(
                        const SnackBar(
                          content: Text('自动归位指令已发送'),
                          backgroundColor: AppColors.successGreen,
                        ),
                      );
                    }
                  : null,
            ),
          ),
          const SizedBox(width: 12),
          Expanded(
            child: _buildQuickButton(
              icon: Icons.screenshot_monitor,
              label: '截图',
              onTap: _isConnected
                  ? () {
                      ScaffoldMessenger.of(context).showSnackBar(
                        const SnackBar(
                          content: Text('截图已保存'),
                          backgroundColor: AppColors.successGreen,
                        ),
                      );
                    }
                  : null,
            ),
          ),
          const SizedBox(width: 12),
          Expanded(
            child: _buildQuickButton(
              icon: Icons.videocam,
              label: '录制',
              onTap: _isConnected
                  ? () {
                      ScaffoldMessenger.of(context).showSnackBar(
                        const SnackBar(
                          content: Text('录制已开始'),
                          backgroundColor: AppColors.successGreen,
                        ),
                      );
                    }
                  : null,
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
          color: enabled
              ? AppColors.surfaceAlt
              : AppColors.background,
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
              color: enabled ? AppColors.bluePurple : AppColors.blueGray.withValues(alpha: 0.4),
              size: 24,
            ),
            const SizedBox(height: 6),
            Text(
              label,
              style: TextStyle(
                color: enabled ? AppColors.darkNavy : AppColors.blueGray.withValues(alpha: 0.4),
                fontSize: 12,
              ),
            ),
          ],
        ),
      ),
    );
  }
}
