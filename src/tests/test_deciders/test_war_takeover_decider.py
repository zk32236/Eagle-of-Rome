"""
测试战争接管决策器 AutoWarTakeoverDecider
"""

import pytest
from unittest.mock import MagicMock
from src.core.deciders.impl.auto_war_takeover_decider import AutoWarTakeoverDecider
from src.core.entities.war import War
from src.core.entities.figure import Figure


class TestAutoWarTakeoverDecider:
    def test_takeover_by_chance(self):
        state = MagicMock()
        war = MagicMock(spec=War)
        new_consul = MagicMock(spec=Figure)
        new_consul.id = 1
        old_commander = MagicMock(spec=Figure)
        old_commander.id = 2

        # 概率 1.0
        state.config.get.return_value = 1.0
        decider = AutoWarTakeoverDecider()
        assert decider.decide_takeover(war, new_consul, old_commander, state) is True

        # 概率 0.0
        state.config.get.return_value = 0.0
        assert decider.decide_takeover(war, new_consul, old_commander, state) is False

        # 概率 0.5，随机抽样
        state.config.get.return_value = 0.5
        results = [decider.decide_takeover(war, new_consul, old_commander, state) for _ in range(100)]
        true_count = sum(results)
        assert 30 <= true_count <= 70

    def test_config_key(self):
        state = MagicMock()
        war = MagicMock(spec=War)
        new_consul = MagicMock(spec=Figure)
        new_consul.id = 1
        old_commander = MagicMock(spec=Figure)
        old_commander.id = 2

        state.config.get.return_value = 0.5
        decider = AutoWarTakeoverDecider()
        decider.decide_takeover(war, new_consul, old_commander, state)

        state.config.get.assert_called_with("combat_rules.war_takeover_chance", 1.0)

    def test_same_commander_no_takeover(self):
        """测试新旧指挥官为同一人时，不应接管"""
        state = MagicMock()
        war = MagicMock(spec=War)
        new_consul = MagicMock(spec=Figure)
        new_consul.id = 1
        old_commander = MagicMock(spec=Figure)
        old_commander.id = 1  # 相同ID

        # 即使概率为1，也应返回False
        state.config.get.return_value = 1.0
        decider = AutoWarTakeoverDecider()
        assert decider.decide_takeover(war, new_consul, old_commander, state) is False