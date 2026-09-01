# src/tests/test_commands/test_phase_combat_naval.py
"""
Naval combat tests — S1 适配版。
CombatCommand 已委托给 combat_api.auto_resolve_combat 共享用例。
"""
import pytest
from unittest.mock import Mock, patch, MagicMock
from src.ui.commands.phase_combat import CombatCommand
from src.core.game_state import GameState
from src.core.entities.war import War, WarStatus, WarType
from src.core.entities.legion import Legion, LegionStatus
from src.core.entities.figure import Figure
from src.core.entities.entities import Faction, GameTurn
from src.core.entities.player import Player, PlayerType
from src.core.systems.war_system import WarSystem
from src.core.systems.military_system import MilitarySystem


@pytest.fixture
def state_with_naval_combat_ready():
    """创建可直接执行 auto_resolve_combat 的 GameState（含海军战争）"""
    state = GameState.create_for_testing({})
    state.turn = GameTurn(turn_number=10, year=-280)
    state.mark_phase_executed("mortality")
    state.mark_phase_executed("revenue")
    state.mark_phase_executed("forum")
    state.mark_phase_executed("population")
    state.mark_phase_executed("senate")

    faction = Faction(id="senate", name="Senate", treasury=50)
    state.add_faction(faction)

    player = Player(player_id="player_opt", faction_id="senate",
                    player_type=PlayerType.HUMAN)
    state.add_player(player)
    state.set_current_player("player_opt")

    commander = Figure(id=101, name="Test Commander", faction_id="senate", age=40)
    commander.martial = 4
    commander.influence = 10
    commander.is_absent = True
    state.add_member(commander)
    faction.member_ids.append(101)

    state._war_system = WarSystem(state)
    state._military_system = MilitarySystem(state)
    state._naval_system = MagicMock()

    war = War(
        id="war1", name="Naval War", war_type=WarType.FOREIGN,
        strength=8, threat_level=3, rewards={"treasury": 100},
        naval_required=True, disaster_numbers=[99], standoff_numbers=[99],
    )
    war.commander_id = 101
    war.legions_assigned = 2
    war.status = WarStatus.ACTIVE
    war._assigned_fleet_ids = [1, 2]
    state._war_system._active_wars.append(war)

    for num in [1, 2]:
        legion = Legion(number=num, name=f"Legio {num}")
        legion.status = LegionStatus.AVAILABLE
        legion.assign_to_war(war.id, commander.id)
        state._military_system._legions.append(legion)

    return state


def test_combat_with_naval_battle_success(state_with_naval_combat_ready):
    """海军战斗胜利 → execute 成功"""
    state = state_with_naval_combat_ready
    # Mock naval system to succeed
    state._naval_system.resolve_naval_battle.return_value = ("VICTORY", {"roman_losses": 0})

    cmd = CombatCommand(state)

    f = pytest.StashKey()
    with patch('sys.stdout'):
        result = cmd.execute([])

    assert result is True


def test_combat_with_naval_battle_defeat(state_with_naval_combat_ready):
    """海军战斗失败（DEFEAT）→ 阻断陆战 → 战争继续 + 不阻塞 advance（G1-09/R-05）"""
    state = state_with_naval_combat_ready
    # Naval defeat
    state._naval_system.resolve_naval_battle.return_value = ("DEFEAT", {"roman_losses": 1})
    war = state._war_system.get_war_by_id("war1")

    cmd = CombatCommand(state)

    with patch('sys.stdout'):
        result = cmd.execute([])

    assert result is True
    # G1-15：军团保持 ACTIVE + assigned（零陆战伤亡）
    ms = state._military_system
    attached = ms.get_legions_for_battle(war.id)
    assert len(attached) == 2
    assert all(l.status.value == "active" for l in attached)
    assert all(l.war_id == war.id for l in attached)
    # 战争继续（未 resolve/discard），制海权未获控
    assert war.status == WarStatus.ACTIVE
    assert war.sea_control_acquired is False
    assert war not in state._war_system._war_discard


def test_combat_with_naval_battle_stalemate_blocks_land_battle(state_with_naval_combat_ready):
    """海军 STALEMATE → 阻断陆战（R-05，G1-09：legacy 曾放行）"""
    state = state_with_naval_combat_ready
    state._naval_system.resolve_naval_battle.return_value = ("STALEMATE", {"roman_losses": 0})
    war = state._war_system.get_war_by_id("war1")

    cmd = CombatCommand(state)

    with patch('sys.stdout'):
        result = cmd.execute([])

    assert result is True
    # STALEMATE 阻断：战争继续 ACTIVE + 军团保持 + 0 舰队损失
    assert war.status == WarStatus.ACTIVE
    ms = state._military_system
    attached = ms.get_legions_for_battle(war.id)
    assert len(attached) == 2
    assert all(l.status.value == "active" for l in attached)
    assert war.sea_control_acquired is False
    assert state.is_phase_executed("combat")
