/// 视觉检测与截图数据模型
///
/// 对应 ROS2 Topics:
///   /vision/detections      → icar_interfaces/msg/DetectionArray
///   /vision/capture_status  → std_msgs/msg/String (JSON)
///   /vision/detections_json → std_msgs/msg/String (JSON, 调试用)
library;

/// 单个检测目标
class Detection {
  /// 目标类别: person / obstacle / water / sign / unknown
  final String className;

  /// 置信度 0.0 ~ 1.0
  final double confidence;

  /// 目标框左上角 x
  final double xMin;

  /// 目标框左上角 y
  final double yMin;

  /// 目标框右下角 x
  final double xMax;

  /// 目标框右下角 y
  final double yMax;

  /// 截图保存路径（可能为空）
  final String imagePath;

  Detection({
    required this.className,
    required this.confidence,
    required this.xMin,
    required this.yMin,
    required this.xMax,
    required this.yMax,
    this.imagePath = '',
  });

  factory Detection.fromJson(Map<String, dynamic> json) {
    return Detection(
      className: json['class_name']?.toString() ?? 'unknown',
      confidence: (json['confidence'] as num?)?.toDouble() ?? 0.0,
      xMin: (json['x_min'] as num?)?.toDouble() ?? 0.0,
      yMin: (json['y_min'] as num?)?.toDouble() ?? 0.0,
      xMax: (json['x_max'] as num?)?.toDouble() ?? 0.0,
      yMax: (json['y_max'] as num?)?.toDouble() ?? 0.0,
      imagePath: json['image_path']?.toString() ?? '',
    );
  }

  /// 目标框宽度
  double get width => xMax - xMin;

  /// 目标框高度
  double get height => yMax - yMin;

  /// 目标框中心 x
  double get centerX => (xMin + xMax) / 2;

  /// 目标框中心 y
  double get centerY => (yMin + yMax) / 2;

  /// 类别中文映射
  String get classNameZh {
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
}

/// 检测结果数组
class DetectionArray {
  final List<Detection> detections;
  final int imageWidth;
  final int imageHeight;
  final String model;
  final String backend;

  DetectionArray({
    required this.detections,
    this.imageWidth = 640,
    this.imageHeight = 480,
    this.model = '',
    this.backend = '',
  });

  factory DetectionArray.fromJson(Map<String, dynamic> json) {
    final list = json['detections'] as List? ?? [];
    return DetectionArray(
      detections: list
          .map((e) => Detection.fromJson(e as Map<String, dynamic>))
          .toList(),
      imageWidth: json['image_width'] as int? ?? 640,
      imageHeight: json['image_height'] as int? ?? 480,
      model: json['model']?.toString() ?? '',
      backend: json['backend']?.toString() ?? '',
    );
  }

  /// 按类别统计数量
  Map<String, int> get classCounts {
    final map = <String, int>{};
    for (final d in detections) {
      map[d.className] = (map[d.className] ?? 0) + 1;
    }
    return map;
  }
}

/// 截图状态
class CaptureStatus {
  final String module;
  final String event;
  final int savedCount;
  final String path;
  final String error;

  CaptureStatus({
    this.module = '',
    this.event = '',
    this.savedCount = 0,
    this.path = '',
    this.error = '',
  });

  factory CaptureStatus.fromJson(Map<String, dynamic> json) {
    final data = json['data'] as Map<String, dynamic>?;
    return CaptureStatus(
      module: json['module']?.toString() ?? '',
      event: json['event']?.toString() ?? '',
      savedCount: json['saved_count'] as int? ?? 0,
      path: data?['path']?.toString() ?? '',
      error: json['error']?.toString() ?? '',
    );
  }

  bool get isSuccess => event == 'image_saved';
  bool get isError => event == 'error' || error.isNotEmpty;

  /// 简短状态描述
  String get description {
    if (isSuccess) return '截图已保存';
    if (isError) return '错误: $error';
    return event;
  }
}
