import 'dart:async';
import 'dart:convert';
import 'package:flutter/material.dart';
import 'package:flutter/services.dart';
import '../theme/app_theme.dart';
import '../services/car_controller.dart';
import '../services/vision_models.dart';
import '../widgets/mjpeg_stream_view.dart';

class VisionPage extends StatefulWidget {
  const VisionPage({super.key});

  @override
  State<VisionPage> createState() => _VisionPageState();
}

class _VisionPageState extends State<VisionPage> {
  final CarController _ctrl = CarController.instance;
  StreamSubscription<DetectionArray>? _detSub;
  StreamSubscription<String>? _imgSub;

  /// 当前检测列表（从流更新）
  List<Detection> _detections = [];

  /// 检测图像的原始分辨率（用于坐标缩放）
  int _imgWidth = 640;
  int _imgHeight = 480;

  /// 视频源：false = 原始画面, true = 标注画面
  bool _showAnnotated = false;

  /// WebSocket 帧图像（base64 JPEG），如果有则优先显示
  Uint8List? _wsFrameBytes;

  /// 视频流日志去重标记
  bool _videoLoadLogged = false;
  bool _videoFirstFrameLogged = false;
  bool _videoErrorLogged = false;
  int _wsFrameCount = 0;
  late bool _lastCloudMode;

  /// 自动截图状态
  bool _autoCapture = false;
  double _captureInterval = 3.0;
  final TextEditingController _intervalCtrl = TextEditingController(
    text: '3.0',
  );

  @override
  void initState() {
    super.initState();
    _lastCloudMode = _ctrl.isCloudMode;
    _ctrl.addListener(_onCtrlChanged);
    _detSub = _ctrl.detectionStream.listen(_onDetections);
    _imgSub = _ctrl.imageFrameStream.listen(_onImageFrame);
  }

  @override
  void dispose() {
    _ctrl.removeListener(_onCtrlChanged);
    _detSub?.cancel();
    _imgSub?.cancel();
    _intervalCtrl.dispose();
    super.dispose();
  }

  void _onCtrlChanged() {
    if (mounted) {
      if (_lastCloudMode != _ctrl.isCloudMode) {
        _lastCloudMode = _ctrl.isCloudMode;
        _wsFrameBytes = null;
      }
      if (!_ctrl.hasLocalMedia) {
        _videoLoadLogged = false;
        _videoFirstFrameLogged = false;
        _videoErrorLogged = false;
        _wsFrameCount = 0;
      }
      setState(() {});
    }
  }

  void _onDetections(DetectionArray arr) {
    setState(() {
      _detections = arr.detections;
      _imgWidth = arr.imageWidth;
      _imgHeight = arr.imageHeight;
    });
  }

  void _onImageFrame(String base64Str) {
    try {
      final bytes = base64Decode(base64Str);
      if (mounted) {
        setState(() {
          _wsFrameBytes = Uint8List.fromList(bytes);
        });
        _wsFrameCount++;
        if (_wsFrameCount == 1) {
          _ctrl.addMessage(
            _ctrl.isCloudMode
                ? '[远程截图] 已显示 (${bytes.length} bytes)'
                : '[视频] 收到 WS 帧 (${bytes.length} bytes)',
          );
        } else if (_wsFrameCount % 100 == 0) {
          _ctrl.addMessage('[视频] 已收到 $_wsFrameCount 帧');
        }
      }
    } catch (_) {
      // base64 解码失败，忽略
    }
  }

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      body: SafeArea(
        child: SingleChildScrollView(
          padding: const EdgeInsets.symmetric(vertical: 12),
          child: Column(
            children: [
              _buildCameraFeed(),
              const SizedBox(height: 8),
              _buildInferenceStatus(),
              const SizedBox(height: 8),
              _buildFeedToggle(),
              const SizedBox(height: 8),
              _buildTrackingBar(),
              const SizedBox(height: 12),
              _buildCaptureControls(),
              const SizedBox(height: 12),
              _buildDetectionPanel(),
              const SizedBox(height: 12),
              _buildCaptureStatus(),
              const SizedBox(height: 12),
              _buildLogPanel(),
            ],
          ),
        ),
      ),
    );
  }

  // ═══════════════════════════════════════════
  // 摄像头画面 + 检测框叠加
  // ═══════════════════════════════════════════

  Widget _buildCameraFeed() {
    final isConnected = _ctrl.hasLocalMedia;

    return Container(
      margin: const EdgeInsets.symmetric(horizontal: 16),
      decoration: BoxDecoration(
        color: AppColors.surfaceAlt,
        borderRadius: BorderRadius.circular(16),
        border: Border.all(color: AppColors.blueGray.withValues(alpha: 0.3)),
        boxShadow: [
          BoxShadow(
            color: Colors.black.withValues(alpha: 0.04),
            blurRadius: 8,
            offset: const Offset(0, 2),
          ),
        ],
      ),
      child: ClipRRect(
        borderRadius: BorderRadius.circular(16),
        child: AspectRatio(
          aspectRatio: _imgWidth / _imgHeight,
          child: Stack(
            fit: StackFit.expand,
            children: [
              // 底层：视频流
              _buildVideoWidget(isConnected),
              // 中层：检测框叠加
              if (_detections.isNotEmpty && !_showAnnotated)
                DetectionOverlay(
                  detections: _detections,
                  imageWidth: _imgWidth.toDouble(),
                  imageHeight: _imgHeight.toDouble(),
                ),
              // 左上角 LIVE 标识
              if (isConnected)
                Positioned(
                  top: 8,
                  left: 8,
                  child: Container(
                    padding: const EdgeInsets.symmetric(
                      horizontal: 8,
                      vertical: 3,
                    ),
                    decoration: BoxDecoration(
                      color: AppColors.orange,
                      borderRadius: BorderRadius.circular(4),
                    ),
                    child: const Row(
                      mainAxisSize: MainAxisSize.min,
                      children: [
                        Icon(Icons.circle, color: Colors.white, size: 7),
                        SizedBox(width: 4),
                        Text(
                          'LIVE',
                          style: TextStyle(
                            color: Colors.white,
                            fontSize: 10,
                            fontWeight: FontWeight.bold,
                          ),
                        ),
                      ],
                    ),
                  ),
                ),
              // 右上角 检测数量
              if (_detections.isNotEmpty)
                Positioned(
                  top: 8,
                  right: 8,
                  child: Container(
                    padding: const EdgeInsets.symmetric(
                      horizontal: 8,
                      vertical: 3,
                    ),
                    decoration: BoxDecoration(
                      color: AppColors.bluePurple,
                      borderRadius: BorderRadius.circular(4),
                    ),
                    child: Text(
                      '${_detections.length} 目标',
                      style: const TextStyle(
                        color: Colors.white,
                        fontSize: 10,
                        fontWeight: FontWeight.bold,
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

  /// 构建视频显示组件
  ///
  /// 优先级：WebSocket 帧 > MJPEG HTTP 流 > 占位符
  Widget _buildVideoWidget(bool isConnected) {
    // 如果有 WebSocket 帧数据
    if (_wsFrameBytes != null && _wsFrameBytes!.isNotEmpty) {
      return Image.memory(
        _wsFrameBytes!,
        fit: BoxFit.cover,
        gaplessPlayback: true,
        errorBuilder: (_, _, _) => _buildPlaceholder(isConnected),
      );
    }

    // MJPEG HTTP 流
    if (isConnected) {
      final url = _showAnnotated ? _ctrl.annotatedVideoUrl : _ctrl.videoUrl;
      return MjpegStreamView(
        key: ValueKey(url),
        url: url,
        fit: BoxFit.cover,
        errorBuilder: (error) {
          if (!_videoErrorLogged) {
            _videoErrorLogged = true;
            _ctrl.addMessage('[视频] MJPEG 流加载失败: $error');
          }
          return Center(
            child: Column(
              mainAxisAlignment: MainAxisAlignment.center,
              children: [
                const Icon(Icons.wifi_off, color: AppColors.blueGray, size: 36),
                const SizedBox(height: 6),
                Text(
                  '视频流加载失败',
                  style: TextStyle(color: AppColors.blueGrayDark, fontSize: 12),
                ),
                const SizedBox(height: 2),
                Text(
                  url,
                  style: TextStyle(
                    color: AppColors.blueGray.withValues(alpha: 0.5),
                    fontSize: 9,
                  ),
                ),
              ],
            ),
          );
        },
        onFirstFrame: () {
          if (!_videoFirstFrameLogged) {
            _videoFirstFrameLogged = true;
            _ctrl.addMessage('[视频] MJPEG 流已接通');
          }
        },
        placeholder: Builder(
          builder: (context) {
            if (!_videoLoadLogged) {
              _videoLoadLogged = true;
              _ctrl.addMessage('[视频] 正在请求 MJPEG 流: $url');
            }
            return Center(
              child: Column(
                mainAxisAlignment: MainAxisAlignment.center,
                children: [
                  const CircularProgressIndicator(
                    color: AppColors.orange,
                    strokeWidth: 2,
                  ),
                  const SizedBox(height: 6),
                  Text(
                    '正在加载视频流...',
                    style: TextStyle(
                      color: AppColors.blueGrayDark,
                      fontSize: 11,
                    ),
                  ),
                ],
              ),
            );
          },
        ),
      );
    }

    // 未连接或云端尚未请求截图
    return _buildPlaceholder(isConnected);
  }

  Widget _buildPlaceholder(bool isConnected) {
    return Center(
      child: Column(
        mainAxisAlignment: MainAxisAlignment.center,
        children: [
          Icon(
            Icons.videocam,
            color: AppColors.blueGray.withValues(alpha: 0.5),
            size: 40,
          ),
          const SizedBox(height: 6),
          Text(
            _ctrl.isCloudMode && _ctrl.canSendCommands
                ? '点击“请求远程截图”获取当前画面'
                : isConnected
                ? '等待视频流...'
                : '连接小车后显示摄像头画面',
            style: TextStyle(color: AppColors.blueGrayDark, fontSize: 12),
          ),
        ],
      ),
    );
  }

  // ═══════════════════════════════════════════
  // 视频源切换
  // ═══════════════════════════════════════════

  Widget _buildFeedToggle() {
    return Padding(
      padding: const EdgeInsets.symmetric(horizontal: 16),
      child: Row(
        mainAxisAlignment: MainAxisAlignment.center,
        children: [
          _buildToggleButton(
            label: '原始画面',
            icon: Icons.videocam,
            selected: !_showAnnotated,
            onTap: () => setState(() => _showAnnotated = false),
          ),
          const SizedBox(width: 8),
          _buildToggleButton(
            label: '标注画面',
            icon: Icons.crop_free,
            selected: _showAnnotated,
            onTap: () => setState(() => _showAnnotated = true),
          ),
          const SizedBox(width: 16),
          Text(
            '分辨率: $_imgWidth x $_imgHeight',
            style: const TextStyle(color: AppColors.blueGray, fontSize: 11),
          ),
        ],
      ),
    );
  }

  Widget _buildInferenceStatus() {
    final ready = _detections.isNotEmpty;
    final message = _showAnnotated
        ? (ready ? '标注画面：检测结果已收到' : '标注画面：等待车端推理结果，当前可能回退为原始画面')
        : (ready ? '原始画面：本地检测框叠加已启用' : '原始画面：等待车端推理结果');
    final color = ready ? AppColors.successGreen : AppColors.warningOrange;
    return Padding(
      padding: const EdgeInsets.symmetric(horizontal: 16),
      child: Container(
        width: double.infinity,
        padding: const EdgeInsets.symmetric(horizontal: 12, vertical: 8),
        decoration: BoxDecoration(
          color: color.withValues(alpha: 0.09),
          borderRadius: BorderRadius.circular(8),
        ),
        child: Row(
          children: [
            Icon(
              ready ? Icons.verified : Icons.hourglass_top,
              color: color,
              size: 17,
            ),
            const SizedBox(width: 8),
            Expanded(
              child: Text(
                message,
                style: TextStyle(color: color, fontSize: 12),
              ),
            ),
          ],
        ),
      ),
    );
  }

  Widget _buildToggleButton({
    required String label,
    required IconData icon,
    required bool selected,
    required VoidCallback onTap,
  }) {
    return GestureDetector(
      onTap: onTap,
      child: Container(
        padding: const EdgeInsets.symmetric(horizontal: 12, vertical: 6),
        decoration: BoxDecoration(
          color: selected
              ? AppColors.orange.withValues(alpha: 0.12)
              : AppColors.surface,
          borderRadius: BorderRadius.circular(8),
          border: Border.all(
            color: selected
                ? AppColors.orange
                : AppColors.blueGray.withValues(alpha: 0.3),
          ),
        ),
        child: Row(
          mainAxisSize: MainAxisSize.min,
          children: [
            Icon(
              icon,
              size: 14,
              color: selected ? AppColors.orange : AppColors.blueGray,
            ),
            const SizedBox(width: 4),
            Text(
              label,
              style: TextStyle(
                color: selected ? AppColors.orange : AppColors.blueGray,
                fontSize: 11,
                fontWeight: selected ? FontWeight.w600 : FontWeight.normal,
              ),
            ),
          ],
        ),
      ),
    );
  }

  // ═══════════════════════════════════════════
  // 人员跟踪控制条
  // ═══════════════════════════════════════════

  Widget _buildTrackingBar() {
    final tracking = _ctrl.latestTrackingStatus;
    final isTracking = tracking.isTracking;

    return Container(
      margin: const EdgeInsets.symmetric(horizontal: 16),
      padding: const EdgeInsets.symmetric(horizontal: 16, vertical: 10),
      decoration: BoxDecoration(
        color: isTracking
            ? AppColors.successGreen.withValues(alpha: 0.1)
            : tracking.isLost
            ? AppColors.orange.withValues(alpha: 0.1)
            : AppColors.surface,
        borderRadius: BorderRadius.circular(12),
        border: Border.all(
          color: isTracking
              ? AppColors.successGreen.withValues(alpha: 0.3)
              : AppColors.blueGray.withValues(alpha: 0.2),
        ),
      ),
      child: Row(
        children: [
          Container(
            width: 8,
            height: 8,
            decoration: BoxDecoration(
              shape: BoxShape.circle,
              color: tracking.statusColor,
            ),
          ),
          const SizedBox(width: 8),
          Text(
            isTracking ? '人员跟踪中' : tracking.eventZh,
            style: TextStyle(
              color: tracking.statusColor,
              fontSize: 13,
              fontWeight: FontWeight.w500,
            ),
          ),
          const Spacer(),
          GestureDetector(
            onTap: isTracking
                ? _ctrl.sendTrackingStop
                : _ctrl.sendTrackingStart,
            child: Container(
              padding: const EdgeInsets.symmetric(horizontal: 12, vertical: 6),
              decoration: BoxDecoration(
                color: isTracking ? AppColors.errorRed : AppColors.bluePurple,
                borderRadius: BorderRadius.circular(8),
              ),
              child: Text(
                isTracking ? '停止跟踪' : '启动跟踪',
                style: const TextStyle(
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
  // 截图控制
  // ═══════════════════════════════════════════

  Widget _buildCaptureControls() {
    return AppCard(
      title: '截图控制',
      icon: Icons.camera_alt,
      child: Column(
        children: [
          // 单次截图 + 停止自动
          Row(
            children: [
              Expanded(
                child: _buildCaptureButton(
                  icon: Icons.camera_alt,
                  label: _ctrl.isCloudMode ? '请求远程截图' : '单次截图',
                  onTap: _ctrl.canSendCommands
                      ? () => _ctrl.sendScreenshot(annotated: _showAnnotated)
                      : null,
                  color: AppColors.orange,
                ),
              ),
              const SizedBox(width: 10),
              Expanded(
                child: _buildCaptureButton(
                  icon: Icons.stop_circle,
                  label: '停止自动截图',
                  onTap: _ctrl.hasLocalMedia
                      ? () {
                          _ctrl.sendCaptureCommand({'action': 'stop'});
                          setState(() => _autoCapture = false);
                        }
                      : null,
                  color: AppColors.blueGray,
                ),
              ),
            ],
          ),
          const SizedBox(height: 12),
          Divider(color: AppColors.blueGray.withValues(alpha: 0.15)),
          const SizedBox(height: 8),
          // 自动截图设置
          Row(
            children: [
              const Icon(
                Icons.timelapse,
                color: AppColors.bluePurple,
                size: 18,
              ),
              const SizedBox(width: 6),
              const Text(
                '自动截图间隔',
                style: TextStyle(color: AppColors.darkNavy, fontSize: 13),
              ),
              const Spacer(),
              SizedBox(
                width: 60,
                height: 32,
                child: TextField(
                  controller: _intervalCtrl,
                  style: const TextStyle(
                    color: AppColors.darkNavy,
                    fontSize: 13,
                  ),
                  textAlign: TextAlign.center,
                  keyboardType: const TextInputType.numberWithOptions(
                    decimal: true,
                  ),
                  decoration: InputDecoration(
                    isDense: true,
                    contentPadding: const EdgeInsets.symmetric(
                      horizontal: 8,
                      vertical: 6,
                    ),
                    suffixText: 's',
                    suffixStyle: const TextStyle(
                      color: AppColors.blueGray,
                      fontSize: 12,
                    ),
                  ),
                  onSubmitted: (v) {
                    final d = double.tryParse(v);
                    if (d != null && d >= 0.5) {
                      setState(() => _captureInterval = d);
                    }
                  },
                ),
              ),
              const SizedBox(width: 8),
              SizedBox(
                height: 32,
                child: ElevatedButton(
                  onPressed: _ctrl.hasLocalMedia
                      ? () {
                          final d = double.tryParse(_intervalCtrl.text) ?? 3.0;
                          _ctrl.sendCaptureCommand({
                            'action': 'set_interval',
                            'interval_sec': d,
                          });
                          setState(() {
                            _autoCapture = true;
                            _captureInterval = d;
                          });
                        }
                      : null,
                  style: ElevatedButton.styleFrom(
                    padding: const EdgeInsets.symmetric(horizontal: 12),
                    textStyle: const TextStyle(fontSize: 12),
                  ),
                  child: const Text('启动'),
                ),
              ),
            ],
          ),
          // 最大保存数
          const SizedBox(height: 10),
          Row(
            children: [
              const Icon(
                Icons.photo_library,
                color: AppColors.blueGray,
                size: 16,
              ),
              const SizedBox(width: 6),
              const Text(
                '最多保存',
                style: TextStyle(color: AppColors.blueGrayDark, fontSize: 12),
              ),
              const Spacer(),
              SizedBox(
                width: 60,
                height: 32,
                child: TextField(
                  style: const TextStyle(
                    color: AppColors.darkNavy,
                    fontSize: 13,
                  ),
                  textAlign: TextAlign.center,
                  keyboardType: TextInputType.number,
                  decoration: const InputDecoration(
                    isDense: true,
                    contentPadding: EdgeInsets.symmetric(
                      horizontal: 8,
                      vertical: 6,
                    ),
                    hintText: '200',
                  ),
                  onSubmitted: (v) {
                    final n = int.tryParse(v);
                    if (n != null && n > 0 && _ctrl.hasLocalMedia) {
                      _ctrl.sendCaptureCommand({
                        'action': 'set_max_images',
                        'max_images': n,
                      });
                    }
                  },
                ),
              ),
              const SizedBox(width: 8),
              SizedBox(
                height: 32,
                child: ElevatedButton(
                  onPressed: _ctrl.hasLocalMedia
                      ? () {
                          // 触发 onSubmitted
                          FocusScope.of(context).unfocus();
                        }
                      : null,
                  style: ElevatedButton.styleFrom(
                    padding: const EdgeInsets.symmetric(horizontal: 12),
                    textStyle: const TextStyle(fontSize: 12),
                    backgroundColor: AppColors.bluePurple,
                  ),
                  child: const Text('设置'),
                ),
              ),
            ],
          ),
        ],
      ),
    );
  }

  Widget _buildCaptureButton({
    required IconData icon,
    required String label,
    VoidCallback? onTap,
    Color color = AppColors.orange,
  }) {
    final enabled = onTap != null;
    return GestureDetector(
      onTap: onTap,
      child: Container(
        padding: const EdgeInsets.symmetric(vertical: 12),
        decoration: BoxDecoration(
          color: enabled ? color.withValues(alpha: 0.12) : AppColors.surfaceAlt,
          borderRadius: BorderRadius.circular(10),
          border: Border.all(
            color: enabled
                ? color.withValues(alpha: 0.4)
                : AppColors.blueGray.withValues(alpha: 0.2),
          ),
        ),
        child: Row(
          mainAxisAlignment: MainAxisAlignment.center,
          children: [
            Icon(
              icon,
              color: enabled
                  ? color
                  : AppColors.blueGray.withValues(alpha: 0.4),
              size: 18,
            ),
            const SizedBox(width: 6),
            Text(
              label,
              style: TextStyle(
                color: enabled
                    ? color
                    : AppColors.blueGray.withValues(alpha: 0.4),
                fontSize: 12,
                fontWeight: FontWeight.w500,
              ),
            ),
          ],
        ),
      ),
    );
  }

  // ═══════════════════════════════════════════
  // 检测结果列表
  // ═══════════════════════════════════════════

  Widget _buildDetectionPanel() {
    final counts = <String, int>{};
    for (final d in _detections) {
      counts[d.className] = (counts[d.className] ?? 0) + 1;
    }

    return AppCard(
      title: '目标识别',
      icon: Icons.crop_free,
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          // 统计摘要
          if (_detections.isNotEmpty) ...[
            Wrap(
              spacing: 8,
              runSpacing: 4,
              children: counts.entries.map((e) {
                return Container(
                  padding: const EdgeInsets.symmetric(
                    horizontal: 8,
                    vertical: 3,
                  ),
                  decoration: BoxDecoration(
                    color: _classColor(e.key).withValues(alpha: 0.12),
                    borderRadius: BorderRadius.circular(6),
                  ),
                  child: Text(
                    '${_classNameZh(e.key)} × ${e.value}',
                    style: TextStyle(
                      color: _classColor(e.key),
                      fontSize: 11,
                      fontWeight: FontWeight.w600,
                    ),
                  ),
                );
              }).toList(),
            ),
            const SizedBox(height: 10),
            Divider(color: AppColors.blueGray.withValues(alpha: 0.15)),
            const SizedBox(height: 6),
          ],
          // 检测列表
          if (_detections.isEmpty)
            Center(
              child: Padding(
                padding: const EdgeInsets.symmetric(vertical: 16),
                child: Column(
                  children: [
                    Icon(
                      Icons.search_off,
                      color: AppColors.blueGray.withValues(alpha: 0.4),
                      size: 28,
                    ),
                    const SizedBox(height: 4),
                    Text(
                      '暂无检测目标',
                      style: TextStyle(
                        color: AppColors.blueGray.withValues(alpha: 0.6),
                        fontSize: 12,
                      ),
                    ),
                  ],
                ),
              ),
            )
          else
            ...(_detections.take(10).map((d) => _buildDetectionItem(d))),
          if (_detections.length > 10)
            Padding(
              padding: const EdgeInsets.only(top: 4),
              child: Center(
                child: Text(
                  '...还有 ${_detections.length - 10} 个目标',
                  style: const TextStyle(
                    color: AppColors.blueGray,
                    fontSize: 11,
                  ),
                ),
              ),
            ),
        ],
      ),
    );
  }

  Widget _buildDetectionItem(Detection d) {
    final color = _classColor(d.className);
    return Padding(
      padding: const EdgeInsets.symmetric(vertical: 4),
      child: Row(
        children: [
          // 类别图标
          Container(
            width: 28,
            height: 28,
            decoration: BoxDecoration(
              color: color.withValues(alpha: 0.12),
              borderRadius: BorderRadius.circular(6),
            ),
            child: Icon(_classIcon(d.className), color: color, size: 16),
          ),
          const SizedBox(width: 8),
          // 类别名 + 置信度
          Expanded(
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                Text(
                  d.classNameZh,
                  style: const TextStyle(
                    color: AppColors.darkNavy,
                    fontSize: 13,
                    fontWeight: FontWeight.w500,
                  ),
                ),
                Text(
                  '置信度: ${(d.confidence * 100).toStringAsFixed(1)}%',
                  style: const TextStyle(
                    color: AppColors.blueGray,
                    fontSize: 11,
                  ),
                ),
              ],
            ),
          ),
          // 位置信息
          Text(
            '(${d.xMin.round()}, ${d.yMin.round()}) '
            '→ (${d.xMax.round()}, ${d.yMax.round()})',
            style: const TextStyle(
              color: AppColors.blueGrayDark,
              fontSize: 10,
              fontFamily: 'monospace',
            ),
          ),
        ],
      ),
    );
  }

  // ═══════════════════════════════════════════
  // 截图状态
  // ═══════════════════════════════════════════

  Widget _buildCaptureStatus() {
    final status = _ctrl.latestCaptureStatus;

    return AppCard(
      title: '截图状态',
      icon: Icons.info_outline,
      child: Column(
        children: [
          Row(
            children: [
              Icon(
                _autoCapture ? Icons.fiber_manual_record : Icons.circle,
                color: _autoCapture
                    ? AppColors.errorRed
                    : AppColors.blueGray.withValues(alpha: 0.5),
                size: 12,
              ),
              const SizedBox(width: 6),
              Text(
                _autoCapture ? '自动截图中 (每 ${_captureInterval}s)' : '手动模式',
                style: TextStyle(
                  color: _autoCapture ? AppColors.errorRed : AppColors.blueGray,
                  fontSize: 12,
                  fontWeight: FontWeight.w500,
                ),
              ),
            ],
          ),
          if (status != null) ...[
            const SizedBox(height: 8),
            Divider(color: AppColors.blueGray.withValues(alpha: 0.15)),
            const SizedBox(height: 6),
            Row(
              children: [
                Icon(
                  status.isSuccess
                      ? Icons.check_circle
                      : status.isError
                      ? Icons.error
                      : Icons.info,
                  color: status.isSuccess
                      ? AppColors.successGreen
                      : status.isError
                      ? AppColors.errorRed
                      : AppColors.blueGray,
                  size: 16,
                ),
                const SizedBox(width: 6),
                Expanded(
                  child: Text(
                    status.description,
                    style: TextStyle(
                      color: status.isSuccess
                          ? AppColors.successGreen
                          : status.isError
                          ? AppColors.errorRed
                          : AppColors.darkNavy,
                      fontSize: 12,
                    ),
                  ),
                ),
              ],
            ),
            if (status.savedCount > 0)
              Padding(
                padding: const EdgeInsets.only(top: 4),
                child: Row(
                  children: [
                    const Icon(
                      Icons.photo_library,
                      color: AppColors.blueGray,
                      size: 14,
                    ),
                    const SizedBox(width: 6),
                    Text(
                      '已保存: ${status.savedCount} 张',
                      style: const TextStyle(
                        color: AppColors.blueGray,
                        fontSize: 11,
                      ),
                    ),
                  ],
                ),
              ),
            if (status.path.isNotEmpty)
              Padding(
                padding: const EdgeInsets.only(top: 4),
                child: Row(
                  children: [
                    const Icon(
                      Icons.folder,
                      color: AppColors.blueGray,
                      size: 14,
                    ),
                    const SizedBox(width: 6),
                    Expanded(
                      child: Text(
                        status.path,
                        style: const TextStyle(
                          color: AppColors.blueGrayDark,
                          fontSize: 10,
                          fontFamily: 'monospace',
                        ),
                        overflow: TextOverflow.ellipsis,
                      ),
                    ),
                  ],
                ),
              ),
          ],
        ],
      ),
    );
  }

  // ═══════════════════════════════════════════
  // 辅助方法
  // ═══════════════════════════════════════════

  Color _classColor(String className) {
    switch (className) {
      case 'person':
        return AppColors.orange;
      case 'obstacle':
        return AppColors.errorRed;
      case 'water':
        return Colors.blue;
      case 'sign':
        return AppColors.bluePurple;
      default:
        return AppColors.blueGray;
    }
  }

  IconData _classIcon(String className) {
    switch (className) {
      case 'person':
        return Icons.person;
      case 'obstacle':
        return Icons.warning;
      case 'water':
        return Icons.water_drop;
      case 'sign':
        return Icons.label;
      default:
        return Icons.help_outline;
    }
  }

  String _classNameZh(String className) {
    switch (className) {
      case 'person':
        return '行人';
      case 'obstacle':
        return '障碍物';
      case 'water':
        return '积水';
      case 'sign':
        return '标识';
      default:
        return className;
    }
  }

  // ═══════════════════════════════════════════
  // 通信日志面板
  // ═══════════════════════════════════════════

  Widget _buildLogPanel() {
    final logs = _ctrl.messages.reversed.take(50).toList();
    return Container(
      margin: const EdgeInsets.symmetric(horizontal: 16, vertical: 8),
      padding: const EdgeInsets.all(16),
      decoration: BoxDecoration(
        color: AppColors.surface,
        borderRadius: BorderRadius.circular(16),
        border: Border.all(
          color: AppColors.blueGray.withValues(alpha: 0.2),
          width: 1,
        ),
        boxShadow: [
          BoxShadow(
            color: Colors.black.withValues(alpha: 0.04),
            blurRadius: 8,
            offset: const Offset(0, 2),
          ),
        ],
      ),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Row(
            children: [
              const Icon(Icons.terminal, color: AppColors.bluePurple, size: 20),
              const SizedBox(width: 8),
              const Text(
                '通信日志',
                style: TextStyle(
                  color: AppColors.bluePurple,
                  fontSize: 14,
                  fontWeight: FontWeight.w600,
                ),
              ),
              const Spacer(),
              IconButton(
                onPressed: logs.isEmpty
                    ? null
                    : () {
                        final allLogs = _ctrl.messages.join('\n');
                        Clipboard.setData(ClipboardData(text: allLogs));
                        ScaffoldMessenger.of(context).showSnackBar(
                          const SnackBar(
                            content: Text('日志已复制到剪贴板'),
                            duration: Duration(seconds: 2),
                          ),
                        );
                      },
                icon: const Icon(Icons.copy, size: 18),
                color: AppColors.bluePurple,
                tooltip: '复制全部日志',
                constraints: const BoxConstraints(minWidth: 36, minHeight: 36),
                padding: EdgeInsets.zero,
              ),
              const SizedBox(width: 4),
              IconButton(
                onPressed: logs.isEmpty ? null : _ctrl.clearMessages,
                icon: const Icon(Icons.delete_outline, size: 18),
                color: AppColors.blueGray,
                tooltip: '清空日志',
                constraints: const BoxConstraints(minWidth: 36, minHeight: 36),
                padding: EdgeInsets.zero,
              ),
            ],
          ),
          const SizedBox(height: 12),
          Container(
            height: 180,
            decoration: BoxDecoration(
              color: AppColors.surfaceAlt,
              borderRadius: BorderRadius.circular(8),
            ),
            child: logs.isEmpty
                ? const Center(
                    child: Text(
                      '暂无日志',
                      style: TextStyle(color: AppColors.blueGray, fontSize: 12),
                    ),
                  )
                : ListView.builder(
                    reverse: true,
                    padding: const EdgeInsets.all(8),
                    itemCount: logs.length,
                    itemBuilder: (context, index) {
                      return Padding(
                        padding: const EdgeInsets.symmetric(vertical: 1),
                        child: Text(
                          logs[index],
                          style: TextStyle(
                            color: logs[index].contains('[错误]')
                                ? AppColors.errorRed
                                : logs[index].contains('[收到]')
                                ? AppColors.successGreen
                                : logs[index].contains('[调试]')
                                ? AppColors.blueGray
                                : AppColors.darkNavyLight,
                            fontSize: 11,
                            fontFamily: 'monospace',
                          ),
                        ),
                      );
                    },
                  ),
          ),
        ],
      ),
    );
  }
}

// ═══════════════════════════════════════════
// 检测框叠加层
// ═══════════════════════════════════════════

class DetectionOverlay extends StatelessWidget {
  final List<Detection> detections;
  final double imageWidth;
  final double imageHeight;

  const DetectionOverlay({
    super.key,
    required this.detections,
    required this.imageWidth,
    required this.imageHeight,
  });

  @override
  Widget build(BuildContext context) {
    return CustomPaint(
      painter: _DetectionPainter(
        detections: detections,
        imageWidth: imageWidth,
        imageHeight: imageHeight,
      ),
      size: Size.infinite,
    );
  }
}

class _DetectionPainter extends CustomPainter {
  final List<Detection> detections;
  final double imageWidth;
  final double imageHeight;

  _DetectionPainter({
    required this.detections,
    required this.imageWidth,
    required this.imageHeight,
  });

  @override
  void paint(Canvas canvas, Size size) {
    if (imageWidth <= 0 || imageHeight <= 0) return;

    // 按 BoxFit.cover 计算缩放和偏移
    final scaleX = size.width / imageWidth;
    final scaleY = size.height / imageHeight;
    final scale = scaleX > scaleY ? scaleX : scaleY;

    final displayW = imageWidth * scale;
    final displayH = imageHeight * scale;
    final offsetX = (size.width - displayW) / 2;
    final offsetY = (size.height - displayH) / 2;

    for (final det in detections) {
      final color = _colorFor(det.className);

      // 框画笔
      final boxPaint = Paint()
        ..color = color
        ..style = PaintingStyle.stroke
        ..strokeWidth = 2.0;

      // 半透明填充
      final fillPaint = Paint()
        ..color = color.withValues(alpha: 0.1)
        ..style = PaintingStyle.fill;

      final rect = Rect.fromLTRB(
        det.xMin * scale + offsetX,
        det.yMin * scale + offsetY,
        det.xMax * scale + offsetX,
        det.yMax * scale + offsetY,
      );

      canvas.drawRect(rect, fillPaint);
      canvas.drawRect(rect, boxPaint);

      // 标签文字
      final label =
          '${det.className} ${(det.confidence * 100).toStringAsFixed(0)}%';
      final tp = TextPainter(
        text: TextSpan(
          text: label,
          style: TextStyle(
            color: Colors.white,
            fontSize: 11,
            fontWeight: FontWeight.bold,
            background: Paint()..color = color,
          ),
        ),
        textDirection: TextDirection.ltr,
      );
      tp.layout(maxWidth: rect.width);
      tp.paint(canvas, Offset(rect.left, rect.top - 16));
    }
  }

  Color _colorFor(String className) {
    switch (className) {
      case 'person':
        return const Color(0xFFFF9B51); // orange
      case 'obstacle':
        return const Color(0xFFE53935); // red
      case 'water':
        return const Color(0xFF2196F3); // blue
      case 'sign':
        return const Color(0xFF4B5694); // blue-purple
      default:
        return const Color(0xFFBFC9D1); // gray
    }
  }

  @override
  bool shouldRepaint(covariant _DetectionPainter old) {
    return detections != old.detections;
  }
}
