import 'package:flutter/material.dart';
import '../theme/app_theme.dart';
import '../services/car_controller.dart';
import '../services/data_models.dart';

class MissionLogPage extends StatefulWidget {
  const MissionLogPage({super.key});

  @override
  State<MissionLogPage> createState() => _MissionLogPageState();
}

class _MissionLogPageState extends State<MissionLogPage> {
  final CarController _ctrl = CarController.instance;

  String _selectedFilter = '全部';

  final List<String> _filters = ['全部', '导航', '检测', '传感器', '系统'];

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

  List<TaskLog> get _allLogs => _ctrl.taskLogs.reversed.toList();

  List<TaskLog> get _filteredLogs {
    if (_selectedFilter == '全部') return _allLogs;
    return _allLogs.where((log) => log.category == _selectedFilter).toList();
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
            Expanded(child: _buildLogList()),
          ],
        ),
      ),
    );
  }

  Widget _buildStatsBar() {
    final logs = _allLogs;
    int totalLogs = logs.length;
    int alertLogs = logs.where((l) => l.isAlert).length;
    final taskStatus = _ctrl.latestTaskStatus;

    return Container(
      margin: const EdgeInsets.all(16),
      padding: const EdgeInsets.all(16),
      decoration: BoxDecoration(
        color: AppColors.surface,
        borderRadius: BorderRadius.circular(16),
        border: Border.all(color: AppColors.blueGray.withValues(alpha: 0.2)),
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
          _buildStatItem('任务状态', taskStatus.statusZh, taskStatus.statusColor),
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
          style: const TextStyle(color: AppColors.blueGrayDark, fontSize: 11),
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
        return _buildLogItem(logs[index], index == logs.length - 1);
      },
    );
  }

  Widget _buildLogItem(TaskLog log, bool isLast) {
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
              if (!isLast)
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
                          log.category,
                          style: TextStyle(
                            color: log.color,
                            fontSize: 10,
                            fontWeight: FontWeight.w600,
                          ),
                        ),
                      ),
                      const Spacer(),
                      Text(
                        log.timeShort,
                        style: const TextStyle(
                          color: AppColors.blueGrayDark,
                          fontSize: 11,
                        ),
                      ),
                    ],
                  ),
                  const SizedBox(height: 6),
                  Text(
                    log.titleZh,
                    style: TextStyle(
                      color: log.isAlert
                          ? AppColors.errorRed
                          : AppColors.darkNavy,
                      fontSize: 14,
                      fontWeight: FontWeight.w600,
                    ),
                  ),
                  if (log.summary.isNotEmpty) ...[
                    const SizedBox(height: 4),
                    Text(
                      log.summary,
                      style: const TextStyle(
                        color: AppColors.blueGrayDark,
                        fontSize: 12,
                      ),
                      maxLines: 3,
                      overflow: TextOverflow.ellipsis,
                    ),
                  ],
                ],
              ),
            ),
          ),
        ],
      ),
    );
  }
}
