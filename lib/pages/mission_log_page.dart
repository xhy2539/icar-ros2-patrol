import 'package:flutter/material.dart';
import '../theme/app_theme.dart';

class MissionLogPage extends StatefulWidget {
  const MissionLogPage({super.key});

  @override
  State<MissionLogPage> createState() => _MissionLogPageState();
}

class _MissionLogPageState extends State<MissionLogPage> {
  String _selectedFilter = '全部';

  final List<String> _filters = ['全部', '导航', '检测', '传感器', '系统'];

  // 模拟任务日志数据
  final List<MissionLog> _logs = [
    MissionLog(
      time: '14:32:05',
      type: '系统',
      title: '巡检任务开始',
      detail: '路线: A → B → C, 预计耗时 15 分钟',
      icon: Icons.play_circle,
      color: AppColors.bluePurple,
    ),
    MissionLog(
      time: '14:32:18',
      type: '导航',
      title: '开始导航至巡检点 A',
      detail: '距离: 3.2m, 路径规划: DWA 算法',
      icon: Icons.navigation,
      color: AppColors.successGreen,
    ),
    MissionLog(
      time: '14:33:42',
      type: '导航',
      title: '到达巡检点 A',
      detail: '用时: 1分24秒, 导航状态: 成功',
      icon: Icons.location_on,
      color: AppColors.successGreen,
    ),
    MissionLog(
      time: '14:33:45',
      type: '传感器',
      title: '采集环境数据',
      detail: '温度: 26.3°C, 湿度: 45%, PM2.5: 32μg/m³',
      icon: Icons.sensors,
      color: AppColors.darkNavy,
    ),
    MissionLog(
      time: '14:33:48',
      type: '检测',
      title: '视觉检测完成',
      detail: '检测到: 人员×2, 障碍物×0, 标志物×1',
      icon: Icons.visibility,
      color: AppColors.bluePurple,
    ),
    MissionLog(
      time: '14:34:02',
      type: '传感器',
      title: 'PM2.5 浓度超标',
      detail: '当前值: 82μg/m³, 阈值: 75μg/m³',
      icon: Icons.warning,
      color: AppColors.errorRed,
      isAlert: true,
    ),
    MissionLog(
      time: '14:34:15',
      type: '导航',
      title: '开始导航至巡检点 B',
      detail: '距离: 5.1m, 路径规划: DWA 算法',
      icon: Icons.navigation,
      color: AppColors.successGreen,
    ),
    MissionLog(
      time: '14:35:03',
      type: '系统',
      title: '雷达检测到障碍物',
      detail: '距离: 0.8m, 执行避障策略: 绕行',
      icon: Icons.error_outline,
      color: AppColors.warningOrange,
    ),
    MissionLog(
      time: '14:36:22',
      type: '导航',
      title: '到达巡检点 B',
      detail: '用时: 2分7秒, 导航状态: 成功',
      icon: Icons.location_on,
      color: AppColors.successGreen,
    ),
    MissionLog(
      time: '14:36:25',
      type: '传感器',
      title: '采集环境数据',
      detail: '温度: 27.1°C, 湿度: 42%, PM2.5: 28μg/m³',
      icon: Icons.sensors,
      color: AppColors.darkNavy,
    ),
    MissionLog(
      time: '14:36:28',
      type: '检测',
      title: '视觉检测完成',
      detail: '检测到: 人员×0, 障碍物×1, 标志物×1',
      icon: Icons.visibility,
      color: AppColors.bluePurple,
    ),
    MissionLog(
      time: '14:37:15',
      type: '导航',
      title: '开始导航至巡检点 C',
      detail: '距离: 4.3m, 路径规划: TEB 算法',
      icon: Icons.navigation,
      color: AppColors.successGreen,
    ),
    MissionLog(
      time: '14:38:50',
      type: '导航',
      title: '到达巡检点 C',
      detail: '用时: 1分35秒, 导航状态: 成功',
      icon: Icons.location_on,
      color: AppColors.successGreen,
    ),
    MissionLog(
      time: '14:38:55',
      type: '系统',
      title: '巡检任务完成',
      detail: '总耗时: 6分50秒, 异常: 1, 打卡: 3/3',
      icon: Icons.check_circle,
      color: AppColors.successGreen,
    ),
  ];

  List<MissionLog> get _filteredLogs {
    if (_selectedFilter == '全部') return _logs;
    return _logs.where((log) => log.type == _selectedFilter).toList();
  }

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      body: SafeArea(
        child: Column(
          children: [
            // 统计栏
            _buildStatsBar(),
            // 筛选标签
            _buildFilterBar(),
            // 日志列表
            Expanded(
              child: _buildLogList(),
            ),
          ],
        ),
      ),
    );
  }

  Widget _buildStatsBar() {
    int totalLogs = _logs.length;
    int alertLogs = _logs.where((l) => l.isAlert).length;
    int checkpoints = _logs.where((l) => l.title.contains('到达')).length;

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
          _buildStatItem('日志总数', '$totalLogs', AppColors.bluePurple),
          Container(
            width: 1,
            height: 36,
            color: AppColors.blueGray.withValues(alpha: 0.3),
          ),
          _buildStatItem('巡检打卡', '$checkpoints/3', AppColors.successGreen),
          Container(
            width: 1,
            height: 36,
            color: AppColors.blueGray.withValues(alpha: 0.3),
          ),
          _buildStatItem(
            '异常事件',
            '$alertLogs',
            alertLogs > 0 ? AppColors.errorRed : AppColors.blueGray,
          ),
        ],
      ),
    );
  }

  Widget _buildStatItem(String label, String value, Color color) {
    return Column(
      children: [
        Text(
          value,
          style: TextStyle(
            color: color,
            fontSize: 22,
            fontWeight: FontWeight.bold,
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
    );
  }

  Widget _buildFilterBar() {
    return SizedBox(
      height: 44,
      child: ListView.builder(
        scrollDirection: Axis.horizontal,
        padding: const EdgeInsets.symmetric(horizontal: 16),
        itemCount: _filters.length,
        itemBuilder: (context, index) {
          String filter = _filters[index];
          bool isSelected = filter == _selectedFilter;
          return Padding(
            padding: const EdgeInsets.only(right: 8),
            child: FilterChip(
              label: Text(filter),
              selected: isSelected,
              onSelected: (selected) {
                setState(() => _selectedFilter = filter);
              },
              labelStyle: TextStyle(
                color: isSelected ? Colors.white : AppColors.blueGrayDark,
                fontSize: 13,
                fontWeight: isSelected ? FontWeight.w600 : FontWeight.normal,
              ),
              backgroundColor: AppColors.surface,
              selectedColor: AppColors.orange,
              checkmarkColor: Colors.white,
              side: BorderSide(
                color: isSelected
                    ? AppColors.orange
                    : AppColors.blueGray.withValues(alpha: 0.3),
              ),
              shape: RoundedRectangleBorder(
                borderRadius: BorderRadius.circular(20),
              ),
            ),
          );
        },
      ),
    );
  }

  Widget _buildLogList() {
    final logs = _filteredLogs;
    if (logs.isEmpty) {
      return Center(
        child: Column(
          mainAxisAlignment: MainAxisAlignment.center,
          children: [
            Icon(
              Icons.inbox,
              color: AppColors.blueGray.withValues(alpha: 0.4),
              size: 48,
            ),
            const SizedBox(height: 8),
            Text(
              '暂无日志',
              style: TextStyle(
                color: AppColors.blueGray.withValues(alpha: 0.6),
                fontSize: 14,
              ),
            ),
          ],
        ),
      );
    }

    return ListView.builder(
      padding: const EdgeInsets.symmetric(horizontal: 16, vertical: 8),
      itemCount: logs.length,
      itemBuilder: (context, index) {
        return _buildLogItem(logs[index], index == 0);
      },
    );
  }

  Widget _buildLogItem(MissionLog log, bool isLatest) {
    return Container(
      margin: const EdgeInsets.only(bottom: 12),
      child: Row(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          // 时间轴
          Column(
            children: [
              Container(
                width: 36,
                height: 36,
                decoration: BoxDecoration(
                  color: log.isAlert
                      ? AppColors.errorRed.withValues(alpha: 0.12)
                      : log.color.withValues(alpha: 0.12),
                  borderRadius: BorderRadius.circular(10),
                  border: Border.all(
                    color: log.isAlert
                        ? AppColors.errorRed.withValues(alpha: 0.3)
                        : log.color.withValues(alpha: 0.25),
                  ),
                ),
                child: Icon(
                  log.icon,
                  color: log.isAlert ? AppColors.errorRed : log.color,
                  size: 18,
                ),
              ),
              if (log != _filteredLogs.last)
                Container(
                  width: 2,
                  height: 40,
                  color: AppColors.blueGray.withValues(alpha: 0.2),
                ),
            ],
          ),
          const SizedBox(width: 12),
          // 内容
          Expanded(
            child: Container(
              padding: const EdgeInsets.all(12),
              decoration: BoxDecoration(
                color: AppColors.surface,
                borderRadius: BorderRadius.circular(12),
                border: Border.all(
                  color: log.isAlert
                      ? AppColors.errorRed.withValues(alpha: 0.2)
                      : AppColors.blueGray.withValues(alpha: 0.1),
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
                crossAxisAlignment: CrossAxisAlignment.start,
                children: [
                  Row(
                    children: [
                      // 类型标签
                      Container(
                        padding: const EdgeInsets.symmetric(
                          horizontal: 8,
                          vertical: 2,
                        ),
                        decoration: BoxDecoration(
                          color: log.color.withValues(alpha: 0.1),
                          borderRadius: BorderRadius.circular(4),
                        ),
                        child: Text(
                          log.type,
                          style: TextStyle(
                            color: log.color,
                            fontSize: 10,
                            fontWeight: FontWeight.w600,
                          ),
                        ),
                      ),
                      const Spacer(),
                      Text(
                        log.time,
                        style: const TextStyle(
                          color: AppColors.blueGrayDark,
                          fontSize: 11,
                        ),
                      ),
                    ],
                  ),
                  const SizedBox(height: 6),
                  Text(
                    log.title,
                    style: TextStyle(
                      color: log.isAlert ? AppColors.errorRed : AppColors.darkNavy,
                      fontSize: 14,
                      fontWeight: FontWeight.w600,
                    ),
                  ),
                  const SizedBox(height: 4),
                  Text(
                    log.detail,
                    style: const TextStyle(
                      color: AppColors.blueGrayDark,
                      fontSize: 12,
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

class MissionLog {
  final String time;
  final String type;
  final String title;
  final String detail;
  final IconData icon;
  final Color color;
  final bool isAlert;

  MissionLog({
    required this.time,
    required this.type,
    required this.title,
    required this.detail,
    required this.icon,
    required this.color,
    this.isAlert = false,
  });
}
