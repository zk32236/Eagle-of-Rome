# src/tests/test_entities/test_fleet.py
from unittest.mock import Mock
from src.core.entities.fleet import Fleet, FleetStatus
from src.core.entities.figure import Figure


class TestFleet:
    def test_fleet_creation(self):
        fleet = Fleet(number=1, name="Test Fleet")
        assert fleet.number == 1
        assert fleet.name == "Test Fleet"
        assert fleet.status == FleetStatus.AVAILABLE
        assert fleet.commander_id is None
        assert fleet.experience == 0
        assert fleet.is_veteran is False
        assert fleet.assigned_war_id is None
        assert fleet.destroyed_turn == 0

    def test_fleet_default_name(self):
        fleet = Fleet(number=5)
        assert fleet.name == "Fleet 5"

    def test_fleet_assign_to_war(self):
        fleet = Fleet(number=2)
        fleet.assign_to_war(war_id="war1", mission_type="escort", commander_id=101)
        assert fleet.status == FleetStatus.ON_MISSION
        assert fleet.assigned_war_id == "war1"
        assert fleet.commander_id == 101
        assert fleet._assigned_mission_type == "escort"  # 私有字段仅用于测试

    def test_fleet_recall(self):
        fleet = Fleet(number=3)
        fleet.assign_to_war(war_id="war2", mission_type="patrol")
        fleet.recall()
        assert fleet.status == FleetStatus.AVAILABLE
        assert fleet.assigned_war_id is None
        assert fleet.commander_id is None

    def test_fleet_mark_destroyed(self):
        fleet = Fleet(number=4)
        fleet.mark_destroyed(current_turn=10)
        assert fleet.status == FleetStatus.DESTROYED
        assert fleet.destroyed_turn == 10
        assert fleet.is_veteran is False
        assert fleet.experience == 0
        assert fleet.commander_id is None
        assert fleet.assigned_war_id is None

    def test_fleet_recover(self):
        fleet = Fleet(number=6)
        fleet.mark_destroyed(current_turn=15)
        fleet.recover()
        assert fleet.status == FleetStatus.AVAILABLE
        assert fleet.destroyed_turn == 0

    def test_fleet_get_combat_strength(self):
        """测试战力计算"""
        state = Mock()
        state.get_economic_rule.return_value = 5  # 基础战力配置

        # 创建指挥官
        commander = Figure(101, "Admiral")
        commander.martial = 4
        state.get_member.return_value = commander

        fleet = Fleet(number=7)
        fleet._commander_id = 101
        fleet._strength_base = 3
        fleet._experience = 2

        strength = fleet.get_combat_strength(state)
        # 基础3 + 经验2 + 指挥官 martial 4 = 9
        assert strength == 9

    def test_fleet_get_maintenance_cost(self):
        """测试维护费计算"""
        state = Mock()
        state.get_economic_rule.side_effect = lambda key, default: {
            "fleet_maintenance_cost": 5
        }.get(key, default)

        fleet = Fleet(number=8)
        cost = fleet.get_maintenance_cost(state)
        assert cost == 5

    def test_fleet_to_dict_and_from_dict(self):
        fleet = Fleet(number=9, name="Invincible")
        fleet.assign_to_war(war_id="war3", mission_type="blockade", commander_id=202)
        fleet._experience = 3
        fleet._is_veteran = True
        fleet._location_zone_id = 2

        d = fleet.to_dict()
        reconstructed = Fleet.from_dict(d)

        assert reconstructed.number == fleet.number
        assert reconstructed.name == fleet.name
        assert reconstructed.status == fleet.status
        assert reconstructed.commander_id == fleet.commander_id
        assert reconstructed.experience == fleet.experience
        assert reconstructed.is_veteran == fleet.is_veteran
        assert reconstructed.assigned_war_id == fleet.assigned_war_id
        assert reconstructed.destroyed_turn == fleet.destroyed_turn
        # 私有字段在序列化/反序列化后应保持一致
        assert reconstructed._assigned_mission_type == fleet._assigned_mission_type
        assert reconstructed._location_zone_id == fleet._location_zone_id