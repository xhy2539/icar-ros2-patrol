from pathlib import Path


SOURCE = Path(__file__).resolve().parents[1] / "voice_control" / "doubao_voice_node.py"


def test_system_role_requires_direct_marked_motion_output():
    role_source = SOURCE.read_text(encoding="utf-8")

    assert "不要求二次确认" in role_source
    assert "执行任务：<原始移动指令>" in role_source
