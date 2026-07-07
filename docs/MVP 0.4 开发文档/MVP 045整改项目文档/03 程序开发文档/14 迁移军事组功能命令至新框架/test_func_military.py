# src/tests/test_commands/test_func_military.py
"""
军事功能命令单元测试
"""

import pytest
from unittest.mock import MagicMock, patch, call
import sys
import os
from io import StringIO

project_root = os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(__file__))))
if project_root not in sys.path:
    sys.path.insert(0, project_root)

from src.ui.commands.func_military import (
    WarsCommand, AssignCommand, LegionsCommand, RecruitCommand, DisbandCommand
)
from src.core.game_state import GameState
from src.core.systems.war_system import WarSystem
from src.core.systems.military_system import MilitarySystem
from src.core.entities.war import War
from src.core.entities.legion import Legion
from src.core.entities.figure import Figure


@pytest.fixture
def mock_state():
    state = MagicMock(spec=GameState)
    state.get_war_system.return_value = MagicMock(spec=WarSystem)
    state.get_military_system.return_value = MagicMock(spec=MilitarySystem)
    state.get_military_preparation_status.return_value = (True, [], [])
    state.treasury = 200
    return state


@pytest.fixture
def mock_war():
    war = MagicMock(spec=War)
    war.id = "war1"
    war.name = "Gallic War"
    war.get_total_strength.return_value = 8
    war.duration = 1
    war.commander_id = 1
    war.legions_assigned = 2
    war.fleets_assigned = 0
    war.naval_support_required = False
    war.penalties = {}
    war.commander_status = "active"
    return war


@pytest.fixture
def mock_legion():
    legion = MagicMock(spec=Legion)
    legion.number = 1
    legion.name = "Legio I"
    legion.is_veteran = False
    legion.war_id = None
    legion.get_combat_strength.return_value = 2
    legion.get_maintenance_cost.return_value = 2
    return legion


@pytest.fixture
def mock_figure():
    fig = MagicMock(spec=Figure)
    fig.id = 1
    fig.name = "Gaius Julius"
    fig.military = 5
    fig.faction_id = "senate"
    fig.is_dead = False
    fig.is_present = True
    return fig


# ========== WarsCommand ==========

def test_wars_no_system(mock_state):
    mock_state.get_war_system.return_value = None
    cmd = WarsCommand(mock_state)
    result = cmd.execute([])
    assert result is False


def test_wars_active(mock_state, mock_war):
    ws = mock_state.get_war_system.return_value
    ws.get_active_wars.return_value = [mock_war]
    ws._war_deck = []
    ws._war_discard = []
    ws.check_imminent_wars.return_value = []

    cmd = WarsCommand(mock_state)
    result = cmd.execute([])
    assert result is True


# ========== AssignCommand ==========

def test_assign_no_system(mock_state):
    mock_state.get_war_system.return_value = None
    cmd = AssignCommand(mock_state)
    result = cmd.execute([])
    assert result is False


@patch('builtins.input')
def test_assign_success(mock_input, mock_state, mock_war, mock_legion, mock_figure):
    ws = mock_state.get_war_system.return_value
    ms = mock_state.get_military_system.return_value
    ws.get_active_wars.return_value = [mock_war]

    # 确保战争没有指挥官
    mock_war.commander_id = None

    # 设置返回值
    ws.assign_commander.return_value = True
    ms.assign_to_war.return_value = (1, "Assigned 1 legion(s)")

    # 模拟候选人
    ms.get_unassigned_legions.return_value = [mock_legion]
    # 模拟派系成员作为指挥官候选人
    faction = MagicMock()
    faction.get_members.return_value = [mock_figure]
    mock_state.factions.values.return_value = [faction]

    # 模拟输入：选择战争1，指挥官1，军团1，不输入海军
    mock_input.side_effect = ["1", "1", "1", "0"]

    cmd = AssignCommand(mock_state)
    result = cmd.execute([])

    assert result is True
    ws.assign_commander.assert_called_once_with("war1", 1, 1, 0)
    ms.assign_to_war.assert_called_once_with([1], "war1", 1)


@patch('builtins.input')
def test_assign_cancel(mock_input, mock_state, mock_war):
    ws = mock_state.get_war_system.return_value
    ws.get_active_wars.return_value = [mock_war]

    mock_input.side_effect = ["1", "c"]  # 选择战争后取消
    cmd = AssignCommand(mock_state)
    result = cmd.execute([])
    assert result is False


# ========== LegionsCommand ==========

def test_legions_no_system(mock_state):
    mock_state.get_military_system.return_value = None
    cmd = LegionsCommand(mock_state)
    result = cmd.execute([])
    assert result is False


def test_legions_success(mock_state):
    ms = mock_state.get_military_system.return_value
    ms.get_military_summary.return_value = "Summary"
    ms.display_legion_status = MagicMock()

    cmd = LegionsCommand(mock_state)
    result = cmd.execute([])
    assert result is True
    ms.get_military_summary.assert_called_once()
    ms.display_legion_status.assert_called_once()


# ========== RecruitCommand ==========

def test_recruit_no_system(mock_state):
    mock_state.get_military_system.return_value = None
    cmd = RecruitCommand(mock_state)
    result = cmd.execute([])
    assert result is False


@patch('builtins.input')
def test_recruit_single_success(mock_input, mock_state, mock_legion):
    ms = mock_state.get_military_system.return_value
    ms.get_available_legions.return_value = [mock_legion]
    ms.recruit_legion.return_value = (True, "Legio I recruited")

    mock_input.side_effect = ["1", "1"]  # 选择单军团模式，选1号
    cmd = RecruitCommand(mock_state)
    result = cmd.execute([])
    assert result is True
    ms.recruit_legion.assert_called_once_with(1)


@patch('builtins.input')
def test_recruit_batch_success(mock_input, mock_state):
    ms = mock_state.get_military_system.return_value
    ms.get_available_legions.return_value = [MagicMock() for _ in range(3)]
    ms.recruit_multiple.return_value = [(1, True, "ok"), (2, True, "ok"), (3, True, "ok")]

    mock_input.side_effect = ["2", "3"]  # 批量模式，征召3个
    cmd = RecruitCommand(mock_state)
    result = cmd.execute([])
    assert result is True
    ms.recruit_multiple.assert_called_once_with(3)


# ========== DisbandCommand ==========

def test_disband_no_system(mock_state):
    mock_state.get_military_system.return_value = None
    cmd = DisbandCommand(mock_state)
    result = cmd.execute([])
    assert result is False


@patch('builtins.input')
def test_disband_single(mock_input, mock_state, mock_legion):
    ms = mock_state.get_military_system.return_value
    ms.get_active_legions.return_value = [mock_legion]
    ms.disband_legion.return_value = (True, "Legio I disbanded")

    mock_input.side_effect = ["1"]  # 选择第一个
    cmd = DisbandCommand(mock_state)
    result = cmd.execute([])
    assert result is True
    ms.disband_legion.assert_called_once_with(1)


@patch('builtins.input')
def test_disband_all(mock_input, mock_state):
    ms = mock_state.get_military_system.return_value
    legions = [MagicMock(number=i, name=f"Legio {i}", war_id=None) for i in range(1, 4)]
    ms.get_active_legions.return_value = legions
    ms.disband_legion.return_value = (True, "ok")

    mock_input.side_effect = ["all"]
    cmd = DisbandCommand(mock_state)
    result = cmd.execute([])
    assert result is True
    assert ms.disband_legion.call_count == 3
    ms.disband_legion.assert_has_calls([call(1), call(2), call(3)])