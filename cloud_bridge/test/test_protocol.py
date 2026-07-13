import json
from pathlib import Path
import sys
import unittest


PACKAGE_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PACKAGE_ROOT))

from cloud_bridge.protocol import (  # noqa: E402
    CloudTopics,
    CommandValidationError,
    RecentCommandIds,
    parse_motion_command,
    parse_snapshot_request,
    parse_task_command,
)


class CloudTopicsTest(unittest.TestCase):
    def test_legacy_topics_are_unchanged_without_device_id(self):
        topics = CloudTopics.build("/icar", "")
        self.assertEqual(topics.command, "/icar/cmd")
        self.assertEqual(topics.status, "/icar/status")
        self.assertEqual(topics.pose, "/icar/pose")
        self.assertEqual(topics.llm_response, "/icar/llm/response")
        self.assertEqual(topics.snapshot_request, "/icar/snapshot/request")
        self.assertEqual(topics.snapshot, "/icar/snapshot")

    def test_device_id_is_inserted_after_prefix(self):
        topics = CloudTopics.build("icar", "robot-01")
        self.assertEqual(topics.command, "/icar/robot-01/cmd")
        self.assertEqual(topics.online, "/icar/robot-01/online")

    def test_rejects_mqtt_wildcards(self):
        with self.assertRaises(ValueError):
            CloudTopics.build("/icar/+", "robot-01")
        with self.assertRaises(ValueError):
            CloudTopics.build("/icar", "robot/#")

    def test_rejects_empty_prefix(self):
        with self.assertRaises(ValueError):
            CloudTopics.build("/", "")


class TaskCommandTest(unittest.TestCase):
    def test_parses_current_legacy_payload(self):
        command = parse_task_command(
            b'{"action":"patrol","route":["A","B","C"]}', now=100
        )
        self.assertEqual(command.action, "patrol")
        self.assertEqual(command.route, ["A", "B", "C"])
        self.assertEqual(json.loads(command.params_json), {})

    def test_normalizes_params_and_command_id(self):
        command = parse_task_command(
            json.dumps(
                {
                    "action": "start",
                    "route": [" A ", "B"],
                    "params": {"stop_on_obstacle": True},
                    "command_id": " cmd-001 ",
                    "issued_at": 90,
                    "expires_at": 110,
                }
            ),
            now=100,
        )
        self.assertEqual(command.route, ["A", "B"])
        self.assertEqual(command.command_id, "cmd-001")
        self.assertEqual(json.loads(command.params_json), {"stop_on_obstacle": True})

    def test_rejects_expired_command(self):
        with self.assertRaisesRegex(CommandValidationError, "已过期"):
            parse_task_command(
                '{"action":"patrol","expires_at":99}', now=100
            )

    def test_rejects_unknown_action(self):
        with self.assertRaisesRegex(CommandValidationError, "不支持"):
            parse_task_command('{"action":"forward"}', now=100)

    def test_rejects_invalid_route(self):
        with self.assertRaisesRegex(CommandValidationError, "route"):
            parse_task_command('{"action":"patrol","route":[]}', now=100)

    def test_rejects_oversized_payload(self):
        with self.assertRaisesRegex(CommandValidationError, "大小限制"):
            parse_task_command(
                '{"action":"patrol"}', now=100, max_payload_bytes=5
            )


class RecentCommandIdsTest(unittest.TestCase):
    def test_detects_duplicates_and_evicts_old_entries(self):
        recent = RecentCommandIds(capacity=2)
        self.assertFalse(recent.seen_or_add("a"))
        self.assertTrue(recent.seen_or_add("a"))
        self.assertFalse(recent.seen_or_add("b"))
        self.assertFalse(recent.seen_or_add("c"))
        self.assertFalse(recent.seen_or_add("a"))

    def test_empty_command_id_is_not_deduplicated(self):
        recent = RecentCommandIds()
        self.assertFalse(recent.seen_or_add(""))
        self.assertFalse(recent.seen_or_add(""))


class MotionCommandTest(unittest.TestCase):
    def test_maps_mecanum_and_turn_commands(self):
        left = parse_motion_command(
            '{"command":"left","speed":0.5,"lease_ms":1000,"issued_at_ms":1000}',
            now_ms=1000,
        )
        turn = parse_motion_command(
            '{"command":"turn_right","speed":0.5,"lease_ms":1000,"issued_at_ms":1000}',
            now_ms=1000,
        )
        self.assertAlmostEqual(left.linear_y, 0.175)
        self.assertAlmostEqual(turn.angular_z, -0.6)

    def test_rejects_expired_motion(self):
        with self.assertRaisesRegex(CommandValidationError, "已过期"):
            parse_motion_command(
                '{"command":"forward","speed":0.5,"lease_ms":1000,"issued_at_ms":1000}',
                now_ms=5000,
            )

    def test_rejects_long_or_invalid_lease(self):
        with self.assertRaisesRegex(CommandValidationError, "lease_ms"):
            parse_motion_command(
                '{"command":"forward","speed":0.5,"lease_ms":5000,"issued_at_ms":1000}',
                now_ms=1000,
            )


class SnapshotRequestTest(unittest.TestCase):
    def test_parses_raw_and_annotated_requests(self):
        raw = parse_snapshot_request(
            '{"request_id":"snap-1","issued_at":90,"expires_at":110}',
            now=100,
        )
        annotated = parse_snapshot_request(
            '{"request_id":"snap-2","annotated":true}', now=100
        )
        self.assertEqual(raw.request_id, "snap-1")
        self.assertFalse(raw.annotated)
        self.assertTrue(annotated.annotated)

    def test_rejects_expired_or_unidentified_request(self):
        with self.assertRaisesRegex(CommandValidationError, "已过期"):
            parse_snapshot_request(
                '{"request_id":"snap-1","expires_at":99}', now=100
            )
        with self.assertRaisesRegex(CommandValidationError, "request_id"):
            parse_snapshot_request('{"annotated":false}', now=100)

    def test_rejects_non_boolean_annotated(self):
        with self.assertRaisesRegex(CommandValidationError, "annotated"):
            parse_snapshot_request(
                '{"request_id":"snap-1","annotated":"yes"}', now=100
            )

if __name__ == "__main__":
    unittest.main()
