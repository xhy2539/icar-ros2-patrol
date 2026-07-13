import 'dart:async';
import 'dart:convert';

import 'package:mqtt_client/mqtt_client.dart';
import 'package:mqtt_client/mqtt_server_client.dart';

import 'car_tcp_service.dart' show CarConnectionState;
import 'cloud_protocol.dart';
import 'data_models.dart';

class CloudMqttService {
  MqttServerClient? _client;
  StreamSubscription? _updatesSubscription;
  CloudMqttConfig _config = CloudMqttConfig.defaults;
  CloudMqttTopics _topics = CloudMqttTopics.build();
  bool _manualDisconnect = false;
  bool _robotOnline = false;

  CarConnectionState _state = CarConnectionState.disconnected;
  CarConnectionState get state => _state;
  bool get isConnected => _state == CarConnectionState.connected;
  bool get robotOnline => _robotOnline;

  final _taskStatusController = StreamController<TaskStatus>.broadcast();
  final _navStatusController = StreamController<NavStatus>.broadcast();
  final _poseController = StreamController<RobotPose>.broadcast();
  final _obstacleController = StreamController<ObstacleStatus>.broadcast();
  final _envDataController = StreamController<EnvData>.broadcast();
  final _sensorAlertController = StreamController<SensorAlert>.broadcast();
  final _safetyAlarmController = StreamController<SafetyAlarm>.broadcast();
  final _taskLogController = StreamController<TaskLog>.broadcast();
  final _ackController = StreamController<Map<String, dynamic>>.broadcast();
  final _onlineController = StreamController<bool>.broadcast();
  final _llmCommandController =
      StreamController<Map<String, dynamic>>.broadcast();
  final _reportController = StreamController<Map<String, dynamic>>.broadcast();
  final _snapshotController = StreamController<CloudSnapshot>.broadcast();

  Stream<TaskStatus> get taskStatusStream => _taskStatusController.stream;
  Stream<NavStatus> get navStatusStream => _navStatusController.stream;
  Stream<RobotPose> get poseStream => _poseController.stream;
  Stream<ObstacleStatus> get obstacleStream => _obstacleController.stream;
  Stream<EnvData> get envDataStream => _envDataController.stream;
  Stream<SensorAlert> get sensorAlertStream => _sensorAlertController.stream;
  Stream<SafetyAlarm> get safetyAlarmStream => _safetyAlarmController.stream;
  Stream<TaskLog> get taskLogStream => _taskLogController.stream;
  Stream<Map<String, dynamic>> get ackStream => _ackController.stream;
  Stream<bool> get onlineStream => _onlineController.stream;
  Stream<Map<String, dynamic>> get llmCommandStream =>
      _llmCommandController.stream;
  Stream<Map<String, dynamic>> get reportStream => _reportController.stream;
  Stream<CloudSnapshot> get snapshotStream => _snapshotController.stream;

  void Function(CarConnectionState)? onStateChanged;
  void Function(String)? onError;
  void Function(String)? onLog;

  Future<bool> connect(CloudMqttConfig config) async {
    if (_state == CarConnectionState.connected ||
        _state == CarConnectionState.connecting) {
      return true;
    }

    _config = config;
    _topics = CloudMqttTopics.build(
      prefix: config.topicPrefix,
      deviceId: config.deviceId,
    );
    _manualDisconnect = false;
    _setState(CarConnectionState.connecting);

    final clientId =
        'icarapp_${DateTime.now().millisecondsSinceEpoch.toRadixString(16)}';
    final client = MqttServerClient.withPort(config.host, clientId, config.port)
      ..logging(on: false)
      ..setProtocolV311()
      ..keepAlivePeriod = 30
      ..connectTimeoutPeriod = 8000
      ..secure = config.useTls
      ..autoReconnect = config.autoReconnect
      ..resubscribeOnAutoReconnect = true;

    client.onConnected = _onConnected;
    client.onDisconnected = _onDisconnected;
    client.onAutoReconnect = () {
      onLog?.call('MQTT 正在自动重连');
      _setState(CarConnectionState.connecting);
    };
    client.onAutoReconnected = () {
      onLog?.call('MQTT 自动重连成功');
      _setState(CarConnectionState.connected);
    };
    client.connectionMessage = MqttConnectMessage()
        .withClientIdentifier(clientId)
        .startClean()
        .withWillQos(MqttQos.atLeastOnce);

    _client = client;
    try {
      final status = await client
          .connect(config.username, config.password)
          .timeout(const Duration(seconds: 10));
      if (status?.state != MqttConnectionState.connected) {
        throw StateError('Broker 拒绝连接: ${status?.returnCode}');
      }

      await _updatesSubscription?.cancel();
      _updatesSubscription = client.updates?.listen(_onMessages);
      for (final topic in _topics.subscriptions) {
        client.subscribe(topic, MqttQos.atLeastOnce);
      }
      _setState(CarConnectionState.connected);
      onLog?.call('MQTT 已连接并订阅 ${_topics.subscriptions.length} 个 Topic');
      return true;
    } catch (error) {
      onError?.call('MQTT 连接失败: $error');
      client.disconnect();
      _setState(CarConnectionState.error);
      return false;
    }
  }

  Future<void> disconnect() async {
    _manualDisconnect = true;
    await _updatesSubscription?.cancel();
    _updatesSubscription = null;
    _client?.disconnect();
    _client = null;
    _setRobotOnline(false);
    _setState(CarConnectionState.disconnected);
  }

  bool publishPatrol({
    required List<String> route,
    Map<String, dynamic> params = const {},
  }) {
    if (!isConnected || !_robotOnline || route.isEmpty) return false;
    final now = DateTime.now().millisecondsSinceEpoch ~/ 1000;
    return _publish(_topics.command, {
      'action': 'patrol',
      'route': route,
      'params': params,
      'command_id': 'app_${DateTime.now().microsecondsSinceEpoch}',
      'issued_at': now,
      'expires_at': now + 30,
    });
  }

  bool publishManualControl(String command, double speed) {
    if (!isConnected || !_robotOnline) return false;
    return _publish(_topics.control, {
      'command': command,
      'speed': speed.clamp(0.0, 1.0),
      'lease_ms': 1000,
      'issued_at_ms': DateTime.now().millisecondsSinceEpoch,
    });
  }

  bool publishLlmCommand(String text, String requestId) {
    if (!isConnected || !_robotOnline || text.trim().isEmpty) return false;
    return _publish(_topics.llmCommand, {
      'text': text.trim(),
      'request_id': requestId,
    });
  }

  bool publishReportRequest(String taskId) {
    if (!isConnected || !_robotOnline) return false;
    return _publish(_topics.llmGenerateReport, {'task_id': taskId});
  }

  bool publishSnapshotRequest({bool annotated = false}) {
    if (!isConnected || !_robotOnline) return false;
    final now = DateTime.now().millisecondsSinceEpoch ~/ 1000;
    return _publish(_topics.snapshotRequest, {
      'request_id': 'snap_${DateTime.now().microsecondsSinceEpoch}',
      'annotated': annotated,
      'issued_at': now,
      'expires_at': now + 10,
    });
  }

  bool _publish(String topic, Map<String, dynamic> payload) {
    final client = _client;
    if (!isConnected || client == null) return false;
    try {
      final builder = MqttClientPayloadBuilder()
        ..addUTF8String(jsonEncode(payload));
      client.publishMessage(topic, MqttQos.atLeastOnce, builder.payload!);
      onLog?.call('MQTT → $topic');
      return true;
    } catch (error) {
      onError?.call('MQTT 发布失败: $error');
      return false;
    }
  }

  void _onMessages(List<MqttReceivedMessage<MqttMessage?>>? messages) {
    if (messages == null) return;
    for (final received in messages) {
      final publish = received.payload as MqttPublishMessage;
      final payload = MqttPublishPayload.bytesToStringAsString(
        publish.payload.message,
      );
      _routeMessage(received.topic, payload);
    }
  }

  void _routeMessage(String topic, String payload) {
    try {
      final decoded = jsonDecode(payload);
      if (decoded is! Map) {
        throw const FormatException('JSON 顶层不是对象');
      }
      final json = Map<String, dynamic>.from(decoded);
      if (topic == _topics.status) {
        _taskStatusController.add(TaskStatus.fromJson(json));
      } else if (topic == _topics.nav) {
        _navStatusController.add(NavStatus.fromJson(json));
      } else if (topic == _topics.pose) {
        _poseController.add(RobotPose.fromJson(json));
      } else if (topic == _topics.obstacle) {
        _obstacleController.add(ObstacleStatus.fromJson(json));
      } else if (topic == _topics.environment) {
        _envDataController.add(EnvData.fromJson(json));
      } else if (topic == _topics.alert) {
        if (json['hazard_type'] != null) {
          _safetyAlarmController.add(SafetyAlarm.fromJson(json));
        }
        _sensorAlertController.add(SensorAlert.fromJson(json));
      } else if (topic == _topics.log) {
        _taskLogController.add(TaskLog.fromJson(normalizeCloudTaskLog(json)));
      } else if (topic == _topics.ack) {
        _ackController.add(json);
      } else if (topic == _topics.online) {
        _setRobotOnline(json['online'] == true);
      } else if (topic == _topics.llmResponse) {
        _llmCommandController.add(json);
      } else if (topic == _topics.llmReport) {
        _reportController.add(json);
      } else if (topic == _topics.snapshot) {
        _snapshotController.add(CloudSnapshot.fromJson(json));
      }
    } catch (error) {
      onError?.call('MQTT 消息解析失败 ($topic): $error');
    }
  }

  void _onConnected() {
    _setState(CarConnectionState.connected);
  }

  void _onDisconnected() {
    _setRobotOnline(false);
    if (_manualDisconnect) {
      _setState(CarConnectionState.disconnected);
    } else if (_config.autoReconnect) {
      _setState(CarConnectionState.connecting);
    } else {
      _setState(CarConnectionState.error);
    }
  }

  void _setRobotOnline(bool value) {
    if (_robotOnline == value) return;
    _robotOnline = value;
    _onlineController.add(value);
    onLog?.call(value ? '小车云桥在线' : '小车云桥离线');
  }

  void _setState(CarConnectionState value) {
    if (_state == value) return;
    _state = value;
    onStateChanged?.call(value);
  }

  Future<void> dispose() async {
    await disconnect();
    await _taskStatusController.close();
    await _navStatusController.close();
    await _poseController.close();
    await _obstacleController.close();
    await _envDataController.close();
    await _sensorAlertController.close();
    await _safetyAlarmController.close();
    await _taskLogController.close();
    await _ackController.close();
    await _onlineController.close();
    await _llmCommandController.close();
    await _reportController.close();
    await _snapshotController.close();
  }
}
