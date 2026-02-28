"""
测试军事系统的 disband_legions_for_war 方法
"""

import pytest
from src.core.systems.military_system import MilitarySystem
from src.core.entities.legion import LegionStatus
from src.core.game_state import GameState


@pytest.fixture
def military_system():
    state = GameState()
    state.treasury = 1000
    return MilitarySystem(state)


class TestMilitarySystemDisband:
    def test_disband_existing_legions(self, military_system):
        """测试解散存在的军团"""
        military_system.recruit_legion(1)
        military_system.recruit_legion(2)
        military_system.recruit_legion(3)

        disbanded, errors = military_system.disband_legions_for_war([1, 2, 4])

        assert disbanded == 2  # 1和2成功，4存在但未征召，解散失败
        assert len(errors) == 1
        # 检查错误信息是否包含“IV”或“无法解散”或数字“4”
        error_msg = errors[0]
        assert "IV" in error_msg or "无法解散" in error_msg or "4" in error_msg

    def test_disband_already_disbanded(self, military_system):
        """测试解散已解散的军团"""
        military_system.recruit_legion(1)
        military_system.disband_legion(1)  # 先解散

        disbanded, errors = military_system.disband_legions_for_war([1])

        assert disbanded == 0
        assert len(errors) == 1
        # 检查错误信息是否合理（可能包含“无法解散”或“已在解散状态”）
        assert "无法解散" in errors[0] or "已在解散状态" in errors[0]

    def test_disband_with_war_id(self, military_system):
        """测试解散指派给战争的军团（应失败）"""
        military_system.recruit_legion(1)
        legion = military_system.get_legion_by_number(1)
        legion.war_id = "test_war"

        disbanded, errors = military_system.disband_legions_for_war([1])

        assert disbanded == 0
        assert len(errors) == 1
        # 检查错误信息是否包含“指派给战争”
        assert "指派给战争" in errors[0] or "war" in errors[0].lower()