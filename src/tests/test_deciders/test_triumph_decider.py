"""
测试论坛命令中的凯旋处理 _process_triumphs
"""

import pytest
from unittest.mock import MagicMock, patch
from src.ui.commands.phase_forum import ForumCommand
from src.core.entities.war import War, WarStatus
from src.core.entities.figure import Figure
from src.core.game_state import GameState
from src.core.systems.war_system import WarSystem


@pytest.fixture
def mock_state():
    state = MagicMock(spec=GameState)
    state.get_war_system.return_value = MagicMock(spec=WarSystem)
    state.config.get.return_value = 5  # triumph_veteran_duration 默认5
    return state


@pytest.fixture
def mock_war():
    war = MagicMock(spec=War)
    war.id = "test_war"
    war.name = "测试战争"
    war.status = WarStatus.RESOLVED
    war.soldier_share = 50
    war.commander_id = 101
    return war


@pytest.fixture
def mock_commander():
    fig = MagicMock(spec=Figure)
    fig.id = 101
    fig.name = "凯撒"
    fig.is_dead = False
    fig.add_temp_influence_task = MagicMock()
    return fig


class TestForumTriumph:
    def test_triumph_approved(self, mock_state, mock_war, mock_commander):
        """测试凯旋批准：士兵份额转为临时影响力任务"""
        ws = mock_state.get_war_system.return_value
        ws._war_discard = [mock_war]
        mock_state.get_member.return_value = mock_commander

        mock_decider = MagicMock()
        mock_decider.decide_triumph.return_value = True
        cmd = ForumCommand(mock_state, triumph_decider=mock_decider)

        cmd._process_triumphs()

        mock_decider.decide_triumph.assert_called_once_with(mock_war, mock_commander, mock_state)
        mock_commander.add_temp_influence_task.assert_called_once_with(10, 5)
        mock_war.set_soldier_share.assert_called_once_with(0)

    def test_triumph_rejected(self, mock_state, mock_war, mock_commander):
        """测试凯旋否决：士兵份额消失"""
        ws = mock_state.get_war_system.return_value
        ws._war_discard = [mock_war]
        mock_state.get_member.return_value = mock_commander

        mock_decider = MagicMock()
        mock_decider.decide_triumph.return_value = False
        cmd = ForumCommand(mock_state, triumph_decider=mock_decider)

        cmd._process_triumphs()

        mock_decider.decide_triumph.assert_called_once()
        mock_commander.add_temp_influence_task.assert_not_called()
        mock_war.set_soldier_share.assert_called_once_with(0)

    def test_commander_dead(self, mock_state, mock_war, mock_commander):
        """测试指挥官已死亡：士兵份额消失，不进行凯旋"""
        mock_commander.is_dead = True
        ws = mock_state.get_war_system.return_value
        ws._war_discard = [mock_war]
        mock_state.get_member.return_value = mock_commander

        mock_decider = MagicMock()
        cmd = ForumCommand(mock_state, triumph_decider=mock_decider)

        cmd._process_triumphs()

        mock_decider.decide_triumph.assert_not_called()
        mock_war.set_soldier_share.assert_called_once_with(0)

    def test_multiple_wars(self, mock_state, mock_war, mock_commander):
        """测试多个待凯旋战争"""
        # 确保 mock_war 有必要的属性
        mock_war.triumph_commander_id = None
        mock_war.set_triumph_approved = MagicMock()

        war2 = MagicMock(spec=War)
        war2.id = "war2"
        war2.name = "第二次战争"
        war2.status = WarStatus.RESOLVED
        war2.soldier_share = 30
        war2.commander_id = 102
        war2.triumph_commander_id = None
        war2.set_triumph_approved = MagicMock()

        commander2 = MagicMock(spec=Figure)
        commander2.id = 102
        commander2.name = "庞培"
        commander2.is_dead = False
        commander2.add_temp_influence_task = MagicMock()

        ws = mock_state.get_war_system.return_value
        ws._war_discard = [mock_war, war2]

        def get_member_side_effect(fid):
            return mock_commander if fid == 101 else commander2

        mock_state.get_member.side_effect = get_member_side_effect

        mock_decider = MagicMock()
        mock_decider.decide_triumph.return_value = True
        cmd = ForumCommand(mock_state, triumph_decider=mock_decider)

        cmd._process_triumphs()

        assert mock_decider.decide_triumph.call_count == 2
        mock_commander.add_temp_influence_task.assert_called_once_with(10, 5)
        commander2.add_temp_influence_task.assert_called_once_with(6, 5)
        mock_war.set_soldier_share.assert_called_once_with(0)
        war2.set_soldier_share.assert_called_once_with(0)