import 'package:flutter/material.dart';
import 'package:shared_preferences/shared_preferences.dart';
import '../theme/app_theme.dart';
import '../services/car_controller.dart';

class SettingsPage extends StatefulWidget {
  const SettingsPage({super.key});

  @override
  State<SettingsPage> createState() => _SettingsPageState();
}

class _SettingsPageState extends State<SettingsPage> {
  final CarController _ctrl = CarController.instance;

  late String _carIp;
  late int _wsPort;
  late double _defaultSpeed;
  late bool _autoReconnect;
  late bool _hapticFeedback;
  bool _vibrateOnAlert = true;

  bool _dirty = false; // 是否有未保存的更改
  bool _saving = false;

  late final TextEditingController _ipCtrl;
  late final TextEditingController _portCtrl;

  @override
  void initState() {
    super.initState();
    _carIp = _ctrl.host;
    _wsPort = _ctrl.port;
    _defaultSpeed = _ctrl.speed;
    _autoReconnect = _ctrl.autoReconnect;
    _hapticFeedback = _ctrl.hapticEnabled;

    _ipCtrl = TextEditingController(text: _carIp);
    _portCtrl = TextEditingController(text: _wsPort.toString());

    _loadPersisted();
  }

  @override
  void dispose() {
    _ipCtrl.dispose();
    _portCtrl.dispose();
    super.dispose();
  }

  Future<void> _loadPersisted() async {
    final prefs = await SharedPreferences.getInstance();
    setState(() {
      _carIp = prefs.getString('car_ip') ?? _ctrl.host;
      _wsPort = prefs.getInt('ws_port') ?? _ctrl.port;
      _defaultSpeed = prefs.getDouble('default_speed') ?? _ctrl.speed;
      _autoReconnect = prefs.getBool('auto_reconnect') ?? _ctrl.autoReconnect;
      _hapticFeedback = prefs.getBool('haptic_feedback') ?? _ctrl.hapticEnabled;
      _vibrateOnAlert = prefs.getBool('vibrate_on_alert') ?? true;

      _ipCtrl.text = _carIp;
      _portCtrl.text = _wsPort.toString();
    });
  }

  void _markDirty() {
    if (!_dirty) setState(() => _dirty = true);
  }

  Future<void> _saveAndApply() async {
    setState(() => _saving = true);

    // 持久化
    final prefs = await SharedPreferences.getInstance();
    await prefs.setString('car_ip', _carIp);
    await prefs.setInt('ws_port', _wsPort);
    await prefs.setDouble('default_speed', _defaultSpeed);
    await prefs.setBool('auto_reconnect', _autoReconnect);
    await prefs.setBool('haptic_feedback', _hapticFeedback);
    await prefs.setBool('vibrate_on_alert', _vibrateOnAlert);

    // 应用到 CarController
    await _ctrl.updateSettings(
      host: _carIp,
      port: _wsPort,
      speed: _defaultSpeed,
      autoReconnect: _autoReconnect,
      hapticEnabled: _hapticFeedback,
    );

    setState(() {
      _dirty = false;
      _saving = false;
    });

    if (mounted) {
      ScaffoldMessenger.of(context).showSnackBar(
        const SnackBar(
          content: Text('设置已保存并应用'),
          duration: Duration(seconds: 2),
        ),
      );
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
              _buildConnectionSettings(),
              const SizedBox(height: 16),
              _buildControlSettings(),
              const SizedBox(height: 16),
              _buildNotificationSettings(),
              const SizedBox(height: 16),
              _buildAboutSection(),
              const SizedBox(height: 16),
              // 保存按钮
              Padding(
                padding: const EdgeInsets.symmetric(horizontal: 16),
                child: SizedBox(
                  width: double.infinity,
                  height: 44,
                  child: ElevatedButton.icon(
                    onPressed: _dirty && !_saving ? _saveAndApply : null,
                    icon: _saving
                        ? const SizedBox(
                            width: 18,
                            height: 18,
                            child: CircularProgressIndicator(
                                strokeWidth: 2, color: Colors.white),
                          )
                        : const Icon(Icons.save, size: 20),
                    label: Text(_dirty ? '保存并应用' : '已保存'),
                    style: ElevatedButton.styleFrom(
                      backgroundColor: AppColors.bluePurple,
                    ),
                  ),
                ),
              ),
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
          _buildTextField(
            label: '小车 IP 地址',
            controller: _ipCtrl,
            icon: Icons.dns,
            onChanged: (value) {
              _carIp = value;
              _markDirty();
            },
          ),
          const SizedBox(height: 16),
          _buildTextField(
            label: 'WebSocket 端口',
            controller: _portCtrl,
            icon: Icons.lan,
            keyboardType: TextInputType.number,
            onChanged: (value) {
              int? port = int.tryParse(value);
              if (port != null && port > 0 && port < 65536) {
                _wsPort = port;
                _markDirty();
              }
            },
          ),
          const SizedBox(height: 16),
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
                    Icon(Icons.info_outline,
                        color: AppColors.bluePurple, size: 16),
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
                  '热点: ohcar121 / 12345678\nVNC 密码: yahboom\n底盘串口: /dev/myserial (ttyUSB1)',
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
            onChanged: (value) {
              setState(() => _defaultSpeed = value);
              _markDirty();
            },
          ),
          const Divider(height: 24),
          _buildSwitchRow(
            icon: Icons.sync,
            label: '自动重连',
            subtitle: '断线后自动尝试重新连接',
            value: _autoReconnect,
            onChanged: (value) {
              setState(() => _autoReconnect = value);
              _markDirty();
            },
          ),
          const SizedBox(height: 16),
          _buildSwitchRow(
            icon: Icons.vibration,
            label: '触觉反馈',
            subtitle: '按下按钮时震动反馈',
            value: _hapticFeedback,
            onChanged: (value) {
              setState(() => _hapticFeedback = value);
              _markDirty();
            },
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
        onChanged: (value) {
          setState(() => _vibrateOnAlert = value);
          _markDirty();
        },
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
          const Divider(height: 16),
          _buildInfoRow('当前连接', '${_ctrl.host}:${_ctrl.port}'),
        ],
      ),
    );
  }

  Widget _buildTextField({
    required String label,
    required TextEditingController controller,
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
            controller: controller,
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
                style:
                    const TextStyle(color: AppColors.darkNavy, fontSize: 14),
              ),
              Text(
                subtitle,
                style: const TextStyle(
                    color: AppColors.blueGrayDark, fontSize: 11),
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
