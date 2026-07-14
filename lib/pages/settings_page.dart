import 'dart:convert';
import 'dart:io';
import 'package:flutter/material.dart';
import 'package:shared_preferences/shared_preferences.dart';
import '../theme/app_theme.dart';
import '../services/car_controller.dart';
import '../services/cloud_protocol.dart';

class SettingsPage extends StatefulWidget {
  const SettingsPage({super.key});

  @override
  State<SettingsPage> createState() => _SettingsPageState();
}

class _SettingsPageState extends State<SettingsPage> {
  final CarController _ctrl = CarController.instance;

  late String _carIp;
  late int _wsPort;
  late CarConnectionMode _connectionMode;
  late String _mqttHost;
  late int _mqttPort;
  late String _mqttUser;
  late String _mqttPassword;
  late String _mqttTopicPrefix;
  late String _deviceId;
  late bool _mqttTls;
  late double _defaultSpeed;
  late bool _autoReconnect;
  late bool _hapticFeedback;
  bool _vibrateOnAlert = true;
  bool _alertSoundEnabled = true;
  bool _obstacleAvoidanceEnabled = true;

  bool _dirty = false; // 是否有未保存的更改
  bool _saving = false;
  bool _checkingConnection = false;
  String? _connectionDiagnostic;

  late final TextEditingController _ipCtrl;
  late final TextEditingController _portCtrl;
  late final TextEditingController _mqttHostCtrl;
  late final TextEditingController _mqttPortCtrl;
  late final TextEditingController _mqttUserCtrl;
  late final TextEditingController _mqttPasswordCtrl;
  late final TextEditingController _mqttTopicPrefixCtrl;
  late final TextEditingController _deviceIdCtrl;

  @override
  void initState() {
    super.initState();
    _carIp = _ctrl.host;
    _wsPort = _ctrl.port;
    _connectionMode = _ctrl.connectionMode;
    _mqttHost = _ctrl.mqttHost;
    _mqttPort = _ctrl.mqttPort;
    _mqttUser = _ctrl.mqttUser;
    _mqttPassword = _ctrl.mqttPassword;
    _mqttTopicPrefix = _ctrl.mqttTopicPrefix;
    _deviceId = _ctrl.deviceId;
    _mqttTls = _ctrl.mqttTls;
    _defaultSpeed = _ctrl.speed;
    _autoReconnect = _ctrl.autoReconnect;
    _hapticFeedback = _ctrl.hapticEnabled;

    _ipCtrl = TextEditingController(text: _carIp);
    _portCtrl = TextEditingController(text: _wsPort.toString());
    _mqttHostCtrl = TextEditingController(text: _mqttHost);
    _mqttPortCtrl = TextEditingController(text: _mqttPort.toString());
    _mqttUserCtrl = TextEditingController(text: _mqttUser);
    _mqttPasswordCtrl = TextEditingController(text: _mqttPassword);
    _mqttTopicPrefixCtrl = TextEditingController(text: _mqttTopicPrefix);
    _deviceIdCtrl = TextEditingController(text: _deviceId);

    _loadPersisted();
  }

  @override
  void dispose() {
    _ipCtrl.dispose();
    _portCtrl.dispose();
    _mqttHostCtrl.dispose();
    _mqttPortCtrl.dispose();
    _mqttUserCtrl.dispose();
    _mqttPasswordCtrl.dispose();
    _mqttTopicPrefixCtrl.dispose();
    _deviceIdCtrl.dispose();
    super.dispose();
  }

  Future<void> _loadPersisted() async {
    final prefs = await SharedPreferences.getInstance();
    setState(() {
      _carIp = prefs.getString('car_ip') ?? _ctrl.host;
      _wsPort = prefs.getInt('ws_port') ?? _ctrl.port;
      _connectionMode = CarConnectionModeX.fromStorage(
        prefs.getString('connection_mode'),
      );
      _mqttHost = prefs.getString('mqtt_host') ?? _ctrl.mqttHost;
      _mqttPort = prefs.getInt('mqtt_port') ?? _ctrl.mqttPort;
      _mqttUser = prefs.getString('mqtt_user') ?? _ctrl.mqttUser;
      _mqttPassword = prefs.getString('mqtt_password') ?? _ctrl.mqttPassword;
      _mqttTopicPrefix =
          prefs.getString('mqtt_topic_prefix') ?? _ctrl.mqttTopicPrefix;
      _deviceId = prefs.getString('mqtt_device_id') ?? _ctrl.deviceId;
      _mqttTls = prefs.getBool('mqtt_tls') ?? _ctrl.mqttTls;
      _defaultSpeed = prefs.getDouble('default_speed') ?? _ctrl.speed;
      _autoReconnect = prefs.getBool('auto_reconnect') ?? _ctrl.autoReconnect;
      _hapticFeedback = prefs.getBool('haptic_feedback') ?? _ctrl.hapticEnabled;
      _vibrateOnAlert = prefs.getBool('vibrate_on_alert') ?? true;
      _alertSoundEnabled =
          prefs.getBool('alert_sound_enabled') ?? _ctrl.alertSoundEnabled;
      _obstacleAvoidanceEnabled =
          prefs.getBool('obstacle_avoidance_enabled') ??
          _ctrl.obstacleAvoidanceEnabled;

      _ipCtrl.text = _carIp;
      _portCtrl.text = _wsPort.toString();
      _mqttHostCtrl.text = _mqttHost;
      _mqttPortCtrl.text = _mqttPort.toString();
      _mqttUserCtrl.text = _mqttUser;
      _mqttPasswordCtrl.text = _mqttPassword;
      _mqttTopicPrefixCtrl.text = _mqttTopicPrefix;
      _deviceIdCtrl.text = _deviceId;
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
    await prefs.setString('connection_mode', _connectionMode.storageValue);
    await prefs.setString('mqtt_host', _mqttHost);
    await prefs.setInt('mqtt_port', _mqttPort);
    await prefs.setString('mqtt_user', _mqttUser);
    await prefs.setString('mqtt_password', _mqttPassword);
    await prefs.setString('mqtt_topic_prefix', _mqttTopicPrefix);
    await prefs.setString('mqtt_device_id', _deviceId);
    await prefs.setBool('mqtt_tls', _mqttTls);
    await prefs.setDouble('default_speed', _defaultSpeed);
    await prefs.setBool('auto_reconnect', _autoReconnect);
    await prefs.setBool('haptic_feedback', _hapticFeedback);
    await prefs.setBool('vibrate_on_alert', _vibrateOnAlert);
    await prefs.setBool('alert_sound_enabled', _alertSoundEnabled);
    await prefs.setBool(
      'obstacle_avoidance_enabled',
      _obstacleAvoidanceEnabled,
    );

    // 应用到 CarController
    await _ctrl.updateSettings(
      connectionMode: _connectionMode,
      host: _carIp,
      port: _wsPort,
      mqttHost: _mqttHost,
      mqttPort: _mqttPort,
      mqttUser: _mqttUser,
      mqttPassword: _mqttPassword,
      mqttTopicPrefix: _mqttTopicPrefix,
      deviceId: _deviceId,
      mqttTls: _mqttTls,
      speed: _defaultSpeed,
      autoReconnect: _autoReconnect,
      hapticEnabled: _hapticFeedback,
      alertSoundEnabled: _alertSoundEnabled,
      obstacleAvoidanceEnabled: _obstacleAvoidanceEnabled,
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
              _buildConnectionDiagnostic(),
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
                              strokeWidth: 2,
                              color: Colors.white,
                            ),
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
          Row(
            children: [
              Icon(
                _connectionMode == CarConnectionMode.cloud
                    ? Icons.cloud
                    : Icons.wifi,
                color: AppColors.blueGray,
                size: 18,
              ),
              const SizedBox(width: 10),
              const Expanded(
                child: Text('连接模式', style: TextStyle(color: AppColors.darkNavy, fontSize: 14)),
              ),
              const SizedBox(width: 8),
              GestureDetector(
                onTap: () { setState(() => _connectionMode = CarConnectionMode.local); _markDirty(); },
                child: Container(
                  padding: const EdgeInsets.symmetric(horizontal: 14, vertical: 8),
                  decoration: BoxDecoration(
                    color: _connectionMode == CarConnectionMode.local ? AppColors.bluePurple : AppColors.surfaceAlt,
                    borderRadius: BorderRadius.circular(8),
                  ),
                  child: Text('局域网', style: TextStyle(color: _connectionMode == CarConnectionMode.local ? Colors.white : AppColors.blueGray, fontSize: 12, fontWeight: FontWeight.w600)),
                ),
              ),
              const SizedBox(width: 4),
              GestureDetector(
                onTap: () { setState(() => _connectionMode = CarConnectionMode.cloud); _markDirty(); },
                child: Container(
                  padding: const EdgeInsets.symmetric(horizontal: 14, vertical: 8),
                  decoration: BoxDecoration(
                    color: _connectionMode == CarConnectionMode.cloud ? AppColors.bluePurple : AppColors.surfaceAlt,
                    borderRadius: BorderRadius.circular(8),
                  ),
                  child: Text('☁️ 云端', style: TextStyle(color: _connectionMode == CarConnectionMode.cloud ? Colors.white : AppColors.blueGray, fontSize: 12, fontWeight: FontWeight.w600)),
                ),
              ),
            ],
          ),
          const SizedBox(height: 16),
          if (_connectionMode == CarConnectionMode.local) ...[
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
                final port = int.tryParse(value);
                if (port != null && port > 0 && port < 65536) {
                  _wsPort = port;
                  _markDirty();
                }
              },
            ),
          ] else ...[
            _buildTextField(
              label: 'MQTT 服务器',
              controller: _mqttHostCtrl,
              icon: Icons.cloud_queue,
              onChanged: (value) {
                _mqttHost = value.trim();
                _markDirty();
              },
            ),
            const SizedBox(height: 16),
            _buildTextField(
              label: 'MQTT 端口',
              controller: _mqttPortCtrl,
              icon: Icons.lan,
              keyboardType: TextInputType.number,
              onChanged: (value) {
                final port = int.tryParse(value);
                if (port != null && port > 0 && port < 65536) {
                  _mqttPort = port;
                  _markDirty();
                }
              },
            ),
            const SizedBox(height: 16),
            _buildTextField(
              label: 'MQTT 用户名',
              controller: _mqttUserCtrl,
              icon: Icons.person,
              onChanged: (value) {
                _mqttUser = value;
                _markDirty();
              },
            ),
            const SizedBox(height: 16),
            _buildTextField(
              label: 'MQTT 密码',
              controller: _mqttPasswordCtrl,
              icon: Icons.password,
              obscureText: true,
              onChanged: (value) {
                _mqttPassword = value;
                _markDirty();
              },
            ),
            const SizedBox(height: 16),
            _buildTextField(
              label: 'Topic 前缀',
              controller: _mqttTopicPrefixCtrl,
              icon: Icons.account_tree,
              onChanged: (value) {
                _mqttTopicPrefix = value.trim();
                _markDirty();
              },
            ),
            const SizedBox(height: 16),
            _buildTextField(
              label: '设备 ID（可空）',
              controller: _deviceIdCtrl,
              icon: Icons.precision_manufacturing,
              onChanged: (value) {
                _deviceId = value.trim();
                _markDirty();
              },
            ),
            const SizedBox(height: 16),
            _buildSwitchRow(
              icon: Icons.lock,
              label: 'MQTT TLS',
              subtitle: _mqttTls ? '使用加密连接' : '当前为测试用明文连接',
              value: _mqttTls,
              onChanged: (value) {
                setState(() => _mqttTls = value);
                _markDirty();
              },
            ),
          ],
          const SizedBox(height: 16),
          Container(
            padding: const EdgeInsets.all(12),
            decoration: BoxDecoration(
              color: AppColors.surfaceAlt,
              borderRadius: BorderRadius.circular(12),
            ),
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                Row(
                  children: [
                    const Icon(
                      Icons.info_outline,
                      color: AppColors.bluePurple,
                      size: 16,
                    ),
                    const SizedBox(width: 8),
                    Text(
                      _connectionMode == CarConnectionMode.cloud
                          ? '远程连接说明'
                          : 'WiFi 热点配置',
                      style: const TextStyle(
                        color: AppColors.bluePurple,
                        fontSize: 13,
                        fontWeight: FontWeight.w600,
                      ),
                    ),
                  ],
                ),
                const SizedBox(height: 8),
                Text(
                  _connectionMode == CarConnectionMode.cloud
                      ? '手机和小车无需连接同一热点。云桥在线后可查看状态、下发巡检并使用带超时保护的方向控制。'
                      : '热点: ohcar121 / 12345678\nVNC 密码: yahboom\n底盘串口: /dev/myserial (ttyUSB1)',
                  style: const TextStyle(
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

  Future<void> _checkLocalConnection() async {
    if (_connectionMode == CarConnectionMode.cloud) {
      setState(() => _connectionDiagnostic = '云端模式请通过“小车在线”状态确认 MQTT 连接。');
      return;
    }
    setState(() {
      _checkingConnection = true;
      _connectionDiagnostic = null;
    });
    final host = _ipCtrl.text.trim();
    final port = int.tryParse(_portCtrl.text) ?? _wsPort;
    final client = HttpClient()..connectionTimeout = const Duration(seconds: 4);
    try {
      final request = await client.getUrl(
        Uri.parse('http://$host:$port/health'),
      );
      final response = await request.close().timeout(
        const Duration(seconds: 5),
      );
      final body = await utf8.decodeStream(response);
      if (response.statusCode != HttpStatus.ok) {
        throw HttpException('HTTP ${response.statusCode}');
      }
      final json = jsonDecode(body) as Map<String, dynamic>;
      final camera = json['camera'] as Map<String, dynamic>? ?? const {};
      final bridge = json['bridge_ready'] == true;
      final raw = camera['raw_ready'] == true;
      final annotated = camera['annotated_ready'] == true;
      setState(() {
        _connectionDiagnostic =
            '控制桥 ${bridge ? '正常' : '异常'} · 原始视频 ${raw ? '正常' : '异常'} · 标注视频 ${annotated ? '正常' : '未就绪'}';
      });
    } catch (error) {
      setState(() => _connectionDiagnostic = '连接检查失败：$error');
    } finally {
      client.close(force: true);
      if (mounted) setState(() => _checkingConnection = false);
    }
  }

  Widget _buildConnectionDiagnostic() {
    final text = _connectionDiagnostic;
    return AppCard(
      title: '连接诊断',
      icon: Icons.health_and_safety,
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Text(
            text ?? '检查控制桥、原始视频与标注视频是否可用。',
            style: TextStyle(
              color: text?.contains('失败') == true
                  ? AppColors.errorRed
                  : AppColors.blueGrayDark,
              fontSize: 13,
            ),
          ),
          const SizedBox(height: 12),
          OutlinedButton.icon(
            onPressed: _checkingConnection ? null : _checkLocalConnection,
            icon: _checkingConnection
                ? const SizedBox(
                    width: 16,
                    height: 16,
                    child: CircularProgressIndicator(strokeWidth: 2),
                  )
                : const Icon(Icons.network_check),
            label: Text(_checkingConnection ? '检查中…' : '检查当前连接'),
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
      child: Column(
        children: [
          _buildSwitchRow(
            icon: Icons.volume_up_outlined,
            label: '告警声音',
            subtitle: '同步关闭车端蜂鸣器；不影响安全拦截',
            value: _alertSoundEnabled,
            onChanged: (value) {
              setState(() => _alertSoundEnabled = value);
              _markDirty();
            },
          ),
          const Divider(height: 24),
          _buildSwitchRow(
            icon: Icons.shield_outlined,
            label: '避障拦截',
            subtitle: '关闭后允许通过障碍区域，仍保留急停；仅限确认周边安全时使用',
            value: _obstacleAvoidanceEnabled,
            onChanged: (value) {
              setState(() => _obstacleAvoidanceEnabled = value);
              _markDirty();
            },
          ),
        ],
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
          _buildInfoRow('技术栈', 'Flutter + WebSocket + MQTT'),
          const Divider(height: 16),
          _buildInfoRow('当前连接', _ctrl.connectionLabel),
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
    bool obscureText = false,
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
            obscureText: obscureText,
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
                style: const TextStyle(
                  color: AppColors.blueGrayDark,
                  fontSize: 11,
                ),
              ),
            ],
          ),
        ),
        Switch(value: value, onChanged: onChanged),
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
