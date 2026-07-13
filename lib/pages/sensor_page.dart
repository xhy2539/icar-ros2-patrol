import 'dart:async';
import 'dart:math';
import 'package:flutter/material.dart';
import '../theme/app_theme.dart';
import '../services/car_controller.dart';

class SensorPage extends StatefulWidget {
  const SensorPage({super.key});

  @override
  State<SensorPage> createState() => _SensorPageState();
}

class _SensorPageState extends State<SensorPage> {
  final CarController _ctrl = CarController.instance;
  Timer? _timer;
  final Random _random = Random();

  // 传感器数据模型
  late List<SensorData> _sensors;

  @override
  void initState() {
    super.initState();
    _sensors = [
      SensorData(
        name: '温度',
        unit: '°C',
        icon: Icons.thermostat,
        value: 26.5,
        min: 0,
        max: 50,
        threshold: 38,
        color: AppColors.orange,
      ),
      SensorData(
        name: '湿度',
        unit: '%',
        icon: Icons.water_drop,
        value: 45.2,
        min: 0,
        max: 100,
        threshold: 80,
        color: AppColors.bluePurple,
      ),
      SensorData(
        name: 'PM2.5',
        unit: 'μg/m³',
        icon: Icons.air,
        value: 35.0,
        min: 0,
        max: 500,
        threshold: 75,
        color: AppColors.darkNavy,
      ),
      SensorData(
        name: '烟雾',
        unit: 'ppm',
        icon: Icons.local_fire_department,
        value: 120.0,
        min: 0,
        max: 1000,
        threshold: 300,
        color: AppColors.orange,
      ),
      SensorData(
        name: '光照',
        unit: 'lux',
        icon: Icons.wb_sunny,
        value: 450.0,
        min: 0,
        max: 1000,
        threshold: 800,
        color: AppColors.orangeDark,
      ),
      SensorData(
        name: '气压',
        unit: 'hPa',
        icon: Icons.compress,
        value: 1013.2,
        min: 900,
        max: 1100,
        threshold: 1050,
        color: AppColors.bluePurple,
      ),
    ];

    _ctrl.addListener(_onControllerChanged);

    // 模拟数据刷新
    _timer = Timer.periodic(const Duration(seconds: 2), (timer) {
      setState(() {
        if (_ctrl.latestSensorEnv != null) return;
        for (var sensor in _sensors) {
          double delta = (_random.nextDouble() - 0.5) * 2;
          sensor.value = (sensor.value + delta)
              .clamp(sensor.min.toDouble(), sensor.max.toDouble())
              .toDouble();
        }
      });
    });
  }

  void _onControllerChanged() {
    if (!mounted) return;
    final data = _ctrl.latestSensorEnv;
    if (data == null) return;
    const keys = {
      '温度': 'temperature',
      '湿度': 'humidity',
      'PM2.5': 'pm25',
      '烟雾': 'smoke',
      '光照': 'light',
      '气压': 'pressure',
    };
    setState(() {
      for (final sensor in _sensors) {
        final value = data[keys[sensor.name]];
        if (value is num) sensor.value = value.toDouble();
      }
      final alert = _ctrl.latestSensorAlert;
      if (alert != null) {
        final sensorType = alert['sensor_type']?.toString();
        final threshold = alert['threshold'];
        for (final sensor in _sensors) {
          if (keys[sensor.name] == sensorType && threshold is num) {
            sensor.threshold = threshold.toDouble();
          }
        }
      }
    });
  }

  @override
  void dispose() {
    _ctrl.removeListener(_onControllerChanged);
    _timer?.cancel();
    super.dispose();
  }

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      body: SafeArea(
        child: Column(
          children: [
            // 顶部汇总
            _buildSummaryBar(),
            // 传感器列表
            Expanded(
              child: ListView.builder(
                padding: const EdgeInsets.symmetric(vertical: 8),
                itemCount: _sensors.length,
                itemBuilder: (context, index) {
                  return _buildSensorCard(_sensors[index]);
                },
              ),
            ),
          ],
        ),
      ),
    );
  }

  Widget _buildSummaryBar() {
    int normalCount = _sensors.where((s) => !s.isAlert).length;
    int alertCount = _sensors.where((s) => s.isAlert).length;

    return Container(
      margin: const EdgeInsets.all(16),
      padding: const EdgeInsets.all(16),
      decoration: BoxDecoration(
        color: AppColors.surface,
        borderRadius: BorderRadius.circular(16),
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
      child: Row(
        mainAxisAlignment: MainAxisAlignment.spaceAround,
        children: [
          _buildSummaryItem(
            '传感器总数',
            '${_sensors.length}',
            Icons.sensors,
            AppColors.bluePurple,
          ),
          Container(
            width: 1,
            height: 40,
            color: AppColors.blueGray.withValues(alpha: 0.3),
          ),
          _buildSummaryItem(
            '正常',
            '$normalCount',
            Icons.check_circle,
            AppColors.successGreen,
          ),
          Container(
            width: 1,
            height: 40,
            color: AppColors.blueGray.withValues(alpha: 0.3),
          ),
          _buildSummaryItem(
            '告警',
            '$alertCount',
            Icons.warning,
            alertCount > 0 ? AppColors.errorRed : AppColors.blueGray,
          ),
        ],
      ),
    );
  }

  Widget _buildSummaryItem(String label, String value, IconData icon, Color color) {
    return Column(
      children: [
        Icon(icon, color: color, size: 24),
        const SizedBox(height: 4),
        Text(
          value,
          style: TextStyle(
            color: color,
            fontSize: 20,
            fontWeight: FontWeight.bold,
          ),
        ),
        Text(
          label,
          style: const TextStyle(
            color: AppColors.blueGrayDark,
            fontSize: 11,
          ),
        ),
      ],
    );
  }

  Widget _buildSensorCard(SensorData sensor) {
    bool isAlert = sensor.isAlert;
    double progress = (sensor.value - sensor.min) / (sensor.max - sensor.min);
    double thresholdProgress =
        (sensor.threshold - sensor.min) / (sensor.max - sensor.min);

    return Container(
      margin: const EdgeInsets.symmetric(horizontal: 16, vertical: 6),
      padding: const EdgeInsets.all(16),
      decoration: BoxDecoration(
        color: AppColors.surface,
        borderRadius: BorderRadius.circular(16),
        border: Border.all(
          color: isAlert
              ? AppColors.errorRed.withValues(alpha: 0.5)
              : AppColors.blueGray.withValues(alpha: 0.15),
          width: isAlert ? 1.5 : 1,
        ),
        boxShadow: [
          BoxShadow(
            color: Colors.black.withValues(alpha: 0.03),
            blurRadius: 6,
            offset: const Offset(0, 2),
          ),
        ],
      ),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          // 标题行
          Row(
            children: [
              Container(
                padding: const EdgeInsets.all(8),
                decoration: BoxDecoration(
                  color: sensor.color.withValues(alpha: 0.12),
                  borderRadius: BorderRadius.circular(10),
                ),
                child: Icon(
                  sensor.icon,
                  color: sensor.color,
                  size: 20,
                ),
              ),
              const SizedBox(width: 12),
              Expanded(
                child: Column(
                  crossAxisAlignment: CrossAxisAlignment.start,
                  children: [
                    Text(
                      sensor.name,
                      style: const TextStyle(
                        color: AppColors.darkNavy,
                        fontSize: 16,
                        fontWeight: FontWeight.w600,
                      ),
                    ),
                    Text(
                      '阈值: ${sensor.threshold} ${sensor.unit}',
                      style: const TextStyle(
                        color: AppColors.blueGrayDark,
                        fontSize: 12,
                      ),
                    ),
                  ],
                ),
              ),
              // 数值
              Text(
                sensor.value.toStringAsFixed(1),
                style: TextStyle(
                  color: isAlert ? AppColors.errorRed : sensor.color,
                  fontSize: 28,
                  fontWeight: FontWeight.bold,
                ),
              ),
              const SizedBox(width: 4),
              Text(
                sensor.unit,
                style: const TextStyle(
                  color: AppColors.blueGrayDark,
                  fontSize: 12,
                ),
              ),
              if (isAlert) ...[
                const SizedBox(width: 8),
                const StatusBadge(
                  text: '超标',
                  color: AppColors.errorRed,
                ),
              ],
            ],
          ),
          const SizedBox(height: 12),
          // 进度条
          Stack(
            children: [
              // 底条
              Container(
                height: 6,
                decoration: BoxDecoration(
                  color: AppColors.blueGray.withValues(alpha: 0.15),
                  borderRadius: BorderRadius.circular(3),
                ),
              ),
              // 当前值
              FractionallySizedBox(
                widthFactor: progress.clamp(0.0, 1.0),
                child: Container(
                  decoration: BoxDecoration(
                    color: isAlert ? AppColors.errorRed : sensor.color,
                    borderRadius: BorderRadius.circular(3),
                  ),
                ),
              ),
              // 阈值线
              Positioned(
                left: MediaQuery.of(context).size.width * thresholdProgress *
                        0.85 - // 估算宽度
                    32,
                child: Container(
                  width: 2,
                  height: 6,
                  color: AppColors.darkNavy.withValues(alpha: 0.4),
                ),
              ),
            ],
          ),
          const SizedBox(height: 6),
          // 范围标注
          Row(
            mainAxisAlignment: MainAxisAlignment.spaceBetween,
            children: [
              Text(
                '${sensor.min}',
                style: TextStyle(
                  color: AppColors.blueGray.withValues(alpha: 0.6),
                  fontSize: 10,
                ),
              ),
              Text(
                '${sensor.max}',
                style: TextStyle(
                  color: AppColors.blueGray.withValues(alpha: 0.6),
                  fontSize: 10,
                ),
              ),
            ],
          ),
        ],
      ),
    );
  }
}

class SensorData {
  final String name;
  final String unit;
  final IconData icon;
  double value;
  final double min;
  final double max;
  double threshold;
  final Color color;

  SensorData({
    required this.name,
    required this.unit,
    required this.icon,
    required this.value,
    required this.min,
    required this.max,
    required this.threshold,
    required this.color,
  });

  bool get isAlert => value > threshold;
}
