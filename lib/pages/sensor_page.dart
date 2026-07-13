import 'package:flutter/material.dart';
import '../theme/app_theme.dart';
import '../services/car_controller.dart';
import '../services/data_models.dart';

class SensorPage extends StatefulWidget {
  const SensorPage({super.key});

  @override
  State<SensorPage> createState() => _SensorPageState();
}

class _SensorPageState extends State<SensorPage> {
  final CarController _ctrl = CarController.instance;

  @override
  void initState() {
    super.initState();
    _ctrl.addListener(_onCtrlChanged);
  }

  @override
  void dispose() {
    _ctrl.removeListener(_onCtrlChanged);
    super.dispose();
  }

  void _onCtrlChanged() {
    if (mounted) setState(() {});
  }

  /// Whether all env data values are zero (default/uninitialized state).
  bool get _isWaiting {
    final d = _ctrl.latestEnvData;
    return d.temperature == 0 &&
        d.humidity == 0 &&
        d.smoke == 0 &&
        d.pm25 == 0 &&
        d.light == 0 &&
        d.pressure == 0;
  }

  @override
  Widget build(BuildContext context) {
    final env = _ctrl.latestEnvData;

    final sensors = <_SensorDisplay>[
      _SensorDisplay(
        name: '温度',
        unit: '°C',
        icon: Icons.thermostat,
        color: AppColors.orange,
        value: env.temperature,
        threshold: EnvData.thresholds['temperature']!,
        isAlert: env.isTempAlert,
        min: 0,
        max: 50,
      ),
      _SensorDisplay(
        name: '湿度',
        unit: '%',
        icon: Icons.water_drop,
        color: AppColors.bluePurple,
        value: env.humidity,
        threshold: EnvData.thresholds['humidity']!,
        isAlert: env.isHumidityAlert,
        min: 0,
        max: 100,
      ),
      _SensorDisplay(
        name: 'PM2.5',
        unit: 'μg/m³',
        icon: Icons.air,
        color: AppColors.darkNavy,
        value: env.pm25,
        threshold: EnvData.thresholds['pm25']!,
        isAlert: env.isPm25Alert,
        min: 0,
        max: 500,
      ),
      _SensorDisplay(
        name: '烟雾',
        unit: 'ppm',
        icon: Icons.local_fire_department,
        color: AppColors.orange,
        value: env.smoke,
        threshold: EnvData.thresholds['smoke']!,
        isAlert: env.isSmokeAlert,
        min: 0,
        max: 1000,
      ),
      _SensorDisplay(
        name: '光照',
        unit: 'lux',
        icon: Icons.wb_sunny,
        color: AppColors.orangeDark,
        value: env.light,
        threshold: EnvData.thresholds['light']!,
        isAlert: env.isLightAlert,
        min: 0,
        max: 1000,
      ),
      _SensorDisplay(
        name: '气压',
        unit: 'hPa',
        icon: Icons.compress,
        color: AppColors.bluePurple,
        value: env.pressure,
        threshold: EnvData.thresholds['pressure']!,
        isAlert: env.isPressureAlert,
        min: 900,
        max: 1100,
      ),
    ];

    final int alertCount = sensors.where((s) => s.isAlert).length;
    final int normalCount = sensors.length - alertCount;
    final bool waiting = _isWaiting;

    return Scaffold(
      body: SafeArea(
        child: Column(
          children: [
            // 顶部汇总
            _buildSummaryBar(sensors.length, normalCount, alertCount, waiting),
            // 传感器列表
            Expanded(
              child: ListView.builder(
                padding: const EdgeInsets.symmetric(vertical: 8),
                itemCount: sensors.length,
                itemBuilder: (context, index) {
                  return _buildSensorCard(sensors[index]);
                },
              ),
            ),
          ],
        ),
      ),
    );
  }

  Widget _buildSummaryBar(int total, int normalCount, int alertCount, bool waiting) {
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
      child: waiting
          ? Center(
              child: Text(
                '等待传感器数据...',
                style: TextStyle(
                  color: AppColors.blueGray.withValues(alpha: 0.8),
                  fontSize: 15,
                  fontWeight: FontWeight.w500,
                ),
              ),
            )
          : Row(
              mainAxisAlignment: MainAxisAlignment.spaceAround,
              children: [
                _buildSummaryItem(
                  '传感器总数',
                  '$total',
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

  Widget _buildSummaryItem(
      String label, String value, IconData icon, Color color) {
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

  Widget _buildSensorCard(_SensorDisplay sensor) {
    final bool isAlert = sensor.isAlert;
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
                      '阈值: ${sensor.threshold.toStringAsFixed(sensor.threshold == sensor.threshold.roundToDouble() ? 0 : 1)} ${sensor.unit}',
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
                left: MediaQuery.of(context).size.width *
                        thresholdProgress *
                        0.85 -
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

/// Lightweight display-only model for sensor cards.
/// Values are read from [EnvData] at build time; thresholds come from [EnvData.thresholds].
class _SensorDisplay {
  final String name;
  final String unit;
  final IconData icon;
  final Color color;
  final double value;
  final double threshold;
  final bool isAlert;
  final double min;
  final double max;

  const _SensorDisplay({
    required this.name,
    required this.unit,
    required this.icon,
    required this.color,
    required this.value,
    required this.threshold,
    required this.isAlert,
    required this.min,
    required this.max,
  });
}
