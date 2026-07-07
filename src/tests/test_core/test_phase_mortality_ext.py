"""
测试天命阶段死亡处理及合同终止联动。
"""

import pytest
from src.core.game_state import GameState
from src.core.entities.entities import GameTurn
from src.core.entities.province import Province
from src.core.entities.contract import Contract, ContractType, ContractStatus
from src.core.entities.figure import Figure
from src.ui.commands.phase_mortality import MortalityCommand


@pytest.fixture
def state():
    config = {
        "mortality_rules": {
            "event_deck": [
                {"name": "死神来了", "effect": "death"}
            ],
            "event_draw_count": 1,
            "death_count": 1
        }
    }
    state = GameState.create_for_testing(config)
    return state


@pytest.fixture
def province(state):
    p = Province(1, "测试行省", 1000)
    state.add_province(p)
    return p


@pytest.fixture
def knight_with_contract(state, province):
    fig = Figure(id=301, name="骑士", faction_id="f1")
    fig.wealth = 200
    fig._land_private = 50
    state.add_member(fig)

    # 创建一个包税合同并手动模拟中标状态
    contract = state.create_contract(ContractType.TAX_FARMING, province.province_id, 100, 5)
    contract._winning_bid = {"bidder_id": fig.id, "amount": 100}
    contract._tax_rate = 0.1
    contract._annual_profit = 20
    contract.status = ContractStatus.ACTIVE
    contract.remaining_years = 5
    fig.add_contract(contract.id)
    province.bind_tax_contract(contract.id)

    return fig, contract


class TestMortalityPhaseExt:
    """天命阶段死亡及合同终止测试"""

    def test_death_event_terminates_contract(self, state, knight_with_contract):
        """死亡事件触发，中标者死亡，合同应终止"""
        knight, contract = knight_with_contract
        assert contract.status == ContractStatus.ACTIVE
        assert knight.is_dead is False
        province = state.get_province(contract.province_id)
        assert province.tax_contract_id == contract.id

        cmd = MortalityCommand(state)
        cmd._handle_death_event()

        assert knight.is_dead is True
        # 合同应变为 EXPIRED
        assert contract.status == ContractStatus.EXPIRED
        # 行省解绑
        assert province.tax_contract_id is None

    def test_mortality_command_execute(self, state):
        """测试 MortalityCommand.execute 能正常运行"""
        # 手动设置回合，确保 fixture 不依赖外部设置
        state.turn = GameTurn(turn_number=1, year=-264)
        cmd = MortalityCommand(state)
        result = cmd.execute([])
        assert result is True
        assert state.is_phase_executed("mortality") is True