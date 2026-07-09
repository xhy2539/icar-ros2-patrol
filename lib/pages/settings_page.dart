import 'package:flutter/material.dart';
import '../theme/app_theme.dart';

class SettingsPage extends StatefulWidget {
  const SettingsPage({super.key});

  @override
  State<SettingsPage> createState() => _SettingsPageState();
}

class _SettingsPageState extends State<SettingsPage> {
  String _carIp = '10.90.164.83';
  int _rosbridgePort = 9090;
  double _defaultSpeed = 0.5;
  bool _autoReconnect = true;
  bool _hapticFeedback = true;
  bool _vibrateOnAlert = true;

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      body: SafeArea(
        child: SingleChildScrollView(
          padding: const EdgeInsets.symmetric(vertical: 16),
          child: Column(
            children: [
              // 连接设置
              _buildConnectionSettings(),
              const SizedBox(height: 16),
              // 控制设置
              _buildControlSettings(),
              const SizedBox(height: 16),
              // 通知设置
              _buildNotificationSettings(),
              const SizedBox(height: 16),
              // 关于
              _buildAboutSection(),
            ],
          ),
        ),
      ),
    );
  }

  Widget _buildConnectionSettings() {
    return AppCard(
      title: '连接设置',
      icon: Icons.settings_ethernet,
      child: Column(
        children: [
          // IP 地址
          _buildTextField(
            label: '小车 IP 地址',
            value: _carIp,
            icon: Icons.dns,
            onChanged: (value) => _carIp = value,
          ),
          const SizedBox(height: 16),
          // WebSocket 端口
          _buildTextField(
            label: 'WebSocket 端口',
            value: _rosbridgePort.toString(),
            icon: Icons.lan,
            keyboardType: TextInputType.number,
            onChanged: (value) {
              int? port = int.tryParse(value);
              if (port != null) _rosbridgePort = port;
            },
          ),
          const SizedBox(height: 16),
          // WiFi 热点信息
          Container(
            padding: const EdgeInsets.all(12),
            decoration: BoxDecoration(
              color: AppColors.surfaceAlt,
              borderRadius: BorderRadius.circular(12),
            ),
            child: const Column(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                Row(
                  children: [
                    Icon(Icons.info_outline, color: AppColors.bluePurple, size: 16),
                    SizedBox(width: 8),
                    Text(
                      'WiFi 热点配置',
                      style: TextStyle(
                        color: AppColors.bluePurple,
                        fontSize: 13,
                        fontWeight: FontWeight.w600,
                      ),
                    ),
                  ],
                ),
                SizedBox(height: 8),
                Text(
                  '网络: 10.90.164.83\nVNC 密码: yahboom\n底盘串口: /dev/myserial (ttyUSB1)',
                  style: TextStyle(
                    color: AppColors.blueGrayDark,
                    fontSize: 12,
                    height: 1.6,
                  ),
                ),
              ],
            ),
          ),
        ],
      ),
    );
  }

  Widget _buildControlSettings() {
    return AppCard(
      title: '控制设置',
      icon: Icons.tune,
      child: Column(
        children: [
          // 默认速度
          Row(
            children: [
              const Icon(Icons.speed, color: AppColors.blueGray, size: 18),
              const SizedBox(width: 10),
              const Text(
                '默认速度',
                style: TextStyle(color: AppColors.darkNavy, fontSize: 14),
              ),
              const Spacer(),
              Text(
                '${(_defaultSpeed * 100).round()}%',
                style: const TextStyle(
                  color: AppColors.bluePurple,
                  fontSize: 14,
                  fontWeight: FontWeight.w600,
                ),
              ),
            ],
          ),
          Slider(
            value: _defaultSpeed,
            min: 0.1,
            max: 1.0,
            divisions: 9,
            onChanged: (value) => setState(() => _defaultSpeed = value),
          ),
          const Divider(height: 24),
          // 自动重连
          _buildSwitchRow(
            icon: Icons.sync,
            label: '自动重连',
            subtitle: '断线后自动尝试重新连接',
            value: _autoReconnect,
            onChanged: (value) => setState(() => _autoReconnect = value),
          ),
          const SizedBox(height: 16),
          // 触觉反馈
          _buildSwitchRow(
            icon: Icons.vibration,
            label: '触觉反馈',
            subtitle: '按下按钮时震动反馈',
            value: _hapticFeedback,
            onChanged: (value) => setState(() => _hapticFeedback = value),
          ),
        ],
      ),
    );
  }

  Widget _buildNotificationSettings() {
    return AppCard(
      title: '告警设置',
      icon: Icons.notifications,
      child: _buildSwitchRow(
        icon: Icons.warning_amber,
        label: '超标震动提醒',
        subtitle: '传感器数据超标时震动提醒',
        value: _vibrateOnAlert,
        onChanged: (value) => setState(() => _vibrateOnAlert = value),
      ),
    );
  }

  Widget _buildAboutSection() {
    return AppCard(
      title: '关于',
      icon: Icons.info,
      child: Column(
        children: [
          _buildInfoRow('应用名称', 'iCar 巡检控制端'),
          const Divider(height: 16),
          _buildInfoRow('版本', 'v2.0.0'),
          const Divider(height: 16),
          _buildInfoRow('项目', '2026 小学期实训'),
          const Divider(height: 16),
          _buildInfoRow('技术栈', 'Flutter + WebSocket'),
        ],
      ),
    );
  }

  Widget _buildTextField({
    required String label,
    required String value,
    required IconData icon,
    required ValueChanged<String> onChanged,
    TextInputType? keyboardType,
  }) {
    return Row(
      children: [
        Icon(icon, color: AppColors.blueGray, size: 18),
        const SizedBox(width: 10),
        Expanded(
          child: Text(
            label,
            style: const TextStyle(color: AppColors.darkNavy, fontSize: 14),
          ),
        ),
        SizedBox(
          width: 150,
          child: TextField(
            controller: TextEditingController(text: value),
            style: const TextStyle(color: AppColors.darkNavy, fontSize: 14),
            keyboardType: keyboardType,
            decoration: InputDecoration(
              isDense: true,
              contentPadding: const EdgeInsets.symmetric(
                horizontal: 12,
                vertical: 10,
              ),
            ),
            onChanged: onChanged,
          ),
        ),
      ],
    );
  }

  Widget _buildSwitchRow({
    required IconData icon,
    required String label,
    required String subtitle,
    required bool value,
    required ValueChanged<bool> onChanged,
  }) {
    return Row(
      children: [
        Icon(icon, color: AppColors.blueGray, size: 18),
        const SizedBox(width: 10),
        Expanded(
          child: Column(
            crossAxisAlignment: CrossAxisAlignment.start,
            children: [
              Text(
                label,
                style: const TextStyle(color: AppColors.darkNavy, fontSize: 14),
              ),
              Text(
                subtitle,
                style: const TextStyle(color: AppColors.blueGrayDark, fontSize: 11),
              ),
            ],
          ),
        ),
        Switch(
          value: value,
          onChanged: onChanged,
        ),
      ],
    );
  }

  Widget _buildInfoRow(String label, String value) {
    return Row(
      mainAxisAlignment: MainAxisAlignment.spaceBetween,
      children: [
        Text(
          label,
          style: const TextStyle(color: AppColors.blueGrayDark, fontSize: 14),
        ),
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
}
