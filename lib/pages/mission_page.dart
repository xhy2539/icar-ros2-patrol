import 'dart:async';
import 'dart:convert';
import 'package:flutter/foundation.dart';
import 'package:flutter/material.dart';
import 'package:speech_to_text/speech_to_text.dart' as stt;
import 'package:speech_to_text/speech_recognition_result.dart';
import '../theme/app_theme.dart';
import '../services/car_controller.dart';
import '../services/data_models.dart';

class MissionPage extends StatefulWidget {
  const MissionPage({super.key});

  @override
  State<MissionPage> createState() => _MissionPageState();
}

class _MissionPageState extends State<MissionPage> {
  final CarController _ctrl = CarController.instance;
  final TextEditingController _inputCtrl = TextEditingController();
  final TextEditingController _taskIdCtrl = TextEditingController();
  StreamSubscription<Map<String, dynamic>>? _parseSub;
  StreamSubscription<Map<String, dynamic>>? _reportSub;
  StreamSubscription<Map<String, dynamic>>? _llmCommandSub;

  /// 语音识别
  final stt.SpeechToText _speech = stt.SpeechToText();
  bool _speechAvailable = false;
  bool _isListening = false;
  String _currentWords = '';

  /// Web 不支持语音
  bool get _voiceSupported => !kIsWeb;

  /// 历史交互记录
  final List<_ChatEntry> _history = [];

  /// 是否显示日志时间线视图（false = 任务模式，true = 日志模式）
  bool _showLogView = false;

  /// 选中的巡检点（用于一键巡检快捷操作）
  final Set<String> _selectedCheckpoints = {};

  @override
  void initState() {
    super.initState();
    _ctrl.addListener(_onCtrlChanged);
    _parseSub = _ctrl.parseTaskStream.listen(_onParseResult);
    _reportSub = _ctrl.reportStream.listen(_onReportResult);
    _llmCommandSub = _ctrl.llmCommandStream.listen(_onLlmCommandResult);
    _initSpeech();
  }

  Future<void> _initSpeech() async {
    if (!_voiceSupported) return;
    _speechAvailable = await _speech.initialize(
      onError: (e) {
        if (mounted) setState(() => _isListening = false);
      },
      onStatus: (status) {
        if (mounted) {
          setState(() {
            _isListening = status == 'listening';
          });
        }
      },
    );
    if (mounted) setState(() {});
  }

  void _startListening() async {
    if (!_speechAvailable || !_voiceSupported) return;
    setState(() => _currentWords = '');
    await _speech.listen(
      onResult: _onSpeechResult,
      listenOptions: stt.SpeechListenOptions(
        localeId: 'zh_CN',
        listenMode: stt.ListenMode.confirmation,
        cancelOnError: true,
        partialResults: true,
      ),
    );
  }

  void _stopListening() async {
    await _speech.stop();
    // 识别完成后把文字填入输入框
    if (_currentWords.isNotEmpty) {
      _inputCtrl.text = _currentWords;
    }
  }

  void _onSpeechResult(SpeechRecognitionResult result) {
    setState(() {
      _currentWords = result.recognizedWords;
      // 实时显示到输入框
      if (_currentWords.isNotEmpty) {
        _inputCtrl.text = _currentWords;
      }
    });
    // 如果是最终结果，自动发送
    if (result.finalResult && _currentWords.isNotEmpty) {
      _sendParseTask();
    }
  }

  @override
  void dispose() {
    _ctrl.removeListener(_onCtrlChanged);
    _parseSub?.cancel();
    _reportSub?.cancel();
    _llmCommandSub?.cancel();
    _inputCtrl.dispose();
    _taskIdCtrl.dispose();
    super.dispose();
  }

  void _onCtrlChanged() {
    if (mounted) setState(() {});
  }

  void _onParseResult(Map<String, dynamic> result) {
    final success = result['success'] == true;
    final taskJson = success ? result['task_json'] : null;
    Map<String, dynamic>? parsed;
    if (taskJson is String) {
      try {
        parsed = jsonDecode(taskJson) as Map<String, dynamic>;
      } catch (_) {}
    } else if (taskJson is Map) {
      parsed = Map<String, dynamic>.from(taskJson);
    }

    setState(() {
      if (_history.isNotEmpty && _history.last.type == _EntryType.pending) {
        _history.last.result = success
            ? _ParseSuccess(taskJson: parsed, raw: result)
            : _ParseError(msg: result['error_msg']?.toString() ?? '未知错误');
      }
    });
  }

  void _onReportResult(Map<String, dynamic> result) {
    setState(() {
      if (_history.isNotEmpty && _history.last.type == _EntryType.reportReq) {
        _history.last.result = result['success'] == true
            ? _ReportSuccess(text: result['report_text']?.toString() ?? '')
            : _ParseError(msg: result['error_msg']?.toString() ?? '未知错误');
      }
    });
  }

  void _onLlmCommandResult(Map<String, dynamic> result) {
    final requestId = result['request_id']?.toString() ?? '';
    final success = result['success'] == true;
    setState(() {
      _ChatEntry? entry;
      for (final candidate in _history.reversed) {
        if (candidate.type == _EntryType.pending &&
            (requestId.isEmpty || candidate.requestId == requestId)) {
          entry = candidate;
          break;
        }
      }
      if (entry == null) return;
      entry.result = success
          ? _ToolSuccess(raw: result)
          : _ParseError(
              msg:
                  result['reply']?.toString() ??
                  result['message']?.toString() ??
                  result['error_msg']?.toString() ??
                  '执行失败',
            );
    });
  }

  void _sendParseTask() {
    final text = _inputCtrl.text.trim();
    if (text.isEmpty) return;

    final requestId = _ctrl.sendLlmCommand(text);
    if (requestId == null) return;
    setState(() {
      _history.add(
        _ChatEntry(type: _EntryType.pending, input: text, requestId: requestId),
      );
    });
    _inputCtrl.clear();
    FocusScope.of(context).unfocus();
  }

  void _sendTaskToManager(_ParseSuccess parse) {
    if (parse.taskJson != null) {
      _ctrl.sendParsedTaskToManager(parse.taskJson!);
      setState(() {
        _history.add(
          _ChatEntry(type: _EntryType.dispatch, input: '任务已下发至 task_manager'),
        );
      });
    }
  }

  void _requestReport() {
    final id = _taskIdCtrl.text.trim();
    if (id.isEmpty) return;
    setState(() {
      _history.add(_ChatEntry(type: _EntryType.reportReq, input: '请求报告: $id'));
    });
    _ctrl.sendGenerateReport(id);
  }

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      body: SafeArea(
        child: Column(
          children: [
            _buildModeToggle(),
            Expanded(
              child: _showLogView ? _buildLogTimeline() : _buildTaskView(),
            ),
          ],
        ),
      ),
    );
  }

  /// 任务模式视图（原有聊天 UI）
  Widget _buildTaskView() {
    return Column(
      children: [
        Expanded(
          child: _history.isEmpty ? _buildEmptyState() : _buildHistory(),
        ),
        _buildRouteSelector(),
        _buildInputBar(),
      ],
    );
  }

  Widget _buildEmptyState() {
    return Center(
      child: Column(
        mainAxisAlignment: MainAxisAlignment.center,
        children: [
          Icon(
            Icons.auto_awesome,
            color: AppColors.bluePurple.withValues(alpha: 0.4),
            size: 48,
          ),
          const SizedBox(height: 12),
          const Text(
            'LLM 智能指挥',
            style: TextStyle(
              color: AppColors.darkNavy,
              fontSize: 16,
              fontWeight: FontWeight.w600,
            ),
          ),
          const SizedBox(height: 6),
          Text(
            '自然语言会调用安全工具执行；不会绕过任务调度和急停',
            style: TextStyle(
              color: AppColors.blueGray.withValues(alpha: 0.7),
              fontSize: 13,
            ),
          ),
          const SizedBox(height: 20),
          _buildQuickSuggestions(),
        ],
      ),
    );
  }

  Widget _buildQuickSuggestions() {
    final suggestions = ['巡检 A、B、C 三个点', '跟踪前面的人', '停止跟踪', '你到哪个点了？'];
    return Padding(
      padding: const EdgeInsets.symmetric(horizontal: 24),
      child: Wrap(
        spacing: 8,
        runSpacing: 8,
        alignment: WrapAlignment.center,
        children: suggestions.map((s) {
          return GestureDetector(
            onTap: () {
              _inputCtrl.text = s;
              _sendParseTask();
            },
            child: Container(
              padding: const EdgeInsets.symmetric(horizontal: 12, vertical: 8),
              decoration: BoxDecoration(
                color: AppColors.surface,
                borderRadius: BorderRadius.circular(20),
                border: Border.all(
                  color: AppColors.blueGray.withValues(alpha: 0.3),
                ),
              ),
              child: Text(
                s,
                style: const TextStyle(
                  color: AppColors.bluePurple,
                  fontSize: 12,
                ),
              ),
            ),
          );
        }).toList(),
      ),
    );
  }

  Widget _buildHistory() {
    return ListView.builder(
      reverse: true,
      padding: const EdgeInsets.symmetric(horizontal: 16, vertical: 8),
      itemCount: _history.length,
      itemBuilder: (ctx, i) {
        final entry = _history[_history.length - 1 - i];
        return _buildEntry(entry);
      },
    );
  }

  Widget _buildEntry(_ChatEntry entry) {
    return Padding(
      padding: const EdgeInsets.only(bottom: 12),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          // 用户输入（右侧气泡）
          Align(
            alignment: Alignment.centerRight,
            child: Container(
              constraints: BoxConstraints(
                maxWidth: MediaQuery.of(context).size.width * 0.75,
              ),
              padding: const EdgeInsets.symmetric(horizontal: 14, vertical: 10),
              decoration: BoxDecoration(
                color: AppColors.orange,
                borderRadius: BorderRadius.circular(
                  16,
                ).copyWith(topRight: const Radius.circular(4)),
              ),
              child: Text(
                entry.input,
                style: const TextStyle(color: Colors.white, fontSize: 14),
              ),
            ),
          ),
          const SizedBox(height: 6),
          // 系统响应（左侧气泡）
          _buildResultBubble(entry),
        ],
      ),
    );
  }

  Widget _buildResultBubble(_ChatEntry entry) {
    final result = entry.result;

    if (result == null) {
      // 等待中
      return Container(
        padding: const EdgeInsets.symmetric(horizontal: 14, vertical: 12),
        decoration: BoxDecoration(
          color: AppColors.surface,
          borderRadius: BorderRadius.circular(
            16,
          ).copyWith(topLeft: const Radius.circular(4)),
          border: Border.all(color: AppColors.blueGray.withValues(alpha: 0.2)),
        ),
        child: const Row(
          mainAxisSize: MainAxisSize.min,
          children: [
            SizedBox(
              width: 14,
              height: 14,
              child: CircularProgressIndicator(
                strokeWidth: 2,
                color: AppColors.bluePurple,
              ),
            ),
            SizedBox(width: 8),
            Text(
              '正在理解并执行...',
              style: TextStyle(color: AppColors.blueGray, fontSize: 13),
            ),
          ],
        ),
      );
    }

    if (result is _ParseError) {
      return Container(
        padding: const EdgeInsets.symmetric(horizontal: 14, vertical: 12),
        decoration: BoxDecoration(
          color: AppColors.errorRed.withValues(alpha: 0.08),
          borderRadius: BorderRadius.circular(
            16,
          ).copyWith(topLeft: const Radius.circular(4)),
          border: Border.all(color: AppColors.errorRed.withValues(alpha: 0.3)),
        ),
        child: Row(
          children: [
            const Icon(
              Icons.error_outline,
              color: AppColors.errorRed,
              size: 18,
            ),
            const SizedBox(width: 8),
            Expanded(
              child: Text(
                result.msg,
                style: const TextStyle(color: AppColors.errorRed, fontSize: 13),
              ),
            ),
          ],
        ),
      );
    }

    if (result is _ToolSuccess) {
      return _buildToolResultCard(result.raw);
    }

    if (result is _ParseSuccess) {
      return _buildParseResultCard(result);
    }

    if (result is _ReportSuccess) {
      return _buildReportCard(result.text);
    }

    if (entry.type == _EntryType.dispatch) {
      return Container(
        padding: const EdgeInsets.symmetric(horizontal: 14, vertical: 10),
        decoration: BoxDecoration(
          color: AppColors.successGreen.withValues(alpha: 0.08),
          borderRadius: BorderRadius.circular(
            16,
          ).copyWith(topLeft: const Radius.circular(4)),
          border: Border.all(
            color: AppColors.successGreen.withValues(alpha: 0.3),
          ),
        ),
        child: const Row(
          mainAxisSize: MainAxisSize.min,
          children: [
            Icon(Icons.check_circle, color: AppColors.successGreen, size: 18),
            SizedBox(width: 8),
            Text(
              '任务已下发',
              style: TextStyle(
                color: AppColors.successGreen,
                fontSize: 13,
                fontWeight: FontWeight.w500,
              ),
            ),
          ],
        ),
      );
    }

    return const SizedBox.shrink();
  }

  Widget _buildToolResultCard(Map<String, dynamic> result) {
    final toolName = result['tool_name']?.toString() ?? '';
    final provider = result['provider']?.toString() ?? 'rule';
    final reply =
        result['reply']?.toString() ?? result['message']?.toString() ?? '执行完成';
    final data = result['data'];

    return Container(
      width: double.infinity,
      padding: const EdgeInsets.all(14),
      decoration: BoxDecoration(
        color: AppColors.surface,
        borderRadius: BorderRadius.circular(
          16,
        ).copyWith(topLeft: const Radius.circular(4)),
        border: Border.all(
          color: AppColors.successGreen.withValues(alpha: 0.35),
        ),
      ),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Row(
            children: [
              const Icon(
                Icons.smart_toy_outlined,
                color: AppColors.successGreen,
                size: 18,
              ),
              const SizedBox(width: 6),
              Text(
                _toolNameZh(toolName),
                style: const TextStyle(
                  color: AppColors.successGreen,
                  fontSize: 13,
                  fontWeight: FontWeight.w600,
                ),
              ),
              const Spacer(),
              Text(
                provider == 'deepseek' ? 'LLM' : '本地安全规则',
                style: const TextStyle(color: AppColors.blueGray, fontSize: 10),
              ),
            ],
          ),
          const SizedBox(height: 10),
          Text(
            reply,
            style: const TextStyle(
              color: AppColors.darkNavy,
              fontSize: 14,
              height: 1.5,
            ),
          ),
          if (data is Map && data.isNotEmpty) ...[
            const SizedBox(height: 8),
            Divider(color: AppColors.blueGray.withValues(alpha: 0.15)),
            Text(
              const JsonEncoder.withIndent('  ').convert(data),
              maxLines: 6,
              overflow: TextOverflow.ellipsis,
              style: const TextStyle(
                color: AppColors.blueGray,
                fontFamily: 'monospace',
                fontSize: 11,
              ),
            ),
          ],
        ],
      ),
    );
  }

  String _toolNameZh(String toolName) {
    const names = {
      'start_patrol': '已启动巡检',
      'get_robot_status': '状态查询',
      'stop_robot': '紧急停止',
      'cancel_task': '取消任务',
      'reset_task': '复位任务',
      'query_vision': '视觉查询',
      'query_navigation': '导航查询',
      'check_safety': '安全查询',
      'play_audio': '播放音频',
      'download_audio': '下载音频',
      'start_tracking': '启动目标跟踪',
      'stop_tracking': '停止目标跟踪',
    };
    return names[toolName] ?? (toolName.isEmpty ? 'LLM 执行结果' : toolName);
  }

  Widget _buildParseResultCard(_ParseSuccess parse) {
    final task = parse.taskJson;
    final taskType = task?['task_type']?.toString() ?? 'unknown';
    final isPatrol = taskType == 'patrol';
    final isInfo = taskType == 'info';

    return Container(
      width: double.infinity,
      padding: const EdgeInsets.all(14),
      decoration: BoxDecoration(
        color: AppColors.surface,
        borderRadius: BorderRadius.circular(
          16,
        ).copyWith(topLeft: const Radius.circular(4)),
        border: Border.all(color: AppColors.bluePurple.withValues(alpha: 0.3)),
      ),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          // 任务类型标签
          Row(
            children: [
              _buildTypeChip(taskType),
              const Spacer(),
              Text(
                'provider: ${task?['params']?['provider'] ?? '-'}',
                style: const TextStyle(color: AppColors.blueGray, fontSize: 10),
              ),
            ],
          ),
          const SizedBox(height: 10),

          // 巡检任务
          if (isPatrol) ...[
            _buildInfoRow('巡检路线', _formatRoute(task?['route'])),
            if (task?['actions'] != null)
              _buildInfoRow('执行动作', _formatList(task?['actions'])),
            if (task?['safety_rule'] != null)
              _buildInfoRow('安全规则', task!['safety_rule'].toString()),
          ],

          // 信息查询
          if (isInfo) ...[
            if (task?['answer'] != null) ...[
              const SizedBox(height: 4),
              Text(
                task!['answer'].toString(),
                style: const TextStyle(
                  color: AppColors.darkNavy,
                  fontSize: 14,
                  height: 1.5,
                ),
              ),
            ],
            if (task?['query_type'] != null)
              _buildInfoRow('查询类型', task!['query_type'].toString()),
          ],

          // 原始 JSON 折叠
          const SizedBox(height: 8),
          Divider(color: AppColors.blueGray.withValues(alpha: 0.15)),
          const SizedBox(height: 4),
          GestureDetector(
            onTap: () => _showRawJson(parse.raw),
            child: const Row(
              children: [
                Icon(Icons.code, color: AppColors.blueGray, size: 14),
                SizedBox(width: 4),
                Text(
                  '查看原始 JSON',
                  style: TextStyle(color: AppColors.blueGray, fontSize: 11),
                ),
              ],
            ),
          ),

          // 下发按钮（仅巡检任务）
          if (isPatrol) ...[
            const SizedBox(height: 12),
            SizedBox(
              width: double.infinity,
              height: 40,
              child: ElevatedButton.icon(
                onPressed: () => _sendTaskToManager(parse),
                icon: const Icon(Icons.send, size: 18),
                label: const Text('下发任务到小车'),
                style: ElevatedButton.styleFrom(
                  backgroundColor: AppColors.bluePurple,
                ),
              ),
            ),
          ],
        ],
      ),
    );
  }

  Widget _buildReportCard(String reportText) {
    return Container(
      width: double.infinity,
      padding: const EdgeInsets.all(14),
      decoration: BoxDecoration(
        color: AppColors.surface,
        borderRadius: BorderRadius.circular(
          16,
        ).copyWith(topLeft: const Radius.circular(4)),
        border: Border.all(
          color: AppColors.successGreen.withValues(alpha: 0.3),
        ),
      ),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Row(
            children: [
              Icon(Icons.description, color: AppColors.successGreen, size: 18),
              const SizedBox(width: 6),
              const Text(
                '巡检报告',
                style: TextStyle(
                  color: AppColors.successGreen,
                  fontSize: 14,
                  fontWeight: FontWeight.w600,
                ),
              ),
            ],
          ),
          const SizedBox(height: 10),
          Text(
            reportText,
            style: const TextStyle(
              color: AppColors.darkNavy,
              fontSize: 13,
              height: 1.6,
            ),
          ),
        ],
      ),
    );
  }

  Widget _buildTypeChip(String type) {
    String label;
    Color color;
    IconData icon;
    switch (type) {
      case 'patrol':
        label = '巡检任务';
        color = AppColors.bluePurple;
        icon = Icons.route;
        break;
      case 'info':
        label = '信息查询';
        color = AppColors.orange;
        icon = Icons.help_outline;
        break;
      default:
        label = type;
        color = AppColors.blueGray;
        icon = Icons.label;
    }
    return Container(
      padding: const EdgeInsets.symmetric(horizontal: 10, vertical: 4),
      decoration: BoxDecoration(
        color: color.withValues(alpha: 0.12),
        borderRadius: BorderRadius.circular(12),
        border: Border.all(color: color.withValues(alpha: 0.3)),
      ),
      child: Row(
        mainAxisSize: MainAxisSize.min,
        children: [
          Icon(icon, color: color, size: 14),
          const SizedBox(width: 4),
          Text(
            label,
            style: TextStyle(
              color: color,
              fontSize: 11,
              fontWeight: FontWeight.w600,
            ),
          ),
        ],
      ),
    );
  }

  Widget _buildInfoRow(String label, String value) {
    return Padding(
      padding: const EdgeInsets.symmetric(vertical: 3),
      child: Row(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Text(
            '$label: ',
            style: const TextStyle(
              color: AppColors.blueGray,
              fontSize: 12,
              fontWeight: FontWeight.w500,
            ),
          ),
          Expanded(
            child: Text(
              value,
              style: const TextStyle(color: AppColors.darkNavy, fontSize: 12),
            ),
          ),
        ],
      ),
    );
  }

  String _formatRoute(dynamic route) {
    if (route is List) return route.join(' → ');
    return route?.toString() ?? '-';
  }

  String _formatList(dynamic list) {
    if (list is List) return list.join(', ');
    return list?.toString() ?? '-';
  }

  void _showRawJson(Map<String, dynamic> raw) {
    showDialog(
      context: context,
      builder: (ctx) => AlertDialog(
        backgroundColor: AppColors.surface,
        title: const Text(
          '原始 JSON',
          style: TextStyle(color: AppColors.darkNavy, fontSize: 16),
        ),
        content: SingleChildScrollView(
          child: SelectableText(
            const JsonEncoder.withIndent('  ').convert(raw),
            style: const TextStyle(
              fontFamily: 'monospace',
              fontSize: 12,
              color: AppColors.darkNavyLight,
            ),
          ),
        ),
        actions: [
          TextButton(
            onPressed: () => Navigator.of(ctx).pop(),
            child: const Text('关闭', style: TextStyle(color: AppColors.orange)),
          ),
        ],
      ),
    );
  }

  // ═══════════════════════════════════════════
  // 模式切换
  // ═══════════════════════════════════════════

  Widget _buildModeToggle() {
    return Container(
      margin: const EdgeInsets.symmetric(horizontal: 16, vertical: 8),
      padding: const EdgeInsets.all(3),
      decoration: BoxDecoration(
        color: AppColors.surfaceAlt,
        borderRadius: BorderRadius.circular(10),
      ),
      child: Row(
        children: [
          Expanded(
            child: GestureDetector(
              onTap: () => setState(() => _showLogView = false),
              child: AnimatedContainer(
                duration: const Duration(milliseconds: 200),
                padding: const EdgeInsets.symmetric(vertical: 8),
                decoration: BoxDecoration(
                  color: !_showLogView
                      ? AppColors.bluePurple
                      : Colors.transparent,
                  borderRadius: BorderRadius.circular(8),
                ),
                child: Center(
                  child: Text(
                    '任务',
                    style: TextStyle(
                      color: !_showLogView ? Colors.white : AppColors.blueGray,
                      fontSize: 13,
                      fontWeight: FontWeight.w600,
                    ),
                  ),
                ),
              ),
            ),
          ),
          Expanded(
            child: GestureDetector(
              onTap: () => setState(() => _showLogView = true),
              child: AnimatedContainer(
                duration: const Duration(milliseconds: 200),
                padding: const EdgeInsets.symmetric(vertical: 8),
                decoration: BoxDecoration(
                  color: _showLogView
                      ? AppColors.bluePurple
                      : Colors.transparent,
                  borderRadius: BorderRadius.circular(8),
                ),
                child: Center(
                  child: Text(
                    '日志',
                    style: TextStyle(
                      color: _showLogView ? Colors.white : AppColors.blueGray,
                      fontSize: 13,
                      fontWeight: FontWeight.w600,
                    ),
                  ),
                ),
              ),
            ),
          ),
        ],
      ),
    );
  }

  // ═══════════════════════════════════════════
  // 巡检点快捷选择
  // ═══════════════════════════════════════════

  Widget _buildRouteSelector() {
    return Container(
      margin: const EdgeInsets.symmetric(horizontal: 16, vertical: 4),
      padding: const EdgeInsets.symmetric(horizontal: 12, vertical: 8),
      decoration: BoxDecoration(
        color: AppColors.surface,
        borderRadius: BorderRadius.circular(12),
        border: Border.all(color: AppColors.blueGray.withValues(alpha: 0.2)),
      ),
      child: Row(
        children: [
          const Text(
            '巡检点: ',
            style: TextStyle(color: AppColors.blueGray, fontSize: 12),
          ),
          ...['A', 'B', 'C'].map(
            (cp) => Padding(
              padding: const EdgeInsets.only(right: 8),
              child: GestureDetector(
                onTap: () => setState(() {
                  if (_selectedCheckpoints.contains(cp)) {
                    _selectedCheckpoints.remove(cp);
                  } else {
                    _selectedCheckpoints.add(cp);
                  }
                }),
                child: Container(
                  padding: const EdgeInsets.symmetric(
                    horizontal: 10,
                    vertical: 4,
                  ),
                  decoration: BoxDecoration(
                    color: _selectedCheckpoints.contains(cp)
                        ? AppColors.bluePurple
                        : Colors.transparent,
                    borderRadius: BorderRadius.circular(6),
                    border: Border.all(
                      color: _selectedCheckpoints.contains(cp)
                          ? AppColors.bluePurple
                          : AppColors.blueGray.withValues(alpha: 0.3),
                    ),
                  ),
                  child: Text(
                    cp,
                    style: TextStyle(
                      color: _selectedCheckpoints.contains(cp)
                          ? Colors.white
                          : AppColors.blueGray,
                      fontSize: 12,
                      fontWeight: FontWeight.w600,
                    ),
                  ),
                ),
              ),
            ),
          ),
          const Spacer(),
          GestureDetector(
            onTap: _selectedCheckpoints.isEmpty
                ? null
                : () {
                    final route = _selectedCheckpoints.toList()..sort();
                    _ctrl.sendParsedTaskToManager({
                      'task_type': 'patrol',
                      'route': route,
                      'actions': ['navigate', 'detect', 'collect'],
                    });
                  },
            child: Container(
              padding: const EdgeInsets.symmetric(horizontal: 12, vertical: 6),
              decoration: BoxDecoration(
                color: _selectedCheckpoints.isEmpty
                    ? AppColors.blueGray.withValues(alpha: 0.3)
                    : AppColors.orange,
                borderRadius: BorderRadius.circular(8),
              ),
              child: const Text(
                '一键巡检',
                style: TextStyle(
                  color: Colors.white,
                  fontSize: 12,
                  fontWeight: FontWeight.w600,
                ),
              ),
            ),
          ),
        ],
      ),
    );
  }

  // ═══════════════════════════════════════════
  // 日志时间线视图
  // ═══════════════════════════════════════════

  Widget _buildLogTimeline() {
    final logs = _ctrl.taskLogs.reversed.toList();
    final taskStatus = _ctrl.latestTaskStatus;

    return Column(
      children: [
        // Stats bar
        Container(
          margin: const EdgeInsets.symmetric(horizontal: 16, vertical: 8),
          padding: const EdgeInsets.symmetric(horizontal: 16, vertical: 10),
          decoration: BoxDecoration(
            color: AppColors.surface,
            borderRadius: BorderRadius.circular(12),
          ),
          child: Row(
            mainAxisAlignment: MainAxisAlignment.spaceAround,
            children: [
              _buildStat('日志总数', '${logs.length}', AppColors.bluePurple),
              _buildStat('任务状态', taskStatus.statusZh, taskStatus.statusColor),
              _buildStat(
                '进度',
                '${taskStatus.currentStep}/${taskStatus.totalSteps}',
                AppColors.orange,
              ),
            ],
          ),
        ),
        // Timeline
        Expanded(
          child: logs.isEmpty
              ? const Center(
                  child: Text(
                    '暂无任务日志',
                    style: TextStyle(color: AppColors.blueGray),
                  ),
                )
              : ListView.builder(
                  padding: const EdgeInsets.symmetric(horizontal: 16),
                  itemCount: logs.length,
                  itemBuilder: (context, index) {
                    final log = logs[index];
                    return _buildLogEntry(log, index == 0);
                  },
                ),
        ),
      ],
    );
  }

  Widget _buildStat(String label, String value, Color color) {
    return Column(
      children: [
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
          style: const TextStyle(color: AppColors.blueGray, fontSize: 10),
        ),
      ],
    );
  }

  Widget _buildLogEntry(TaskLog log, bool isLatest) {
    return Padding(
      padding: const EdgeInsets.only(bottom: 12),
      child: Row(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          // Timeline dot + line
          Column(
            children: [
              Container(
                width: 28,
                height: 28,
                decoration: BoxDecoration(
                  color: log.color.withValues(alpha: 0.15),
                  shape: BoxShape.circle,
                ),
                child: Icon(log.icon, size: 14, color: log.color),
              ),
              if (!isLatest)
                Container(
                  width: 2,
                  height: 30,
                  color: AppColors.blueGray.withValues(alpha: 0.2),
                ),
            ],
          ),
          const SizedBox(width: 10),
          // Content
          Expanded(
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                Row(
                  children: [
                    Text(
                      log.titleZh,
                      style: TextStyle(
                        color: log.color,
                        fontSize: 13,
                        fontWeight: FontWeight.w600,
                      ),
                    ),
                    const Spacer(),
                    Text(
                      log.timeShort,
                      style: const TextStyle(
                        color: AppColors.blueGray,
                        fontSize: 10,
                      ),
                    ),
                  ],
                ),
                if (log.summary.isNotEmpty)
                  Padding(
                    padding: const EdgeInsets.only(top: 2),
                    child: Text(
                      log.summary,
                      style: const TextStyle(
                        color: AppColors.blueGray,
                        fontSize: 11,
                      ),
                      maxLines: 2,
                      overflow: TextOverflow.ellipsis,
                    ),
                  ),
              ],
            ),
          ),
        ],
      ),
    );
  }

  // ═══════════════════════════════════════════
  // 底部输入栏
  // ═══════════════════════════════════════════

  Widget _buildInputBar() {
    return Container(
      padding: const EdgeInsets.fromLTRB(12, 8, 12, 12),
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
        top: false,
        child: Column(
          mainAxisSize: MainAxisSize.min,
          children: [
            // 主输入行
            Row(
              children: [
                Expanded(
                  child: TextField(
                    controller: _inputCtrl,
                    textInputAction: TextInputAction.send,
                    onSubmitted: (_) => _sendParseTask(),
                    style: const TextStyle(
                      color: AppColors.darkNavy,
                      fontSize: 14,
                    ),
                    decoration: InputDecoration(
                      isDense: true,
                      contentPadding: const EdgeInsets.symmetric(
                        horizontal: 14,
                        vertical: 10,
                      ),
                      hintText: _isListening
                          ? '正在听...$_currentWords'
                          : '如“巡检ABC”“跟踪前面的人”“立即停下”',
                      hintStyle: TextStyle(
                        color: _isListening
                            ? AppColors.orange.withValues(alpha: 0.7)
                            : AppColors.blueGray.withValues(alpha: 0.6),
                        fontSize: 13,
                      ),
                    ),
                  ),
                ),
                const SizedBox(width: 6),
                // 语音按钮（仅 Android 可用）
                if (_voiceSupported) ...[
                  SizedBox(
                    height: 42,
                    width: 42,
                    child: GestureDetector(
                      onTap: _speechAvailable ? (_isListening ? _stopListening : _startListening) : null,
                      child: AnimatedContainer(
                        duration: const Duration(milliseconds: 200),
                        decoration: BoxDecoration(
                          color: _isListening
                              ? AppColors.errorRed.withValues(alpha: 0.15)
                              : AppColors.surfaceAlt,
                          borderRadius: BorderRadius.circular(12),
                          border: Border.all(
                            color: _isListening
                                ? AppColors.errorRed.withValues(alpha: 0.5)
                                : AppColors.blueGray.withValues(alpha: 0.2),
                          ),
                        ),
                        child: Icon(
                          _isListening ? Icons.stop : Icons.mic,
                          color: _isListening
                              ? AppColors.errorRed
                              : AppColors.bluePurple,
                          size: 22,
                        ),
                      ),
                    ),
                  ),
                  const SizedBox(width: 6),
                ],
                SizedBox(
                  height: 42,
                  width: 42,
                  child: ElevatedButton(
                    onPressed: _ctrl.canSendCommands ? _sendParseTask : null,
                    style: ElevatedButton.styleFrom(
                      padding: EdgeInsets.zero,
                      shape: RoundedRectangleBorder(
                        borderRadius: BorderRadius.circular(12),
                      ),
                    ),
                    child: const Icon(Icons.send, size: 20),
                  ),
                ),
              ],
            ),
            const SizedBox(height: 8),
            // 报告请求行
            Row(
              children: [
                const Icon(
                  Icons.description,
                  color: AppColors.blueGray,
                  size: 16,
                ),
                const SizedBox(width: 6),
                const Text(
                  '报告',
                  style: TextStyle(color: AppColors.blueGray, fontSize: 11),
                ),
                const SizedBox(width: 8),
                Expanded(
                  child: SizedBox(
                    height: 34,
                    child: TextField(
                      controller: _taskIdCtrl,
                      textInputAction: TextInputAction.go,
                      onSubmitted: (_) => _requestReport(),
                      style: const TextStyle(
                        color: AppColors.darkNavy,
                        fontSize: 12,
                      ),
                      decoration: InputDecoration(
                        isDense: true,
                        contentPadding: const EdgeInsets.symmetric(
                          horizontal: 10,
                          vertical: 8,
                        ),
                        hintText: 'task_id',
                        hintStyle: TextStyle(
                          color: AppColors.blueGray.withValues(alpha: 0.5),
                          fontSize: 12,
                        ),
                      ),
                    ),
                  ),
                ),
                const SizedBox(width: 8),
                SizedBox(
                  height: 34,
                  child: ElevatedButton(
                    onPressed: _ctrl.canSendCommands ? _requestReport : null,
                    style: ElevatedButton.styleFrom(
                      padding: const EdgeInsets.symmetric(horizontal: 12),
                      textStyle: const TextStyle(fontSize: 12),
                      backgroundColor: AppColors.bluePurple,
                    ),
                    child: const Text('生成'),
                  ),
                ),
              ],
            ),
          ],
        ),
      ),
    );
  }
}

// ═══════════════════════════════════════════
// 数据类
// ═══════════════════════════════════════════

enum _EntryType { pending, dispatch, reportReq }

class _ChatEntry {
  final _EntryType type;
  final String input;
  final String requestId;
  Object? result; // _ToolSuccess / _ParseSuccess / _ParseError / _ReportSuccess

  _ChatEntry({required this.type, required this.input, this.requestId = ''});
}

class _ToolSuccess {
  final Map<String, dynamic> raw;
  _ToolSuccess({required this.raw});
}

class _ParseSuccess {
  final Map<String, dynamic>? taskJson;
  final Map<String, dynamic> raw;
  _ParseSuccess({this.taskJson, required this.raw});
}

class _ParseError {
  final String msg;
  _ParseError({required this.msg});
}

class _ReportSuccess {
  final String text;
  _ReportSuccess({required this.text});
}
