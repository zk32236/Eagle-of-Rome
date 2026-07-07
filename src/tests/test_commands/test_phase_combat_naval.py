# src/tests/test_commands/test_phase_combat_naval.py
import pytest
from unittest.mock import Mock, patch
from src.ui.commands.phase_combat import CombatCommand
from src.core.game_state import GameState
from src.core.entities.war import War, WarStatus
from src.core.entities.legion import Legion


@pytest.fixture
def state_with_naval_war():
    state = Mock(spec=GameState)
    state.turn = Mock()
    state.turn.turn_number = 10
    state.turn.year = 280
    state.turn.leader_ids = []  # 设置为空列表
    state.executed_phases = {"senate"}
    state.is_phase_executed.side_effect = lambda p: p == "senate"

    def config_get(key, default=None):
        if key == "testing.force_battle_result":
            return "VICTORY"  # 强制战斗结果为 VICTORY
        return default
    state.config.get.side_effect = config_get

    ms = Mock()
    legion1 = Mock(spec=Legion)
    legion1.get_combat_strength.return_value = 2
    legion2 = Mock(spec=Legion)
    legion2.get_combat_strength.return_value = 2
    ms.get_legions_for_battle.return_value = [legion1, legion2]
    state.get_military_system.return_value = ms

    state.naval_system = Mock()

    war_system = Mock()
    war_system.get_truce_wars_with_approved_treaty.return_value = []
    war_system.escalate_threats.return_value = []
    war_system.check_triggers.return_value = None

    war = War(
        id="war1",
        name="Naval War",
        naval_required=True,
        disaster_numbers=[99],   # 避免意外触发灾难
        standoff_numbers=[99]    # 避免意外触发僵持
    )
    war.status = WarStatus.ACTIVE
    war.commander_id = 101
    war._assigned_fleet_ids = [1, 2]
    war_system.get_active_wars.return_value = [war]
    state.get_war_system.return_value = war_system

    commander = Mock(name="Commander")
    commander.martial = 4
    commander.is_dead = False
    commander.id = 101
    commander.name = "Test Commander"
    commander.influence = 0          # ✅ 设置整数属性，使 += 操作可行
    commander.is_faction_leader = False  # ✅ 避免灾难分支出错
    state.get_member.return_value = commander

    return state


def test_combat_with_naval_battle_success(state_with_naval_war):
    cmd = CombatCommand(state_with_naval_war)
    state_with_naval_war.naval_system.resolve_naval_battle.return_value = ("VICTORY", {"roman_losses": 0})

    result = cmd.execute([])

    assert result is True
    state_with_naval_war.naval_system.resolve_naval_battle.assert_called_once()


def test_combat_with_naval_battle_defeat(state_with_naval_war):
    cmd = CombatCommand(state_with_naval_war)
    state_with_naval_war.naval_system.resolve_naval_battle.return_value = ("DEFEAT", {"roman_losses": 1})

    result = cmd.execute([])

    assert result is True
    state_with_naval_war.naval_system.resolve_naval_battle.assert_called_once()