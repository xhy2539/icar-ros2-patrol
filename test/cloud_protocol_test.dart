import 'package:flutter_test/flutter_test.dart';
import 'package:icar_app/services/cloud_protocol.dart';

void main() {
  group('CloudMqttTopics', () {
    test('keeps legacy topics without a device id', () {
      final topics = CloudMqttTopics.build();
      expect(topics.command, '/icar/cmd');
      expect(topics.control, '/icar/control');
      expect(topics.status, '/icar/status');
      expect(topics.environment, '/icar/env');
      expect(topics.llmResponse, '/icar/llm/response');
      expect(topics.snapshotRequest, '/icar/snapshot/request');
      expect(topics.snapshot, '/icar/snapshot');
    });

    test('adds the device id after the prefix', () {
      final topics = CloudMqttTopics.build(deviceId: 'robot-01');
      expect(topics.command, '/icar/robot-01/cmd');
      expect(topics.online, '/icar/robot-01/online');
      expect(topics.pose, '/icar/robot-01/pose');
    });

    test('rejects wildcard topic configuration', () {
      expect(
        () => CloudMqttTopics.build(prefix: '/icar/+'),
        throwsArgumentError,
      );
      expect(
        () => CloudMqttTopics.build(deviceId: 'robot/#'),
        throwsArgumentError,
      );
    });
  });

  test('normalizes legacy cloud log payload', () {
    final normalized = normalizeCloudTaskLog({
      'task_id': 'task-1',
      'data': '{"point":"A"}',
    });
    expect(normalized['data_json'], '{"point":"A"}');
    expect(normalized['timestamp'], '');
  });

  group('CloudSnapshot', () {
    test('parses a bounded JPEG payload', () {
      final snapshot = CloudSnapshot.fromJson({
        'ok': true,
        'request_id': 'snap-1',
        'annotated': true,
        'captured_at_ms': 123,
        'image_base64': '/9j/2Q==',
      });
      expect(snapshot.ok, isTrue);
      expect(snapshot.annotated, isTrue);
      expect(snapshot.imageBase64, '/9j/2Q==');
    });

    test('rejects a successful response without image data', () {
      expect(
        () => CloudSnapshot.fromJson({'ok': true, 'request_id': 'snap-1'}),
        throwsFormatException,
      );
    });
  });
}
