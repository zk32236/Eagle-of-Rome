import unittest
from unittest.mock import MagicMock, patch, create_autospec

# 假设这些导入路径正确，根据实际项目结构调整
from src.core.deciders.fleet_disband_decider import FleetDisbandDecider
from src.core.deciders.impl.auto_fleet_disband_decider import AutoFleetDisbandDecider
from src.core.entities.fleet import Fleet, FleetStatus
from src.core.game_state import GameState
from src.core.entities.war import War, WarStatus


class TestAutoFleetDisbandDecider(unittest.TestCase):
    """测试自动舰队解散决策器"""

    def setUp(self):
        # 创建决策器实例
        self.decider = AutoFleetDisbandDecider()

        # 创建 mock 游戏状态
        self.state = create_autospec(GameState)

        # 创建 mock 战争系统
        self.war_system = MagicMock()
        self.state.get_war_system.return_value = self.war_system

        # 默认返回空战争列表
        self.war_system.get_active_wars.return_value = []
        self.war_system.get_threat_wars.return_value = []
        self.war_system.get_truce_wars.return_value = []

    def create_fleet(self, status=FleetStatus.AVAILABLE, is_building=False):
        """辅助方法：创建一个具有指定状态的 mock 舰队"""
        fleet = create_autospec(Fleet)
        fleet.status = status
        fleet.is_building = is_building
        # 其他属性根据需要可以设置
        return fleet

    def create_war(self, naval_required=True, status=WarStatus.ACTIVE, peace_treaty_status=None):
        """辅助方法：创建一个战争 mock"""
        war = create_autospec(War)
        war.naval_required = naval_required
        war.status = status
        if peace_treaty_status is not None:
            war.peace_treaty = {"status": peace_treaty_status}
        else:
            war.peace_treaty = None
        return war

    # ---------- 舰队状态过滤测试 ----------
    def test_ignore_building_fleet(self):
        """建造中的舰队不应考虑解散"""
        fleet = self.create_fleet(status=FleetStatus.BUILDING, is_building=True)
        result = self.decider.should_disband_fleet(fleet, self.state)
        self.assertFalse(result)

    def test_ignore_destroyed_fleet(self):
        """已摧毁的舰队不应考虑解散"""
        fleet = self.create_fleet(status=FleetStatus.DESTROYED, is_building=False)
        result = self.decider.should_disband_fleet(fleet, self.state)
        self.assertFalse(result)

    # ---------- 无战争测试 ----------
    def test_no_wars_should_disband(self):
        """没有任何需要海战的战争，应解散"""
        fleet = self.create_fleet()
        result = self.decider.should_disband_fleet(fleet, self.state)
        self.assertTrue(result)

    # ---------- 活跃战争测试 ----------
    def test_active_war_with_naval_required_should_not_disband(self):
        """有活跃战争且需要海战，不应解散"""
        fleet = self.create_fleet()
        war = self.create_war(naval_required=True, status=WarStatus.ACTIVE)
        self.war_system.get_active_wars.return_value = [war]
        result = self.decider.should_disband_fleet(fleet, self.state)
        self.assertFalse(result)

    def test_active_war_without_naval_required_should_disband(self):
        """有活跃战争但不需要海战，应解散"""
        fleet = self.create_fleet()
        war = self.create_war(naval_required=False, status=WarStatus.ACTIVE)
        self.war_system.get_active_wars.return_value = [war]
        result = self.decider.should_disband_fleet(fleet, self.state)
        self.assertTrue(result)

    # ---------- 威胁战争测试 ----------
    def test_threat_war_with_naval_required_should_not_disband(self):
        """有威胁战争且需要海战，不应解散"""
        fleet = self.create_fleet()
        war = self.create_war(naval_required=True, status=WarStatus.THREAT)
        self.war_system.get_threat_wars.return_value = [war]
        result = self.decider.should_disband_fleet(fleet, self.state)
        self.assertFalse(result)

    # ---------- 停战战争测试 ----------
    def test_truce_war_pending_should_not_disband(self):
        """停战战争，草案未批准（pending），不应解散"""
        fleet = self.create_fleet()
        war = self.create_war(naval_required=True, status=WarStatus.TRUCE, peace_treaty_status='pending')
        self.war_system.get_truce_wars.return_value = [war]
        result = self.decider.should_disband_fleet(fleet, self.state)
        self.assertFalse(result)

    def test_truce_war_submitted_should_not_disband(self):
        """停战战争，草案已提交但未表决（submitted），不应解散（视作未批准）"""
        fleet = self.create_fleet()
        war = self.create_war(naval_required=True, status=WarStatus.TRUCE, peace_treaty_status='submitted')
        self.war_system.get_truce_wars.return_value = [war]
        result = self.decider.should_disband_fleet(fleet, self.state)
        self.assertFalse(result)

    def test_truce_war_approved_should_disband(self):
        """停战战争，草案已批准，应解散（假设没有其他需要海战的战争）"""
        fleet = self.create_fleet()
        war = self.create_war(naval_required=True, status=WarStatus.TRUCE, peace_treaty_status='approved')
        self.war_system.get_truce_wars.return_value = [war]
        result = self.decider.should_disband_fleet(fleet, self.state)
        self.assertTrue(result)

    def test_truce_war_approved_but_active_war_should_not_disband(self):
        """停战战争已批准，但还有活跃战争需要海战，不应解散"""
        fleet = self.create_fleet()
        truce_war = self.create_war(naval_required=True, status=WarStatus.TRUCE, peace_treaty_status='approved')
        active_war = self.create_war(naval_required=True, status=WarStatus.ACTIVE)
        self.war_system.get_truce_wars.return_value = [truce_war]
        self.war_system.get_active_wars.return_value = [active_war]
        result = self.decider.should_disband_fleet(fleet, self.state)
        self.assertFalse(result)

    # ---------- 混合战争测试 ----------
    def test_mix_no_naval_wars_should_disband(self):
        """混合战争，但没有一个需要海战，应解散"""
        fleet = self.create_fleet()
        wars = [
            self.create_war(naval_required=False, status=WarStatus.ACTIVE),
            self.create_war(naval_required=False, status=WarStatus.THREAT),
            self.create_war(naval_required=True, status=WarStatus.TRUCE, peace_treaty_status='approved')
        ]
        self.war_system.get_active_wars.return_value = [w for w in wars if w.status == WarStatus.ACTIVE]
        self.war_system.get_threat_wars.return_value = [w for w in wars if w.status == WarStatus.THREAT]
        self.war_system.get_truce_wars.return_value = [w for w in wars if w.status == WarStatus.TRUCE]
        result = self.decider.should_disband_fleet(fleet, self.state)
        self.assertTrue(result)

    def test_mix_with_naval_war_should_not_disband(self):
        """混合战争，其中有一个需要海战（无论是 active/threat/pending truce），不应解散"""
        fleet = self.create_fleet()
        wars = [
            self.create_war(naval_required=False, status=WarStatus.ACTIVE),
            self.create_war(naval_required=True, status=WarStatus.THREAT),   # 需要海战
            self.create_war(naval_required=True, status=WarStatus.TRUCE, peace_treaty_status='approved')
        ]
        self.war_system.get_active_wars.return_value = [w for w in wars if w.status == WarStatus.ACTIVE]
        self.war_system.get_threat_wars.return_value = [w for w in wars if w.status == WarStatus.THREAT]
        self.war_system.get_truce_wars.return_value = [w for w in wars if w.status == WarStatus.TRUCE]
        result = self.decider.should_disband_fleet(fleet, self.state)
        self.assertFalse(result)

    # ---------- 边缘情况 ----------
    def test_no_war_system_should_not_disband(self):
        """如果没有战争系统（不应发生），应保守不解散"""
        self.state.get_war_system.return_value = None
        fleet = self.create_fleet()
        result = self.decider.should_disband_fleet(fleet, self.state)
        self.assertFalse(result)

    def test_fleet_on_mission_should_be_considered(self):
        """舰队处于 ON_MISSION 状态也应考虑解散（只要没有需要海战的战争）"""
        fleet = self.create_fleet(status=FleetStatus.ON_MISSION, is_building=False)
        result = self.decider.should_disband_fleet(fleet, self.state)
        self.assertTrue(result)


if __name__ == '__main__':
    unittest.main()