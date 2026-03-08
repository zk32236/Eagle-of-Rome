# src/tests/test_systems/test_naval_system.py
import pytest
from unittest.mock import Mock, patch
from src.core.systems.naval_system import NavalSystem
from src.core.entities.fleet import Fleet, FleetStatus
from src.core.entities.war import War, WarStatus, WarType
from src.core.entities.contract import Contract, ContractType, ContractStatus
from src.core.game_state import GameState


@pytest.fixture
def mock_state():
    state = Mock(spec=GameState)
    state.turn = Mock()
    state.turn.turn_number = 10
    state.config.get.side_effect = lambda key, default=None: {
        "economic_rules.fleet_types": {
            "trireme": {"build_cost": 40, "build_time": 1, "maintenance_cost": 4, "strength_base": 3},
            "quadrireme": {"build_cost": 60, "build_time": 2, "maintenance_cost": 6, "strength_base": 4},
        },
        "economic_rules.default_fleet_type": "trireme"
    }.get(key, default)
    # 确保 get_all_contracts 返回可迭代对象
    state.get_all_contracts.return_value = []
    return state


@pytest.fixture
def naval_system(mock_state):
    return NavalSystem(mock_state)


class TestNavalSystem:
    def test_generate_construction_contracts_with_naval_threat(self, naval_system, mock_state):
        # 创建需要海战的威胁战争
        war = War(id="war1", name="Naval War", naval_required=True)
        war.status = WarStatus.THREAT
        war_system = Mock()
        war_system._threats = [war]
        mock_state.get_war_system.return_value = war_system
        # 设置 get_all_contracts 返回空列表（已在fixture中设置）
        mock_state.create_contract = Mock(return_value=Contract(
            id=1, contract_type=ContractType.PUBLIC_WORKS,
            _province_id=0, _create_turn=10, base_cost=40
        ))

        contracts = naval_system.generate_construction_contracts(10)
        assert len(contracts) == 1
        contract = contracts[0]
        assert contract._is_fleet_construction is True
        assert contract._target_war_id == "war1"
        assert contract._fleet_type == "trireme"
        assert contract._build_time == 1

    def test_generate_construction_contracts_no_threat(self, naval_system, mock_state):
        war_system = Mock()
        war_system._threats = []
        mock_state.get_war_system.return_value = war_system
        contracts = naval_system.generate_construction_contracts(10)
        assert contracts == []

    def test_on_contract_awarded_creates_fleet(self, naval_system, mock_state):
        contract = Contract(
            id=5, contract_type=ContractType.PUBLIC_WORKS,
            _province_id=0, _create_turn=10, base_cost=40
        )
        contract._is_fleet_construction = True
        contract._target_war_id = "war1"
        contract._fleet_type = "trireme"
        contract._build_time = 1
        naval_system._next_fleet_number = 1

        naval_system.on_contract_awarded(contract, winner_id=101)
        assert 1 in naval_system._fleets
        fleet = naval_system._fleets[1]
        assert fleet.fleet_type == "trireme"
        assert fleet.status == FleetStatus.BUILDING
        assert fleet.build_start_turn == 10
        assert fleet.build_end_turn == 11
        assert fleet.contract_id == 5
        assert naval_system._construction_contracts[5] == 1

    def test_process_fleet_construction_completes(self, naval_system):
        fleet = Fleet(number=1, fleet_type="trireme")
        fleet.start_building(start_turn=10, contract_id=5, build_time=2)
        fleet._build_end_turn = 12  # 应于回合12完成
        naval_system._fleets[1] = fleet

        completed = naval_system.process_fleet_construction(current_turn=11)
        assert completed == []
        assert fleet.status == FleetStatus.BUILDING

        completed = naval_system.process_fleet_construction(current_turn=12)
        assert completed == [1]
        assert fleet.status == FleetStatus.AVAILABLE
        assert fleet.build_start_turn is None
        assert fleet.build_end_turn is None

    def test_assign_fleet_to_war(self, naval_system, mock_state):
        fleet = Fleet(number=2)
        fleet._status = FleetStatus.AVAILABLE
        naval_system._fleets[2] = fleet

        war = War(id="war2", name="War2", naval_required=True)
        war_system = Mock()
        war_system.get_war_by_id.return_value = war
        mock_state.get_war_system.return_value = war_system

        result = naval_system.assign_fleet_to_war(2, "war2", "naval", commander_id=101)
        assert result is True
        assert fleet.assigned_war_id == "war2"
        assert fleet.status == FleetStatus.ON_MISSION
        assert war.assigned_fleet_ids == [2]

    def test_resolve_naval_battle_triumph(self, naval_system, mock_state):
        fleet1 = Fleet(number=1)
        fleet1._strength_base = 3
        fleet1._experience = 1
        fleet1._status = FleetStatus.AVAILABLE  # 关键修复：设为可用
        fleet2 = Fleet(number=2)
        fleet2._strength_base = 3
        fleet2._experience = 0
        fleet2._status = FleetStatus.AVAILABLE  # 关键修复：设为可用
        naval_system._fleets = {1: fleet1, 2: fleet2}
        war = War(id="war3", name="Naval Battle", naval_required=True)
        war._assigned_fleet_ids = [1, 2]
        war._enemy_naval_current = 5
        with patch('src.core.systems.naval_system.random.randint', return_value=12):
            result, losses = naval_system.resolve_naval_battle(war)
        assert result == "TRIUMPH"
        assert losses["roman_losses"] == 0

    def test_resolve_naval_battle_defeat(self, naval_system, mock_state):
        fleet1 = Fleet(number=1)
        fleet1._strength_base = 3
        fleet1._status = FleetStatus.AVAILABLE
        fleet2 = Fleet(number=2)
        fleet2._strength_base = 3
        fleet2._status = FleetStatus.AVAILABLE
        naval_system._fleets = {1: fleet1, 2: fleet2}
        war = War(id="war4", name="Naval Defeat", naval_required=True)
        war._assigned_fleet_ids = [1, 2]
        war._enemy_naval_current = 20
        # 使用骰子10，避免 standoff 和 disaster 干扰
        with patch('src.core.systems.naval_system.random.randint', return_value=10):
            result, losses = naval_system.resolve_naval_battle(war)
        assert result == "DEFEAT"
        # 损失一半：2艘中的1艘
        assert losses["roman_losses"] == 1

    def test_calculate_maintenance(self, naval_system):
        fleet1 = Fleet(number=1, fleet_type="trireme")
        fleet1._status = FleetStatus.AVAILABLE
        fleet2 = Fleet(number=2, fleet_type="quadrireme")
        fleet2._status = FleetStatus.ON_MISSION
        fleet3 = Fleet(number=3, fleet_type="trireme")
        fleet3._status = FleetStatus.BUILDING
        naval_system._fleets = {1: fleet1, 2: fleet2, 3: fleet3}
        # 配置维护费已在 mock_state 的 config.get 中设置
        total = naval_system.calculate_maintenance()
        assert total == 4 + 6  # trireme 4, quadrireme 6