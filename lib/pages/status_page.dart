import 'dart:async';
import 'package:flutter/material.dart';
import '../theme/app_theme.dart';
import '../services/car_controller.dart';

class StatusPage extends StatefulWidget {
  const StatusPage({super.key});

  @override
  State<StatusPage> createState() => _StatusPageState();
}

class _StatusPageState extends State<StatusPage> {
  final CarController _ctrl = CarController.instance;
  // 模拟数据
  final double _batteryLevel = 78.0;
  double _currentSpeed = 0.0;
  String _navigationMode = '手动控制';
  final String _signalStrength = '强';
  int _runningTime = 1245; // 秒
  Timer? _timer;

  @override
  void initState() {
    super.initState();
    _ctrl.addListener(_onControllerChanged);
    _timer = Timer.periodic(const Duration(seconds: 1), (timer) {
      setState(() {
        _runningTime++;
      });
    });
  }

  void _onControllerChanged() {
    if (!mounted) return;
    final nav = _ctrl.latestNavStatus;
    setState(() {
      final status = nav?['status']?.toString() ?? '';
      _navigationMode = status == 'NAVIGATING' ? '自主导航' : '手动控制';
      _currentSpeed = _ctrl.currentDirection.isEmpty ? 0.0 : _ctrl.speed * 0.35;
    });
  }

  @override
  void dispose() {
    _ctrl.removeListener(_onControllerChanged);
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
    final nav = _ctrl.latestNavStatus;
    final obstacle = _ctrl.latestObstacleStatus;
    final progress = ((nav?['progress'] as num?)?.toDouble() ?? 0.0)
        .clamp(0.0, 1.0)
        .toDouble();
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
              Text(
                nav?['status']?.toString() ?? 'IDLE',
                style: const TextStyle(color: AppColors.blueGrayDark),
              ),
            ],
          ),
          const SizedBox(height: 12),
          LinearProgressIndicator(value: progress),
          const SizedBox(height: 12),
          _buildDetailRow(
            '剩余距离',
            '${((nav?['distance_remain'] as num?)?.toDouble() ?? 0.0).toStringAsFixed(2)} m',
            Icons.route,
          ),
          const SizedBox(height: 8),
          _buildDetailRow(
            '障碍状态',
            obstacle?['is_obstacle'] == true
                ? '${obstacle?['risk_level'] ?? 'warning'} / ${obstacle?['min_distance'] ?? '-'} m'
                : '安全',
            Icons.shield_outlined,
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
