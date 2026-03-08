# src/tests/test_commands/test_phase_forum_fleet_contract.py
import pytest
from unittest.mock import Mock, patch
from src.ui.commands.phase_forum import ForumCommand
from src.core.game_state import GameState
from src.core.entities.war import War, WarStatus, WarType


@pytest.fixture
def state_with_naval_threat():
    state = Mock(spec=GameState)
    state.turn = Mock()
    state.turn.turn_number = 5
    state.turn.year = 280
    state.executed_phases = {"revenue"}
    state.is_phase_executed.side_effect = lambda p: p == "revenue"

    # 模拟 naval_system
    state.naval_system = Mock()

    # 模拟 war_system
    war_system = Mock()
    war1 = War(id="war1", name="Naval War 1", naval_required=True)
    war2 = War(id="war2", name="Land War", naval_required=False)
    war_system._threats = [war1, war2]
    state.get_war_system.return_value = war_system

    return state


def test_forum_generates_fleet_contracts(state_with_naval_threat):
    cmd = ForumCommand(state_with_naval_threat)
    # patch 掉所有可能引起问题的内部方法，只关注 generate_construction_contracts
    with patch.object(cmd, '_print_notice_board'), \
         patch.object(cmd, '_print_labor_market'), \
         patch.object(cmd, '_print_contract_auction'), \
         patch.object(cmd, '_print_land_deals'):
        with patch.object(state_with_naval_threat.naval_system, 'generate_construction_contracts') as mock_gen:
            cmd.execute([])
            mock_gen.assert_called_once_with(state_with_naval_threat.turn.turn_number)