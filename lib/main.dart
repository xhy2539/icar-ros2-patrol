import 'package:flutter/material.dart';
import 'package:flutter/services.dart';
import 'package:shared_preferences/shared_preferences.dart';
import 'theme/app_theme.dart';
import 'pages/control_page.dart';
import 'pages/vision_page.dart';
import 'pages/status_page.dart';
import 'pages/sensor_page.dart';
import 'pages/mission_page.dart';
import 'pages/settings_page.dart';
import 'services/car_controller.dart';
import 'services/cloud_protocol.dart';

void main() async {
  WidgetsFlutterBinding.ensureInitialized();
  SystemChrome.setPreferredOrientations([
    DeviceOrientation.portraitUp,
    DeviceOrientation.portraitDown,
  ]);
  SystemChrome.setSystemUIOverlayStyle(
    const SystemUiOverlayStyle(
      statusBarColor: Colors.transparent,
      statusBarIconBrightness: Brightness.dark,
    ),
  );
  // 初始化小车控制器单例
  CarController.instance;
  // 从 SharedPreferences 加载持久化设置
  final prefs = await SharedPreferences.getInstance();
  final savedHost = prefs.getString('car_ip');
  // 当前实车在校园网地址；旧热点地址自动迁移，用户仍可在设置页覆盖。
  final carHost = savedHost == null || savedHost.startsWith('192.168.137.')
      ? '10.247.5.83'
      : savedHost;
  if (savedHost != carHost) {
    await prefs.setString('car_ip', carHost);
  }
  await CarController.instance.updateSettings(
    connectionMode: CarConnectionModeX.fromStorage(
      prefs.getString('connection_mode'),
    ),
    host: carHost,
    port: prefs.getInt('ws_port'),
    mqttHost: prefs.getString('mqtt_host'),
    mqttPort: prefs.getInt('mqtt_port'),
    mqttUser: prefs.getString('mqtt_user'),
    mqttPassword: prefs.getString('mqtt_password'),
    mqttTopicPrefix: prefs.getString('mqtt_topic_prefix'),
    deviceId: prefs.getString('mqtt_device_id'),
    mqttTls: prefs.getBool('mqtt_tls'),
    speed: prefs.getDouble('default_speed'),
    autoReconnect: prefs.getBool('auto_reconnect'),
    hapticEnabled: prefs.getBool('haptic_feedback'),
    alertSoundEnabled: prefs.getBool('alert_sound_enabled'),
    obstacleAvoidanceEnabled: prefs.getBool('obstacle_avoidance_enabled'),
  );
  runApp(const ICarApp());
}

class ICarApp extends StatelessWidget {
  const ICarApp({super.key});

  @override
  Widget build(BuildContext context) {
    return MaterialApp(
      title: 'iCar 巡检控制端',
      debugShowCheckedModeBanner: false,
      theme: AppTheme.lightTheme,
      home: const MainScreen(),
    );
  }
}

class MainScreen extends StatefulWidget {
  const MainScreen({super.key});

  @override
  State<MainScreen> createState() => _MainScreenState();
}

class _MainScreenState extends State<MainScreen> {
  int _currentIndex = 0;

  final List<Widget> _pages = const [
    ControlPage(),
    VisionPage(),
    StatusPage(),
    SensorPage(),
    MissionPage(),
    SettingsPage(),
  ];

  final List<String> _titles = [
    'iCar 控制台',
    '视觉监控',
    '状态监控',
    '传感器数据',
    '智能任务',
    '设置',
  ];

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      appBar: AppBar(
        title: Text(
          _titles[_currentIndex],
          style: const TextStyle(fontSize: 18, fontWeight: FontWeight.w600),
        ),
        actions: [
          if (_currentIndex == 0)
            Padding(
              padding: const EdgeInsets.only(right: 8),
              child: IconButton(
                icon: const Icon(Icons.help_outline, color: AppColors.blueGray),
                onPressed: _showHelpDialog,
              ),
            ),
        ],
      ),
      body: IndexedStack(index: _currentIndex, children: _pages),
      bottomNavigationBar: Container(
        decoration: BoxDecoration(
          color: AppColors.surface,
          boxShadow: [
            BoxShadow(
              color: Colors.black.withValues(alpha: 0.06),
              blurRadius: 8,
              offset: const Offset(0, -2),
            ),
          ],
        ),
        child: SafeArea(
          child: Padding(
            padding: const EdgeInsets.symmetric(horizontal: 4, vertical: 8),
            child: Row(
              mainAxisAlignment: MainAxisAlignment.spaceAround,
              children: [
                _buildNavItem(0, Icons.gamepad, '控制'),
                _buildNavItem(1, Icons.visibility, '视觉'),
                _buildNavItem(2, Icons.monitor, '状态'),
                _buildNavItem(3, Icons.sensors, '传感器'),
                _buildNavItem(4, Icons.auto_awesome, '任务'),
                _buildNavItem(5, Icons.settings, '设置'),
              ],
            ),
          ),
        ),
      ),
    );
  }

  Widget _buildNavItem(int index, IconData icon, String label) {
    bool isSelected = _currentIndex == index;
    return GestureDetector(
      onTap: () {
        setState(() => _currentIndex = index);
        HapticFeedback.selectionClick();
      },
      behavior: HitTestBehavior.opaque,
      child: AnimatedContainer(
        duration: const Duration(milliseconds: 200),
        padding: const EdgeInsets.symmetric(horizontal: 10, vertical: 6),
        decoration: BoxDecoration(
          color: isSelected
              ? AppColors.orange.withValues(alpha: 0.12)
              : Colors.transparent,
          borderRadius: BorderRadius.circular(10),
        ),
        child: Column(
          mainAxisSize: MainAxisSize.min,
          children: [
            Icon(
              icon,
              color: isSelected ? AppColors.orange : AppColors.blueGray,
              size: isSelected ? 22 : 20,
            ),
            const SizedBox(height: 1),
            Text(
              label,
              style: TextStyle(
                color: isSelected ? AppColors.orange : AppColors.blueGray,
                fontSize: 10,
                fontWeight: isSelected ? FontWeight.w600 : FontWeight.normal,
              ),
            ),
          ],
        ),
      ),
    );
  }

  void _showHelpDialog() {
    showDialog(
      context: context,
      builder: (context) => AlertDialog(
        backgroundColor: AppColors.surface,
        title: const Text('使用说明', style: TextStyle(color: AppColors.darkNavy)),
        content: const SingleChildScrollView(
          child: Column(
            crossAxisAlignment: CrossAxisAlignment.start,
            children: [
              Text(
                '1. 在设置中选择“局域网直连”或“云端远程”模式',
                style: TextStyle(color: AppColors.blueGrayDark, fontSize: 13),
              ),
              SizedBox(height: 8),
              Text(
                '2. 局域网模式需要连接小车热点；云端模式可使用任意网络',
                style: TextStyle(color: AppColors.blueGrayDark, fontSize: 13),
              ),
              SizedBox(height: 8),
              Text(
                '3. 小车在线后可长按方向键控制，松手或断线会自动停车',
                style: TextStyle(color: AppColors.blueGrayDark, fontSize: 13),
              ),
              SizedBox(height: 8),
              Text(
                '4. 状态页面查看摄像头画面和系统信息',
                style: TextStyle(color: AppColors.blueGrayDark, fontSize: 13),
              ),
              SizedBox(height: 8),
              Text(
                '5. 传感器页面查看环境数据实时监测',
                style: TextStyle(color: AppColors.blueGrayDark, fontSize: 13),
              ),
              SizedBox(height: 8),
              Text(
                '6. 任务日志记录巡检过程的所有事件',
                style: TextStyle(color: AppColors.blueGrayDark, fontSize: 13),
              ),
            ],
          ),
        ),
        actions: [
          TextButton(
            onPressed: () => Navigator.of(context).pop(),
            child: const Text('知道了', style: TextStyle(color: AppColors.orange)),
          ),
        ],
      ),
    );
  }
}
