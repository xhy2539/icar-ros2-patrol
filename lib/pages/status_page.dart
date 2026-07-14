import 'package:flutter/material.dart';
import '../theme/app_theme.dart';
import '../services/car_controller.dart';
import '../services/data_models.dart';

class StatusPage extends StatefulWidget {
  const StatusPage({super.key});

  @override
  State<StatusPage> createState() => _StatusPageState();
}

class _StatusPageState extends State<StatusPage> {
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

  // ═══════════════════════════════════════════
  // Helpers
  // ═══════════════════════════════════════════

  /// Whether real car data is available (connected + non-default values)
  bool get _hasNavData {
    final nav = _ctrl.latestNavStatus;
    return nav.status != 'IDLE' ||
        nav.progress > 0.0 ||
        nav.distanceRemain > 0.0;
  }

  bool get _hasObstacleData {
    final obs = _ctrl.latestObstacleStatus;
    return obs.isObstacle || obs.minDistance < 99.0;
  }

  bool get _hasTaskData {
    final task = _ctrl.latestTaskStatus;
    return task.taskId.isNotEmpty ||
        task.status != 'PENDING' ||
        task.totalSteps > 0;
  }

  Color _riskColor(String riskLevel) {
    switch (riskLevel) {
      case 'danger':
        return AppColors.errorRed;
      case 'warning':
        return AppColors.warningOrange;
      default:
        return AppColors.successGreen;
    }
  }

  IconData _directionIcon(String direction) {
    switch (direction) {
      case 'front':
        return Icons.arrow_upward;
      case 'back':
        return Icons.arrow_downward;
      case 'left':
        return Icons.arrow_back;
      case 'right':
        return Icons.arrow_forward;
      default:
        return Icons.near_me;
    }
  }

  // ═══════════════════════════════════════════
  // Build
  // ═══════════════════════════════════════════

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
              if (_ctrl.latestSafetyAlarm?.active == true) ...[
                _buildSafetyAlarmCard(_ctrl.latestSafetyAlarm!),
                const SizedBox(height: 16),
              ],
              // 详细信息
              _buildDetailCards(),
              const SizedBox(height: 16),
              // 导航信息
              _buildNavigationInfo(),
              const SizedBox(height: 16),
              // 系统信息
              _buildSystemInfo(),
            ],
          ),
        ),
      ),
    );
  }

  // ═══════════════════════════════════════════
  // 状态概览
  // ═══════════════════════════════════════════

  Widget _buildStatusOverview() {
    final connected = _ctrl.isConnected;
    final reachable = connected && _ctrl.robotOnline;
    final nav = _ctrl.latestNavStatus;
    final task = _ctrl.latestTaskStatus;

    return Padding(
      padding: const EdgeInsets.symmetric(horizontal: 16),
      child: Row(
        children: [
          Expanded(
            child: _buildStatusItem(
              icon: reachable ? Icons.link : Icons.link_off,
              label: '连接',
              value: reachable
                  ? (_ctrl.isCloudMode ? '远程在线' : '已连接')
                  : (_ctrl.isCloudMode && connected ? '小车离线' : '未连接'),
              color: reachable
                  ? AppColors.successGreen
                  : (_ctrl.isCloudMode && connected
                        ? AppColors.warningOrange
                        : AppColors.errorRed),
            ),
          ),
          const SizedBox(width: 8),
          Expanded(
            child: _buildStatusItem(
              icon: Icons.speed,
              label: '速度',
              value: '${(_ctrl.speed * 100).round()}%',
              color: AppColors.bluePurple,
            ),
          ),
          const SizedBox(width: 8),
          Expanded(
            child: _buildStatusItem(
              icon: Icons.navigation,
              label: '导航',
              value: _hasNavData ? nav.statusZh : '--',
              color: _hasNavData ? nav.statusColor : AppColors.blueGray,
            ),
          ),
          const SizedBox(width: 8),
          Expanded(
            child: _buildStatusItem(
              icon: Icons.task_alt,
              label: '任务',
              value: _hasTaskData ? task.statusZh : '--',
              color: _hasTaskData ? task.statusColor : AppColors.blueGray,
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
        border: Border.all(color: AppColors.blueGray.withValues(alpha: 0.2)),
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
            style: const TextStyle(color: AppColors.blueGrayDark, fontSize: 11),
          ),
        ],
      ),
    );
  }

  // ═══════════════════════════════════════════
  // 详细卡片: 避障状态 + 任务进度
  // ═══════════════════════════════════════════

  Widget _buildDetailCards() {
    return Column(children: [_buildObstacleCard(), _buildTaskProgressCard()]);
  }

  Widget _buildSafetyAlarmCard(SafetyAlarm alarm) {
    final critical = alarm.isCritical;
    final color = critical ? AppColors.errorRed : AppColors.warningOrange;
    final evidence = alarm.capturePending
        ? '证据截图保存中'
        : alarm.imagePath.isNotEmpty
        ? '证据已保存'
        : alarm.captureStatus.isNotEmpty
        ? '截图${alarm.captureStatus}'
        : '暂无截图';
    return AppCard(
      title: '需工作人员处理的安全告警',
      icon: critical ? Icons.emergency : Icons.water_damage,
      child: Column(
        children: [
          _buildDetailRow('事件', alarm.typeZh, Icons.warning_amber, color),
          const SizedBox(height: 10),
          _buildDetailRow(
            '处置',
            alarm.action == 'replan_current_goal' ? '已请求绕行' : '请人工确认',
            Icons.route,
            color,
          ),
          const SizedBox(height: 10),
          _buildDetailRow('证据', evidence, Icons.photo_camera, color),
          if (alarm.checkpoint.isNotEmpty) ...[
            const SizedBox(height: 10),
            _buildDetailRow('位置', alarm.checkpoint, Icons.location_on, color),
          ],
          if (alarm.message.isNotEmpty) ...[
            const SizedBox(height: 12),
            Align(
              alignment: Alignment.centerLeft,
              child: Text(
                alarm.message,
                style: const TextStyle(
                  color: AppColors.blueGrayDark,
                  fontSize: 13,
                ),
              ),
            ),
          ],
        ],
      ),
    );
  }

  /// 避障状态卡片
  Widget _buildObstacleCard() {
    final obs = _ctrl.latestObstacleStatus;

    return AppCard(
      title: '避障状态',
      icon: Icons.radar,
      child: _hasObstacleData
          ? Column(
              children: [
                _buildDetailRow(
                  '障碍物',
                  obs.isObstacle ? '检测到' : '无',
                  obs.isObstacle
                      ? Icons.warning_amber
                      : Icons.check_circle_outline,
                  obs.isObstacle
                      ? AppColors.warningOrange
                      : AppColors.successGreen,
                ),
                const Divider(height: 20),
                _buildDetailRow(
                  '最近距离',
                  '${obs.minDistance.toStringAsFixed(1)} m',
                  Icons.straighten,
                  _riskColor(obs.riskLevel),
                ),
                const SizedBox(height: 8),
                _buildDetailRow(
                  '方向',
                  obs.directionZh,
                  _directionIcon(obs.direction),
                  AppColors.darkNavy,
                ),
                const SizedBox(height: 8),
                _buildDetailRow(
                  '风险等级',
                  obs.riskLevel == 'danger'
                      ? '危险'
                      : obs.riskLevel == 'warning'
                      ? '警告'
                      : '安全',
                  obs.isDanger
                      ? Icons.error_outline
                      : obs.isWarning
                      ? Icons.warning_amber
                      : Icons.shield,
                  _riskColor(obs.riskLevel),
                ),
                const SizedBox(height: 8),
                _buildDetailRow(
                  '建议动作',
                  _obstacleActionZh(obs.action),
                  Icons.psychology,
                  AppColors.bluePurple,
                ),
              ],
            )
          : _buildPlaceholder('等待车端避障数据...'),
    );
  }

  /// 任务进度卡片
  Widget _buildTaskProgressCard() {
    final task = _ctrl.latestTaskStatus;

    return AppCard(
      title: '任务进度',
      icon: Icons.checklist,
      child: _hasTaskData
          ? Column(
              children: [
                Row(
                  children: [
                    StatusBadge(text: task.statusZh, color: task.statusColor),
                    const Spacer(),
                    if (task.taskId.isNotEmpty)
                      Text(
                        'ID: ${task.taskId}',
                        style: const TextStyle(
                          color: AppColors.blueGrayDark,
                          fontSize: 12,
                        ),
                      ),
                  ],
                ),
                const SizedBox(height: 12),
                _buildDetailRow(
                  '当前步骤',
                  '${task.currentStep} / ${task.totalSteps}',
                  Icons.format_list_numbered,
                  AppColors.darkNavy,
                ),
                const SizedBox(height: 12),
                // 进度条
                ClipRRect(
                  borderRadius: BorderRadius.circular(6),
                  child: LinearProgressIndicator(
                    value: task.totalSteps > 0
                        ? task.currentStep / task.totalSteps
                        : 0.0,
                    backgroundColor: AppColors.blueGray.withValues(alpha: 0.2),
                    valueColor: AlwaysStoppedAnimation<Color>(task.statusColor),
                    minHeight: 8,
                  ),
                ),
                if (task.message.isNotEmpty) ...[
                  const SizedBox(height: 10),
                  Text(
                    task.message,
                    style: const TextStyle(
                      color: AppColors.blueGrayDark,
                      fontSize: 12,
                    ),
                  ),
                ],
              ],
            )
          : _buildPlaceholder('等待车端任务数据...'),
    );
  }

  // ═══════════════════════════════════════════
  // 导航信息
  // ═══════════════════════════════════════════

  Widget _buildNavigationInfo() {
    final nav = _ctrl.latestNavStatus;

    return AppCard(
      title: '导航信息',
      icon: Icons.navigation,
      child: _hasNavData
          ? Column(
              children: [
                Row(
                  children: [
                    StatusBadge(
                      text: nav.statusZh,
                      color: nav.statusColor,
                      pulse: nav.isNavigating,
                    ),
                  ],
                ),
                const SizedBox(height: 12),
                _buildDetailRow(
                  '导航进度',
                  '${(nav.progress * 100).round()}%',
                  Icons.trending_up,
                  nav.statusColor,
                ),
                const SizedBox(height: 10),
                // 导航进度条
                ClipRRect(
                  borderRadius: BorderRadius.circular(6),
                  child: LinearProgressIndicator(
                    value: nav.progress,
                    backgroundColor: AppColors.blueGray.withValues(alpha: 0.2),
                    valueColor: AlwaysStoppedAnimation<Color>(nav.statusColor),
                    minHeight: 8,
                  ),
                ),
                const SizedBox(height: 12),
                _buildDetailRow(
                  '剩余距离',
                  '${nav.distanceRemain.toStringAsFixed(1)} m',
                  Icons.near_me,
                  AppColors.darkNavy,
                ),
                if (nav.message.isNotEmpty) ...[
                  const SizedBox(height: 10),
                  Container(
                    width: double.infinity,
                    padding: const EdgeInsets.all(10),
                    decoration: BoxDecoration(
                      color: nav.isFailed
                          ? AppColors.errorRed.withValues(alpha: 0.08)
                          : AppColors.surfaceAlt,
                      borderRadius: BorderRadius.circular(8),
                    ),
                    child: Text(
                      nav.message,
                      style: TextStyle(
                        color: nav.isFailed
                            ? AppColors.errorRed
                            : AppColors.blueGrayDark,
                        fontSize: 12,
                      ),
                    ),
                  ),
                ],
              ],
            )
          : _buildPlaceholder('等待车端导航数据...'),
    );
  }

  // ═══════════════════════════════════════════
  // 系统信息（硬编码，不来自 CarController）
  // ═══════════════════════════════════════════

  Widget _buildSystemInfo() {
    return AppCard(
      title: '系统信息',
      icon: Icons.memory,
      child: Column(
        children: [
          _buildDetailRow(
            '主控',
            'Jetson Orin Nano',
            Icons.developer_board,
            AppColors.darkNavy,
          ),
          const Divider(height: 20),
          _buildDetailRow(
            '系统',
            'Ubuntu 20.04',
            Icons.laptop,
            AppColors.darkNavy,
          ),
          const SizedBox(height: 8),
          _buildDetailRow('ROS2', 'Foxy', Icons.hub, AppColors.darkNavy),
          const SizedBox(height: 8),
          _buildDetailRow(
            '驱动模式',
            '麦轮全向',
            Icons.all_inclusive,
            AppColors.bluePurple,
          ),
        ],
      ),
    );
  }

  // ═══════════════════════════════════════════
  // 通用组件
  // ═══════════════════════════════════════════

  Widget _buildDetailRow(
    String label,
    String value,
    IconData icon,
    Color iconColor,
  ) {
    return Row(
      children: [
        Icon(icon, color: iconColor, size: 16),
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

  Widget _buildPlaceholder(String text) {
    return Padding(
      padding: const EdgeInsets.symmetric(vertical: 20),
      child: Center(
        child: Column(
          children: [
            Icon(
              Icons.hourglass_empty,
              color: AppColors.blueGray.withValues(alpha: 0.5),
              size: 28,
            ),
            const SizedBox(height: 8),
            Text(
              text,
              style: const TextStyle(
                color: AppColors.blueGrayDark,
                fontSize: 13,
              ),
            ),
          ],
        ),
      ),
    );
  }

  String _obstacleActionZh(String action) {
    switch (action) {
      case 'slow_down':
        return '减速';
      case 'stop':
        return '停止';
      case 'turn':
        return '转向';
      default:
        return '无';
    }
  }
}
