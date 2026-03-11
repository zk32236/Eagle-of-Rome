# src/tests/test_systems/test_naval_system.py
import pytest
from unittest.mock import Mock, patch
from src.core.systems.naval_system import NavalSystem
from src.core.entities.fleet import Fleet, FleetStatus
from src.core.entities.war import War, WarStatus, WarType
from src.core.entities.contract import Contract, ContractType, ContractStatus
from src.core.game_state import GameState
from src.core.deciders.fleet_disband_decider import FleetDisbandDecider
from src.core.deciders.impl.auto_fleet_disband_decider import AutoFleetDisbandDecider

class TestFleetDisbandDecider:
    """测试自动舰队解散决策器"""

    @pytest.fixture
    def state_mock(self):
        state = Mock()
        war_system = Mock()
        state.get_war_system.return_value = war_system
        return state

    @pytest.fixture
    def decider(self):
        return AutoFleetDisbandDecider()

    def create_fleet(self, status=FleetStatus.AVAILABLE, is_building=False):
        fleet = Mock(spec=Fleet)
        fleet.status = status
        fleet.is_building = is_building
        return fleet

    def test_should_disband_fleet_when_no_naval_wars(self, state_mock, decider):
        """当没有任何需要海战的战争时，应解散可用舰队"""
        war_system = state_mock.get_war_system.return_value
        war_system.get_active_wars.return_value = []
        war_system._threats = []
        fleet = self.create_fleet(FleetStatus.AVAILABLE, False)
        assert decider.should_disband_fleet(fleet, state_mock) is True

    def test_should_not_disband_fleet_when_active_naval_war_exists(self, state_mock, decider):
        """当存在需要海战的活跃战争时，不应解散舰队"""
        war_system = state_mock.get_war_system.return_value
        active_war = Mock(spec=War)
        active_war.naval_required = True
        war_system.get_active_wars.return_value = [active_war]
        war_system._threats = []
        fleet = self.create_fleet(FleetStatus.AVAILABLE, False)
        assert decider.should_disband_fleet(fleet, state_mock) is False

    def test_should_not_disband_fleet_when_threat_naval_war_exists(self, state_mock, decider):
        """当存在需要海战的威胁战争时，不应解散舰队"""
        war_system = state_mock.get_war_system.return_value
        war_system.get_active_wars.return_value = []
        threat_war = Mock(spec=War)
        threat_war.naval_required = True
        war_system._threats = [threat_war]
        fleet = self.create_fleet(FleetStatus.AVAILABLE, False)
        assert decider.should_disband_fleet(fleet, state_mock) is False

    def test_should_not_disband_fleet_when_active_war_no_naval(self, state_mock, decider):
        """活跃战争存在但不需要海战，且无其他战争时，应解散"""
        war_system = state_mock.get_war_system.return_value
        active_war = Mock(spec=War)
        active_war.naval_required = False
        war_system.get_active_wars.return_value = [active_war]
        war_system._threats = []
        fleet = self.create_fleet(FleetStatus.AVAILABLE, False)
        assert decider.should_disband_fleet(fleet, state_mock) is True

    @pytest.mark.parametrize("status", [FleetStatus.BUILDING, FleetStatus.DESTROYED])
    def test_should_not_disband_non_eligible_fleets(self, state_mock, decider, status):
        """不应解散非 AVAILABLE/ON_MISSION 或建造中的舰队"""
        war_system = state_mock.get_war_system.return_value
        war_system.get_active_wars.return_value = []
        war_system._threats = []
        fleet = self.create_fleet(status, is_building=(status == FleetStatus.BUILDING))
        assert decider.should_disband_fleet(fleet, state_mock) is False

    def test_should_disband_on_mission_fleet_when_no_naval_wars(self, state_mock, decider):
        """ON_MISSION 舰队在无海战战争时也应被解散"""
        war_system = state_mock.get_war_system.return_value
        war_system.get_active_wars.return_value = []
        war_system._threats = []
        fleet = self.create_fleet(FleetStatus.ON_MISSION, False)
        assert decider.should_disband_fleet(fleet, state_mock) is True


class TestNavalSystemDisband:
    """测试 NavalSystem 的解散功能"""

    @pytest.fixture
    def naval_system(self):
        state = Mock()
        system = NavalSystem(state)
        system._fleets = {}
        system._next_fleet_number = 1
        return system

    def create_fleet(self, number, status=FleetStatus.AVAILABLE, is_building=False):
        fleet = Mock(spec=Fleet)
        fleet.number = number
        fleet.status = status
        fleet.is_building = is_building
        fleet.assigned_war_id = None
        return fleet

    def test_disband_unused_fleets_calls_decider_and_destroys(self, naval_system):
        """disband_unused_fleets 应调用决策器并销毁符合条件的舰队"""
        # 准备舰队
        fleet1 = self.create_fleet(1, FleetStatus.AVAILABLE)
        fleet2 = self.create_fleet(2, FleetStatus.ON_MISSION)
        fleet3 = self.create_fleet(3, FleetStatus.BUILDING, is_building=True)
        naval_system._fleets = {1: fleet1, 2: fleet2, 3: fleet3}

        # 模拟决策器
        decider = Mock(spec=FleetDisbandDecider)
        # 决策器对 fleet1 返回 True（解散），对 fleet2 返回 False（保留），对 fleet3 返回 False（建造中）
        decider.should_disband_fleet.side_effect = lambda f, s: f.number == 1

        current_turn = 10
        result = naval_system.disband_unused_fleets(current_turn, decider)

        # 验证返回解散的编号
        assert result == [1]

        # 验证 fleet1 被销毁
        fleet1.mark_destroyed.assert_called_once_with(current_turn)

        # 验证 fleet2 和 fleet3 未调用 mark_destroyed
        fleet2.mark_destroyed.assert_not_called()
        fleet3.mark_destroyed.assert_not_called()

        # 验证日志记录（可选）
        naval_system.state.log_event.assert_called_once()
        args, kwargs = naval_system.state.log_event.call_args
        assert "[DEBUG] 舰队 1 已解散" in args[0]

    def test_disband_returns_empty_list_when_no_fleets(self, naval_system):
        """无舰队时返回空列表"""
        decider = Mock()
        assert naval_system.disband_unused_fleets(10, decider) == []


class TestNavalSystemRecallFromWar:
    """测试舰队召回功能"""

    @pytest.fixture
    def naval_system(self):
        state = Mock()
        system = NavalSystem(state)
        system._fleets = {}
        return system

    def create_fleet(self, number, assigned_war_id, status=FleetStatus.ON_MISSION):
        fleet = Mock(spec=Fleet)
        fleet.number = number
        fleet.assigned_war_id = assigned_war_id
        fleet.status = status
        return fleet

    def test_recall_fleets_from_war_recalls_all_matching_fleets(self, naval_system):
        """recall_fleets_from_war 应召回所有指派给指定战争的舰队"""
        war_id = "war1"
        fleet1 = self.create_fleet(1, war_id)
        fleet2 = self.create_fleet(2, war_id)
        fleet3 = self.create_fleet(3, "other_war")
        naval_system._fleets = {1: fleet1, 2: fleet2, 3: fleet3}

        naval_system.recall_fleets_from_war(war_id)

        # 验证召回方法被调用
        fleet1.recall.assert_called_once()
        fleet2.recall.assert_called_once()
        fleet3.recall.assert_not_called()

    def test_recall_fleets_from_war_ignores_non_matching_or_wrong_status(self, naval_system):
        """不应召回状态不是 ON_MISSION 的舰队"""
        war_id = "war1"
        fleet1 = self.create_fleet(1, war_id)  # 默认 ON_MISSION
        fleet2 = Mock(spec=Fleet)
        fleet2.number = 2
        fleet2.assigned_war_id = war_id
        fleet2.status = FleetStatus.AVAILABLE
        naval_system._fleets = {1: fleet1, 2: fleet2}

        naval_system.recall_fleets_from_war(war_id)

        fleet1.recall.assert_called_once()
        fleet2.recall.assert_not_called()


# 可选：测试战争系统与海军系统的集成
class TestWarSystemIntegration:
    """测试战争系统在解决战争时召回舰队"""

    @pytest.fixture
    def war_system(self):
        from src.core.systems.war_system import WarSystem
        state = Mock()
        state.naval_system = Mock()
        system = WarSystem(state)
        system._active_wars = []
        system._war_discard = []
        return system

    def test_resolve_war_calls_recall_fleets(self, war_system):
        """resolve_war 应调用 naval_system.recall_fleets_from_war"""
        war = Mock(spec=War)
        war.id = "war1"
        war.commander_id = None
        war.status = WarStatus.ACTIVE
        war_system._active_wars = [war]

        war_system.resolve_war("war1", victory=True)

        # 验证召回方法被调用
        war_system.state.naval_system.recall_fleets_from_war.assert_called_once_with("war1")

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
        war = War(id="war1", name="Naval War", naval_required=True)
        war.status = WarStatus.THREAT
        war._enemy_naval_current = 5  # <-- 添加此行
        war_system = Mock()
        war_system._threats = [war]
        mock_state.get_war_system.return_value = war_system
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
        war._enemy_naval_current = 2
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