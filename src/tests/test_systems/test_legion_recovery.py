# src/tests/test_systems/test_legion_recovery.py
"""
测试军团恢复机制：
- 标记 DESTROYED
- 恢复条件判断
- 按顺序恢复
- 配置读取
"""

import pytest
from src.core.game_state import GameState
from src.core.systems.military_system import MilitarySystem
from src.core.entities.legion import LegionStatus
from src.core.entities.entities import GameTurn


@pytest.fixture
def state():
    """创建测试用 GameState，设置回合、配置和国库"""
    config = {
        "combat_rules": {
            "legion_recovery_interval": 5
        }
    }
    state = GameState.create_for_testing(config)
    state.turn = GameTurn(turn_number=1, year=-264)
    state.treasury = 1000  # 设置国库，确保征召成功
    return state


@pytest.fixture
def military_system(state):
    """创建 MilitarySystem 实例（会自动初始化10个军团）"""
    ms = MilitarySystem(state)
    return ms


class TestLegionRecovery:
    """军团恢复测试"""

    def test_initial_state(self, military_system):
        """测试初始所有军团为 UNRAISED"""
        legions = military_system.get_all_legions()
        assert len(legions) == 16
        for leg in legions:
            assert leg.status == LegionStatus.UNRAISED
            assert leg.destroyed_turn == 0

    def test_mark_destroyed(self, military_system):
        """测试标记军团被摧毁"""
        legion = military_system.get_legion_by_number(1)
        legion.mark_destroyed(10)  # 假设在第10回合被摧毁

        assert legion.status == LegionStatus.DESTROYED
        assert legion.destroyed_turn == 10
        assert legion.war_id is None
        assert legion.commander_id is None
        assert legion.is_veteran is False  # 重置

    def test_get_destroyed_legions_order(self, military_system):
        """测试获取被摧毁军团列表并按摧毁回合排序"""
        # 摧毁几个军团，故意顺序乱
        leg1 = military_system.get_legion_by_number(1)
        leg2 = military_system.get_legion_by_number(2)
        leg3 = military_system.get_legion_by_number(3)

        leg3.mark_destroyed(7)
        leg1.mark_destroyed(5)
        leg2.mark_destroyed(6)

        destroyed = military_system.get_destroyed_legions()
        # 应返回按 destroyed_turn 升序的列表：5,6,7
        assert [l.number for l in destroyed] == [1, 2, 3]

    def test_recovery_not_yet(self, military_system):
        """测试恢复条件未满足时，不应恢复"""
        # 配置间隔为5，当前回合=10，摧毁于7 -> 10-7=3 <5，不应恢复
        legion = military_system.get_legion_by_number(1)
        legion.mark_destroyed(7)

        recovered = military_system._process_legion_recovery(10)  # current_turn=10
        assert recovered == []  # 无恢复
        assert legion.status == LegionStatus.DESTROYED  # 状态不变

    def test_recovery_just_meet(self, military_system):
        """测试刚好满足恢复条件时，恢复一个最老的"""
        # 间隔5，当前回合=12
        # 摧毁: 1号于5，2号于6，3号于7
        leg1 = military_system.get_legion_by_number(1)
        leg2 = military_system.get_legion_by_number(2)
        leg3 = military_system.get_legion_by_number(3)
        leg1.mark_destroyed(5)  # 12-5=7 >=5
        leg2.mark_destroyed(6)  # 12-6=6 >=5
        leg3.mark_destroyed(7)  # 12-7=5 >=5

        # 调用恢复，应该恢复最老的1号
        recovered = military_system._process_legion_recovery(12)
        assert recovered == [1]
        assert leg1.status == LegionStatus.DISBANDED
        assert leg1.destroyed_turn == 0
        # 2号和3号仍为 DESTROYED
        assert leg2.status == LegionStatus.DESTROYED
        assert leg3.status == LegionStatus.DESTROYED

        # 再次调用，应该恢复下一个最老的2号
        recovered = military_system._process_legion_recovery(12)  # 同一回合，但间隔已满足
        assert recovered == [2]
        assert leg2.status == LegionStatus.DISBANDED
        assert leg3.status == LegionStatus.DESTROYED

        # 第三次调用，恢复3号
        recovered = military_system._process_legion_recovery(12)
        assert recovered == [3]
        assert leg3.status == LegionStatus.DISBANDED

        # 第四次调用，无更多
        recovered = military_system._process_legion_recovery(12)
        assert recovered == []

    def test_recovery_interval_config(self, military_system, state):
        """测试从配置读取恢复间隔"""
        # 修改配置为3
        state.config._config["combat_rules"]["legion_recovery_interval"] = 3

        legion = military_system.get_legion_by_number(1)
        legion.mark_destroyed(10)

        # 当前回合12 -> 12-10=2 <3，不应恢复
        recovered = military_system._process_legion_recovery(12)
        assert recovered == []

        # 当前回合13 -> 13-10=3 >=3，应恢复
        recovered = military_system._process_legion_recovery(13)
        assert recovered == [1]
        assert legion.status == LegionStatus.DISBANDED

    def test_recovery_with_zero_interval(self, military_system, state):
        """测试间隔为0时，不应恢复（配置为0表示禁用恢复）"""
        state.config._config["combat_rules"]["legion_recovery_interval"] = 0

        legion = military_system.get_legion_by_number(1)
        legion.mark_destroyed(10)

        recovered = military_system._process_legion_recovery(100)  # 任意大回合
        assert recovered == []
        assert legion.status == LegionStatus.DESTROYED

    def test_apply_battle_results_disaster(self, military_system):
        # 模拟战争系统
        from unittest.mock import MagicMock
        mock_ws = MagicMock()
        mock_war = MagicMock()
        mock_war.id = "test_war"
        mock_ws.get_war_by_id.return_value = mock_war
        # 设置 state.get_war_system 返回模拟战争系统
        military_system.state.get_war_system = MagicMock(return_value=mock_ws)

        # 原有代码继续...
        legion = military_system.get_legion_by_number(1)
        success, msg = military_system.recruit_legion(1)
        assert success, f"征召失败: {msg}"
        assert legion.status == LegionStatus.ACTIVE

        # 指派到战争
        war_id = "test_war"
        assigned, msg = military_system.assign_to_war([1], war_id, 1001)
        assert assigned == 1, f"指派失败: {msg}"
        assert legion.war_id == war_id

        # 设置当前回合
        military_system.state.turn.turn_number = 15

        # 应用灾难结果
        military_system.apply_battle_results(war_id, victory=False, disaster=True)

        assert legion.status == LegionStatus.DESTROYED
        assert legion.destroyed_turn == 15
        assert legion.war_id is None

    