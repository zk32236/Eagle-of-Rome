# src/tests/test_commands/test_rebellion.py

import pytest
from unittest.mock import Mock
from src.core.game_state import GameState
from src.core.entities.province import Province
from src.core.systems.war_system import WarSystem
from src.core.entities.war import WarStatus
from src.ui.commands.phase_forum import ForumCommand
from src.core.entities.figure import Figure


def test_rebellion_trigger():
    """测试民怨达到3时触发起义"""
    state = GameState.create_for_testing({})
    state._war_system = WarSystem(state)

    province = Province(province_id=1, name="Test", total_land=1000)
    province.set_grievance(3)
    state.add_province(province)
    state.turn = Mock()
    state.turn.turn_number = 10
    state.turn.year = -280
    state.mark_phase_executed("revenue")
    state.is_phase_executed = lambda p: p == "revenue"

    cmd = ForumCommand(state)
    cmd._update_civil_unrest()

    war_system = state.get_war_system()
    active_wars = war_system.get_active_wars()
    assert len(active_wars) == 1
    war = active_wars[0]
    assert war.rebellion_province_id == 1
    assert province.event_flags.get("rebellion_active") is True


def test_rebellion_victory():
    """测试起义战争胜利后的效果"""
    state = GameState.create_for_testing({})
    state._war_system = WarSystem(state)
    state.turn = Mock()
    state.turn.turn_number = 10  # 必须设置 turn_number
    state.turn.year = -280  # 可选

    province = Province(province_id=1, name="Test", total_land=1000)
    province.set_grievance(3)
    province.set_event_flag("rebellion_active", True)
    state.add_province(province)

    war_system = state.get_war_system()
    war = war_system.create_rebellion_war(province)
    assert war is not None, "create_rebellion_war returned None"
    war.status = WarStatus.ACTIVE
    war._commander_id = 101
    war_system._active_wars.append(war)

    commander = Figure(id=101, name="General")
    commander.family_prestige = 0
    state.add_member(commander)

    result = war_system.resolve_war(war.id, victory=True)

    assert province.grievance == 0
    assert province.event_flags.get("rebellion_active") is None
    assert commander.family_prestige == 1
    assert result.get("rewards") == {}
    assert war not in war_system.get_active_wars()


def test_rebellion_defeat():
    """测试起义战争失败（暂不实现特殊处理）"""
    state = GameState.create_for_testing({})
    state._war_system = WarSystem(state)
    state.turn = Mock()
    state.turn.turn_number = 10  # 必须设置
    state.turn.year = -280

    province = Province(province_id=1, name="Test", total_land=1000)
    province.set_grievance(3)
    province.set_event_flag("rebellion_active", True)
    state.add_province(province)

    war_system = state.get_war_system()
    war = war_system.create_rebellion_war(province)
    assert war is not None, "create_rebellion_war returned None"
    war.status = WarStatus.ACTIVE
    war._commander_id = 101
    war_system._active_wars.append(war)

    commander = Figure(id=101, name="General")
    commander.family_prestige = 0
    state.add_member(commander)

    result = war_system.resolve_war(war.id, victory=False)

    assert province.grievance == 3
    assert province.event_flags.get("rebellion_active") is True
    assert war.status == WarStatus.DEFEATED