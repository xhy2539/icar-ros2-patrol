import 'package:flutter/material.dart';
import 'package:flutter/services.dart';
import 'theme/app_theme.dart';
import 'pages/control_page.dart';
import 'pages/status_page.dart';
import 'pages/sensor_page.dart';
import 'pages/mission_log_page.dart';
import 'pages/settings_page.dart';
import 'services/car_controller.dart';

void main() {
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
    StatusPage(),
    SensorPage(),
    MissionLogPage(),
    SettingsPage(),
  ];

  final List<String> _titles = [
    'iCar 控制台',
    '状态监控',
    '传感器数据',
    '任务日志',
    '设置',
  ];

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      appBar: AppBar(
        title: Text(
          _titles[_currentIndex],
          style: const TextStyle(
            fontSize: 18,
            fontWeight: FontWeight.w600,
          ),
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
      body: IndexedStack(
        index: _currentIndex,
        children: _pages,
      ),
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
            padding: const EdgeInsets.symmetric(horizontal: 8, vertical: 8),
            child: Row(
              mainAxisAlignment: MainAxisAlignment.spaceAround,
              children: [
                _buildNavItem(0, Icons.gamepad, '控制'),
                _buildNavItem(1, Icons.monitor, '状态'),
                _buildNavItem(2, Icons.sensors, '传感器'),
                _buildNavItem(3, Icons.list_alt, '日志'),
                _buildNavItem(4, Icons.settings, '设置'),
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
        padding: const EdgeInsets.symmetric(horizontal: 16, vertical: 8),
        decoration: BoxDecoration(
          color: isSelected
              ? AppColors.orange.withValues(alpha: 0.12)
              : Colors.transparent,
          borderRadius: BorderRadius.circular(12),
        ),
        child: Column(
          mainAxisSize: MainAxisSize.min,
          children: [
            Icon(
              icon,
              color: isSelected ? AppColors.orange : AppColors.blueGray,
              size: isSelected ? 24 : 22,
            ),
            const SizedBox(height: 2),
            Text(
              label,
              style: TextStyle(
                color: isSelected ? AppColors.orange : AppColors.blueGray,
                fontSize: 11,
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
              Text('1. 确保手机和小车在同一网络下 (小车 IP: 10.90.164.83)',
                  style: TextStyle(color: AppColors.blueGrayDark, fontSize: 13)),
              SizedBox(height: 8),
              Text('2. 在控制页面输入小车 IP 地址并点击连接',
                  style: TextStyle(color: AppColors.blueGrayDark, fontSize: 13)),
              SizedBox(height: 8),
              Text('3. 连接成功后可使用方向按钮控制小车',
                  style: TextStyle(color: AppColors.blueGrayDark, fontSize: 13)),
              SizedBox(height: 8),
              Text('4. 状态页面查看摄像头画面和系统信息',
                  style: TextStyle(color: AppColors.blueGrayDark, fontSize: 13)),
              SizedBox(height: 8),
              Text('5. 传感器页面查看环境数据实时监测',
                  style: TextStyle(color: AppColors.blueGrayDark, fontSize: 13)),
              SizedBox(height: 8),
              Text('6. 任务日志记录巡检过程的所有事件',
                  style: TextStyle(color: AppColors.blueGrayDark, fontSize: 13)),
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
