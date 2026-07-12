import unittest

from voice_control.intent_classifier import classify_intent


class IntentClassifierTest(unittest.TestCase):
    def test_chat(self):
        result = classify_intent("我今天有点想家")
        self.assertEqual(result["intent"], "chat")
        self.assertFalse(result["requires_confirmation"])

    def test_robot_task_requires_confirmation(self):
        result = classify_intent("请开始巡检二楼走廊")
        self.assertEqual(result["intent"], "robot_task")
        self.assertTrue(result["requires_confirmation"])

    def test_care_alert(self):
        result = classify_intent("我有点头晕，帮我找护士")
        self.assertEqual(result["intent"], "care_alert")

    def test_emergency_has_priority(self):
        result = classify_intent("我摔倒了，快来人救命")
        self.assertEqual(result["intent"], "emergency")
        self.assertEqual(result["interaction"], "interrupt")


if __name__ == "__main__":
    unittest.main()
