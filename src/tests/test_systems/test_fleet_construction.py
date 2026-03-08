# src/tests/test_systems/test_fleet_construction.py
import pytest
from unittest.mock import Mock, patch
from src.core.systems.naval_system import NavalSystem
from src.core.game_state import GameState
from src.core.entities.contract import Contract, ContractType, ContractStatus
from src.core.systems.war_system import WarSystem
from src.core.entities.war import War, WarStatus


def test_fleet_construction_lifecycle():
    """测试舰队从合同生成到建造完成的完整流程"""
    state = GameState.create_for_testing({
        "economic_rules": {
            "fleet_types": {
                "trireme": {"build_cost": 40, "build_time": 2, "maintenance_cost": 4, "strength_base": 3}
            },
            "default_fleet_type": "trireme"
        }
    })

    # 手动创建战争系统并赋值
    state._war_system = WarSystem(state)
    war = War(id="war1", name="Test Naval War", naval_required=True)
    war.status = WarStatus.ACTIVE  # 设为活跃，以便后续自动指派
    state.get_war_system()._threats = [war]  # 保持威胁列表，但实际我们会模拟 get_war_by_id

    # 设置回合
    state.turn = Mock()
    state.turn.turn_number = 1

    ns = NavalSystem(state)

    # 回合1：生成合同
    contracts = ns.generate_construction_contracts(current_turn=1)
    assert len(contracts) == 1
    contract = contracts[0]
    contract._target_war_id = war.id

    # 模拟元老院通过预算、竞标
    contract.status = ContractStatus.BUDGETED
    bid = {"bidder_id": 101, "amount": 40, "r": 0}
    contract._bids = [bid]

    ns.on_contract_awarded(contract, winner_id=101)

    # 检查舰队创建
    fleets = ns.get_all_fleets()
    assert len(fleets) == 1
    fleet = fleets[0]
    assert fleet.status.value == "building"
    assert fleet.build_start_turn == 1
    assert fleet.build_end_turn == 3
    assert fleet.target_war_id == war.id

    # 回合2：建造中
    completed = ns.process_fleet_construction(current_turn=2)
    assert completed == []
    assert fleet.status.value == "building"

    # 回合3：建造完成，自动指派
    # 模拟战争系统返回活跃战争
    war_system_mock = Mock()
    war_system_mock.get_war_by_id.return_value = war
    state.get_war_system = Mock(return_value=war_system_mock)

    # 模拟 assign_fleet_to_war 方法，验证是否被调用
    with patch.object(ns, 'assign_fleet_to_war') as mock_assign:
        completed = ns.process_fleet_construction(current_turn=3)
        assert completed == [1]
        assert fleet.status.value == "available"
        # 验证自动指派被调用
        mock_assign.assert_called_once_with(1, war.id, "naval", commander_id=None)