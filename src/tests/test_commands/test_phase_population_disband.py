"""
测试人口阶段中的军团解散和凯旋式处理
"""

import pytest
from unittest.mock import MagicMock
from src.ui.commands.phase_population import PopulationCommand
from src.core.entities.war import War, WarStatus
from src.core.entities.figure import Figure
from src.core.game_state import GameState
from src.core.systems.war_system import WarSystem
from src.core.systems.military_system import MilitarySystem


@pytest.fixture
def mock_state():
    state = MagicMock(spec=GameState)
    state.get_war_system.return_value = MagicMock(spec=WarSystem)
    state.get_military_system.return_value = MagicMock(spec=MilitarySystem)
    return state


@pytest.fixture
def mock_war():
    war = MagicMock(spec=War)
    war.id = "test_war"
    war.name = "测试战争"
    war.status = WarStatus.RESOLVED
    war.soldier_share = 50
    war.commander_id = 101
    war.triumph_approved = True
    war.legion_numbers = [1, 2, 3]
    return war


@pytest.fixture
def mock_commander():
    fig = MagicMock(spec=Figure)
    fig.id = 101
    fig.name = "凯撒"
    fig.is_dead = False
    return fig


class TestPopulationDisband:
    def test_disband_with_triumph(self, mock_state, mock_war, mock_commander):
        """测试凯旋已批准的战争：显示凯旋式并解散军团"""
        ws = mock_state.get_war_system.return_value
        ws._war_discard = [mock_war]
        ms = mock_state.get_military_system.return_value
        ms.disband_legions_for_war.return_value = (3, [])
        mock_state.get_member.return_value = mock_commander

        cmd = PopulationCommand(mock_state)
        cmd._process_legion_disbandment_and_triumphs()

        ms.disband_legions_for_war.assert_called_once_with([1, 2, 3])

    def test_disband_without_triumph(self, mock_state, mock_war):
        """测试凯旋未批准的战争：只解散军团，不显示凯旋式"""
        mock_war.triumph_approved = False
        ws = mock_state.get_war_system.return_value
        ws._war_discard = [mock_war]
        ms = mock_state.get_military_system.return_value
        ms.disband_legions_for_war.return_value = (3, [])

        cmd = PopulationCommand(mock_state)
        cmd._process_legion_disbandment_and_triumphs()

        ms.disband_legions_for_war.assert_called_once_with([1, 2, 3])

    def test_commander_dead(self, mock_state, mock_war, mock_commander):
        """测试指挥官已死亡：不显示凯旋式，但军团仍解散"""
        mock_commander.is_dead = True
        ws = mock_state.get_war_system.return_value
        ws._war_discard = [mock_war]
        ms = mock_state.get_military_system.return_value
        ms.disband_legions_for_war.return_value = (3, [])
        mock_state.get_member.return_value = mock_commander

        cmd = PopulationCommand(mock_state)
        cmd._process_legion_disbandment_and_triumphs()

        ms.disband_legions_for_war.assert_called_once_with([1, 2, 3])

    def test_no_legions(self, mock_state, mock_war):
        """测试战争没有军团记录，不应调用解散"""
        mock_war.legion_numbers = []
        ws = mock_state.get_war_system.return_value
        ws._war_discard = [mock_war]
        ms = mock_state.get_military_system.return_value

        cmd = PopulationCommand(mock_state)
        cmd._process_legion_disbandment_and_triumphs()

        ms.disband_legions_for_war.assert_not_called()

    def test_multiple_wars(self, mock_state, mock_war):
        """测试多个战争"""
        war2 = MagicMock(spec=War)
        war2.id = "war2"
        war2.name = "第二次战争"  # 必须提供 name
        war2.status = WarStatus.RESOLVED
        war2.triumph_approved = False
        war2.legion_numbers = [4, 5]

        ws = mock_state.get_war_system.return_value
        ws._war_discard = [mock_war, war2]
        ms = mock_state.get_military_system.return_value
        ms.disband_legions_for_war.side_effect = [(3, []), (2, [])]

        cmd = PopulationCommand(mock_state)
        cmd._process_legion_disbandment_and_triumphs()

        # 验证两次调用，参数分别为 [1,2,3] 和 [4,5]
        assert ms.disband_legions_for_war.call_count == 2
        ms.disband_legions_for_war.assert_any_call([1, 2, 3])
        ms.disband_legions_for_war.assert_any_call([4, 5])