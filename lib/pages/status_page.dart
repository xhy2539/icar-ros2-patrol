import 'dart:async';
import 'package:flutter/material.dart';
import '../theme/app_theme.dart';

class StatusPage extends StatefulWidget {
  const StatusPage({super.key});

  @override
  State<StatusPage> createState() => _StatusPageState();
}

class _StatusPageState extends State<StatusPage> {
  // 模拟数据
  double _batteryLevel = 78.0;
  double _currentSpeed = 0.0;
  String _navigationMode = '手动控制';
  String _signalStrength = '强';
  int _runningTime = 1245; // 秒
  Timer? _timer;

  @override
  void initState() {
    super.initState();
    _timer = Timer.periodic(const Duration(seconds: 1), (timer) {
      setState(() {
        _runningTime++;
        // 模拟速度波动
        _currentSpeed = (_currentSpeed + (DateTime.now().second % 3 - 1) * 0.1)
            .clamp(0.0, 1.5);
      });
    });
  }

  @override
  void dispose() {
    _timer?.cancel();
    super.dispose();
  }

  String _formatTime(int seconds) {
    int h = seconds ~/ 3600;
    int m = (seconds % 3600) ~/ 60;
    int s = seconds % 60;
    return '${h.toString().padLeft(2, '0')}:${m.toString().padLeft(2, '0')}:${s.toString().padLeft(2, '0')}';
  }

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      body: SafeArea(
        child: SingleChildScrollView(
          padding: const EdgeInsets.symmetric(vertical: 16),
          child: Column(
            children: [
              // 摄像头画面
              _buildCameraFeed(),
              const SizedBox(height: 16),
              // 状态概览
              _buildStatusOverview(),
              const SizedBox(height: 16),
              // 详细信息
              _buildDetailCards(),
              const SizedBox(height: 16),
              // 导航信息
              _buildNavigationInfo(),
            ],
          ),
        ),
      ),
    );
  }

  Widget _buildCameraFeed() {
    return Container(
      margin: const EdgeInsets.symmetric(horizontal: 16),
      height: 220,
      decoration: BoxDecoration(
        color: AppColors.surfaceAlt,
        borderRadius: BorderRadius.circular(16),
        border: Border.all(
          color: AppColors.blueGray.withValues(alpha: 0.3),
        ),
        boxShadow: [
          BoxShadow(
            color: Colors.black.withValues(alpha: 0.04),
            blurRadius: 8,
            offset: const Offset(0, 2),
          ),
        ],
      ),
      child: Stack(
        children: [
          // 模拟摄像头画面
          Center(
            child: Column(
              mainAxisAlignment: MainAxisAlignment.center,
              children: [
                Icon(
                  Icons.videocam,
                  color: AppColors.blueGray.withValues(alpha: 0.5),
                  size: 48,
                ),
                const SizedBox(height: 8),
                Text(
                  '摄像头画面',
                  style: TextStyle(
                    color: AppColors.blueGrayDark,
                    fontSize: 14,
                  ),
                ),
                const SizedBox(height: 4),
                Text(
                  '连接小车后显示实时画面',
                  style: TextStyle(
                    color: AppColors.blueGray.withValues(alpha: 0.6),
                    fontSize: 12,
                  ),
                ),
              ],
            ),
          ),
          // 左上角 LIVE 标识
          Positioned(
            top: 12,
            left: 12,
            child: Container(
              padding: const EdgeInsets.symmetric(horizontal: 10, vertical: 4),
              decoration: BoxDecoration(
                color: AppColors.orange,
                borderRadius: BorderRadius.circular(4),
              ),
              child: const Row(
                mainAxisSize: MainAxisSize.min,
                children: [
                  Icon(Icons.circle, color: Colors.white, size: 8),
                  SizedBox(width: 4),
                  Text(
                    'LIVE',
                    style: TextStyle(
                      color: Colors.white,
                      fontSize: 11,
                      fontWeight: FontWeight.bold,
                    ),
                  ),
                ],
              ),
            ),
          ),
          // 右上角 分辨率
          Positioned(
            top: 12,
            right: 12,
            child: Container(
              padding: const EdgeInsets.symmetric(horizontal: 8, vertical: 4),
              decoration: BoxDecoration(
                color: AppColors.darkNavy.withValues(alpha: 0.6),
                borderRadius: BorderRadius.circular(4),
              ),
              child: const Text(
                '640×480',
                style: TextStyle(
                  color: Colors.white,
                  fontSize: 11,
                ),
              ),
            ),
          ),
          // 底部工具栏
          Positioned(
            bottom: 0,
            left: 0,
            right: 0,
            child: Container(
              padding: const EdgeInsets.symmetric(horizontal: 16, vertical: 10),
              decoration: BoxDecoration(
                gradient: LinearGradient(
                  begin: Alignment.topCenter,
                  end: Alignment.bottomCenter,
                  colors: [
                    Colors.transparent,
                    AppColors.darkNavy.withValues(alpha: 0.7),
                  ],
                ),
                borderRadius: const BorderRadius.only(
                  bottomLeft: Radius.circular(16),
                  bottomRight: Radius.circular(16),
                ),
              ),
              child: Row(
                mainAxisAlignment: MainAxisAlignment.spaceAround,
                children: [
                  _buildCameraAction(Icons.camera_alt, '拍照'),
                  _buildCameraAction(Icons.videocam, '录制'),
                  _buildCameraAction(Icons.fullscreen, '全屏'),
                  _buildCameraAction(Icons.switch_camera, '切换'),
                ],
              ),
            ),
          ),
        ],
      ),
    );
  }

  Widget _buildCameraAction(IconData icon, String label) {
    return Column(
      mainAxisSize: MainAxisSize.min,
      children: [
        Icon(icon, color: Colors.white, size: 20),
        const SizedBox(height: 2),
        Text(
          label,
          style: const TextStyle(color: Colors.white70, fontSize: 10),
        ),
      ],
    );
  }

  Widget _buildStatusOverview() {
    return Padding(
      padding: const EdgeInsets.symmetric(horizontal: 16),
      child: Row(
        children: [
          Expanded(
            child: _buildStatusItem(
              icon: Icons.battery_charging_full,
              label: '电量',
              value: '${_batteryLevel.round()}%',
              color: _batteryLevel > 30
                  ? AppColors.successGreen
                  : AppColors.errorRed,
            ),
          ),
          const SizedBox(width: 8),
          Expanded(
            child: _buildStatusItem(
              icon: Icons.speed,
              label: '速度',
              value: '${_currentSpeed.toStringAsFixed(1)} m/s',
              color: AppColors.bluePurple,
            ),
          ),
          const SizedBox(width: 8),
          Expanded(
            child: _buildStatusItem(
              icon: Icons.timer,
              label: '运行时间',
              value: _formatTime(_runningTime),
              color: AppColors.darkNavy,
            ),
          ),
          const SizedBox(width: 8),
          Expanded(
            child: _buildStatusItem(
              icon: Icons.wifi,
              label: '信号',
              value: _signalStrength,
              color: AppColors.successGreen,
            ),
          ),
        ],
      ),
    );
  }

  Widget _buildStatusItem({
    required IconData icon,
    required String label,
    required String value,
    required Color color,
  }) {
    return Container(
      padding: const EdgeInsets.symmetric(vertical: 16, horizontal: 12),
      decoration: BoxDecoration(
        color: AppColors.surface,
        borderRadius: BorderRadius.circular(12),
        border: Border.all(
          color: AppColors.blueGray.withValues(alpha: 0.2),
        ),
        boxShadow: [
          BoxShadow(
            color: Colors.black.withValues(alpha: 0.03),
            blurRadius: 4,
            offset: const Offset(0, 1),
          ),
        ],
      ),
      child: Column(
        children: [
          Icon(icon, color: color, size: 22),
          const SizedBox(height: 6),
          Text(
            value,
            style: TextStyle(
              color: color,
              fontSize: 14,
              fontWeight: FontWeight.w700,
            ),
          ),
          const SizedBox(height: 2),
          Text(
            label,
            style: const TextStyle(
              color: AppColors.blueGrayDark,
              fontSize: 11,
            ),
          ),
        ],
      ),
    );
  }

  Widget _buildDetailCards() {
    return Column(
      children: [
        // 底盘状态
        AppCard(
          title: '底盘状态',
          icon: Icons.settings_input_component,
          child: Column(
            children: [
              _buildDetailRow('驱动模式', '麦轮全向', Icons.all_inclusive),
              const Divider(height: 20),
              _buildDetailRow('左前轮', '0 rpm', Icons.rotate_right),
              const SizedBox(height: 8),
              _buildDetailRow('右前轮', '0 rpm', Icons.rotate_left),
              const SizedBox(height: 8),
              _buildDetailRow('左后轮', '0 rpm', Icons.rotate_right),
              const SizedBox(height: 8),
              _buildDetailRow('右后轮', '0 rpm', Icons.rotate_left),
            ],
          ),
        ),
        // 系统信息
        AppCard(
          title: '系统信息',
          icon: Icons.memory,
          child: Column(
            children: [
              _buildDetailRow('主控', 'Jetson Orin Nano', Icons.developer_board),
              const Divider(height: 20),
              _buildDetailRow('系统', 'Ubuntu 20.04', Icons.laptop),
              const SizedBox(height: 8),
              _buildDetailRow('ROS2', 'Foxy', Icons.hub),
              const SizedBox(height: 8),
              _buildDetailRow('Docker', '运行中', Icons.inventory_2),
            ],
          ),
        ),
      ],
    );
  }

  Widget _buildDetailRow(String label, String value, IconData icon) {
    return Row(
      children: [
        Icon(icon, color: AppColors.blueGray, size: 16),
        const SizedBox(width: 10),
        Text(
          label,
          style: const TextStyle(color: AppColors.blueGrayDark, fontSize: 14),
        ),
        const Spacer(),
        Text(
          value,
          style: const TextStyle(
            color: AppColors.darkNavy,
            fontSize: 14,
            fontWeight: FontWeight.w500,
          ),
        ),
      ],
    );
  }

  Widget _buildNavigationInfo() {
    return AppCard(
      title: '导航信息',
      icon: Icons.navigation,
      child: Column(
        children: [
          Row(
            children: [
              StatusBadge(
                text: _navigationMode,
                color: AppColors.bluePurple,
              ),
              const Spacer(),
              TextButton.icon(
                onPressed: () {
                  setState(() {
                    _navigationMode = _navigationMode == '手动控制'
                        ? '自主导航'
                        : '手动控制';
                  });
                },
                icon: const Icon(Icons.swap_horiz, size: 16),
                label: const Text('切换模式'),
                style: TextButton.styleFrom(
                  foregroundColor: AppColors.bluePurple,
                ),
              ),
            ],
          ),
          const SizedBox(height: 12),
          Container(
            height: 160,
            decoration: BoxDecoration(
              color: AppColors.surfaceAlt,
              borderRadius: BorderRadius.circular(12),
              border: Border.all(
                color: AppColors.blueGray.withValues(alpha: 0.2),
              ),
            ),
            child: Center(
              child: Column(
                mainAxisAlignment: MainAxisAlignment.center,
                children: [
                  Icon(
                    Icons.map,
                    color: AppColors.blueGray.withValues(alpha: 0.5),
                    size: 40,
                  ),
                  const SizedBox(height: 8),
                  Text(
                    'SLAM 地图',
                    style: TextStyle(
                      color: AppColors.blueGrayDark,
                      fontSize: 13,
                    ),
                  ),
                  const SizedBox(height: 2),
                  Text(
                    '建图后显示',
                    style: TextStyle(
                      color: AppColors.blueGray.withValues(alpha: 0.5),
                      fontSize: 11,
                    ),
                  ),
                ],
              ),
            ),
          ),
        ],
      ),
    );
  }
}
