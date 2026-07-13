import 'dart:convert';

enum CarConnectionMode { local, cloud }

extension CarConnectionModeX on CarConnectionMode {
  String get storageValue => name;

  String get label => this == CarConnectionMode.local ? '局域网直连' : '云端远程';

  static CarConnectionMode fromStorage(String? value) {
    return value == CarConnectionMode.cloud.name
        ? CarConnectionMode.cloud
        : CarConnectionMode.local;
  }
}

class CloudMqttConfig {
  final String host;
  final int port;
  final String username;
  final String password;
  final String topicPrefix;
  final String deviceId;
  final bool useTls;
  final bool autoReconnect;

  const CloudMqttConfig({
    required this.host,
    required this.port,
    required this.username,
    required this.password,
    this.topicPrefix = '/icar',
    this.deviceId = '',
    this.useTls = false,
    this.autoReconnect = true,
  });

  static const defaults = CloudMqttConfig(
    host: '82.156.132.43',
    port: 1883,
    username: 'icar',
    password: 'icar123456',
  );
}

class CloudMqttTopics {
  final String command;
  final String control;
  final String status;
  final String nav;
  final String pose;
  final String obstacle;
  final String environment;
  final String alert;
  final String log;
  final String ack;
  final String online;
  final String llmCommand;
  final String llmGenerateReport;
  final String llmResponse;
  final String llmReport;
  final String snapshotRequest;
  final String snapshot;

  const CloudMqttTopics._({
    required this.command,
    required this.control,
    required this.status,
    required this.nav,
    required this.pose,
    required this.obstacle,
    required this.environment,
    required this.alert,
    required this.log,
    required this.ack,
    required this.online,
    required this.llmCommand,
    required this.llmGenerateReport,
    required this.llmResponse,
    required this.llmReport,
    required this.snapshotRequest,
    required this.snapshot,
  });

  factory CloudMqttTopics.build({
    String prefix = '/icar',
    String deviceId = '',
  }) {
    final normalizedPrefix =
        '/${prefix.trim().replaceAll(RegExp(r'^/+|/+$'), '')}';
    final normalizedDevice = deviceId.trim().replaceAll(RegExp(r'^/+|/+$'), '');
    if (normalizedPrefix == '/' || normalizedPrefix.contains(RegExp(r'[+#]'))) {
      throw ArgumentError('MQTT Topic 前缀不能为空或包含通配符');
    }
    if (normalizedDevice.contains(RegExp(r'[/+#]'))) {
      throw ArgumentError('设备 ID 不能包含 /、+ 或 #');
    }
    final base = normalizedDevice.isEmpty
        ? normalizedPrefix
        : '$normalizedPrefix/$normalizedDevice';
    return CloudMqttTopics._(
      command: '$base/cmd',
      control: '$base/control',
      status: '$base/status',
      nav: '$base/nav',
      pose: '$base/pose',
      obstacle: '$base/obstacle',
      environment: '$base/env',
      alert: '$base/alert',
      log: '$base/log',
      ack: '$base/ack',
      online: '$base/online',
      llmCommand: '$base/llm/command',
      llmGenerateReport: '$base/llm/generate_report',
      llmResponse: '$base/llm/response',
      llmReport: '$base/llm/report',
      snapshotRequest: '$base/snapshot/request',
      snapshot: '$base/snapshot',
    );
  }

  List<String> get subscriptions => [
    status,
    nav,
    pose,
    obstacle,
    environment,
    alert,
    log,
    ack,
    online,
    llmResponse,
    llmReport,
    snapshot,
  ];
}

class CloudSnapshot {
  final bool ok;
  final String requestId;
  final bool annotated;
  final String imageBase64;
  final int capturedAtMs;
  final String error;

  const CloudSnapshot({
    required this.ok,
    required this.requestId,
    required this.annotated,
    required this.imageBase64,
    required this.capturedAtMs,
    required this.error,
  });

  factory CloudSnapshot.fromJson(Map<String, dynamic> json) {
    final ok = json['ok'] == true;
    final requestId = json['request_id']?.toString() ?? '';
    final imageBase64 = json['image_base64']?.toString() ?? '';
    if (requestId.isEmpty) {
      throw const FormatException('远程截图缺少 request_id');
    }
    if (ok) {
      if (imageBase64.isEmpty || imageBase64.length > 1024 * 1024) {
        throw const FormatException('远程截图为空或超过 1 MiB Base64 限制');
      }
      try {
        base64Decode(imageBase64);
      } on FormatException {
        throw const FormatException('远程截图不是有效 Base64');
      }
    }
    return CloudSnapshot(
      ok: ok,
      requestId: requestId,
      annotated: json['annotated'] == true,
      imageBase64: imageBase64,
      capturedAtMs: (json['captured_at_ms'] as num?)?.toInt() ?? 0,
      error: json['error']?.toString() ?? '',
    );
  }
}

Map<String, dynamic> normalizeCloudTaskLog(Map<String, dynamic> json) {
  return {
    ...json,
    'data_json': json['data_json'] ?? json['data'] ?? '',
    'timestamp': json['timestamp'] ?? '',
  };
}
