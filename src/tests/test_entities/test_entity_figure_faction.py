"""
T1-2 实体层校验测试：Figure 和 Faction 增量功能
测试用例对应指令集中的 FIG-001 至 FIG-007 和 FAC-001 至 FAC-008
"""

import pytest
from src.core.entities.figure import Figure, ClassTier, OfficeTerm
from src.core.entities.entities import Faction

class TestFigure:
    """Figure 类 MVP 0.5 新增功能测试"""

    def test_fig_001_default_values(self, sample_figure):
        """FIG-001: 新增字段默认值"""
        fig = sample_figure
        assert fig.land_private == 0
        assert fig.contract_ids == []
        assert fig.has_active_contract is False
        # 删除 figure_type 断言，或改为 class_tier
        assert fig.class_tier == ClassTier.PLEBEIAN
        assert fig.tribute_profit == 0
        assert fig.project_profit == 0

    def test_fig_003_add_contract_normal(self, sample_figure):
        """FIG-003: add_contract 正常添加"""
        fig = sample_figure
        fig.add_contract(1)
        assert 1 in fig.contract_ids
        assert fig.has_active_contract is True

    def test_fig_004_add_contract_duplicate(self, sample_figure):
        """FIG-004: add_contract 重复添加应不引发异常，且合同列表不变"""
        fig = sample_figure
        fig.add_contract(1)
        fig.add_contract(1)  # 再次添加相同ID
        assert fig.contract_ids == [1]  # 列表不应增加
        assert fig.has_active_contract is True  # 活跃状态应保持

    def test_fig_005_remove_contract_normal(self, sample_figure):
        """FIG-005: remove_contract 正常移除"""
        fig = sample_figure
        fig.add_contract(1)
        fig.remove_contract(1)
        assert fig.contract_ids == []
        assert fig.has_active_contract is False

    def test_fig_006_remove_contract_nonexistent(self, sample_figure):
        """FIG-006: remove_contract 移除不存在的 ID 应静默忽略"""
        fig = sample_figure
        fig.add_contract(1)
        fig.remove_contract(999)
        assert fig.contract_ids == [1]
        assert fig.has_active_contract is True

    def test_fig_007_settle_contract_profit(self, sample_figure):
        """FIG-007: settle_contract_profit 增加财富"""
        fig = sample_figure
        initial_wealth = fig.wealth
        fig.settle_contract_profit(50)
        assert fig.wealth == initial_wealth + 50

    def test_influence_and_rank(self):
        """测试影响力计算和官职等级"""
        fig = Figure(id=999, name="Test", faction_id="f1", age=40)
        fig._land_private = 3
        fig.veterans = 1
        fig.popularity = 5
        fig.nomen = "Julius"
        fig.family_prestige = 3  # 对应 Julius 的声望
        fig.update_influence()
        # 基础 = 3*10 + 1*10 + 5 = 45，家族加成 3*10=30，总计75
        assert fig.influence == 75
        assert fig.rank == 0
        fig.office = "consul"
        fig.update_influence()
        # 基础45 + 家族30 + 执政官加成40 = 115
        assert fig.influence == 115
        assert fig.rank == 4
        assert fig.has_military_command() is True
        assert fig.has_veto_power() is False
        assert fig.has_prosecution_power() is False

    def test_can_hold_office_higher_prevents_lower(self):
        """测试现任或曾担任高阶官职的人物不能竞选低阶官职"""
        config = {
            "political_rules": {
                "office_cooldowns": {"consul": 2, "praetor": 2, "quaestor": 2}
            }
        }
        current_turn = 10

        # 1. 现任执政官不能竞选大法官
        fig_consul = Figure(id=1, name="Consul", faction_id="f1", age=45)
        fig_consul.office = "consul"
        can, reason = fig_consul.can_hold_office("praetor", current_turn, config)
        assert not can
        assert "while holding higher office" in reason

        # 2. 现任执政官不能竞选财务官
        can, reason = fig_consul.can_hold_office("quaestor", current_turn, config)
        assert not can

        # 3. 现任大法官不能竞选财务官
        fig_praetor = Figure(id=2, name="Praetor", faction_id="f1", age=40)
        fig_praetor.office = "praetor"
        can, reason = fig_praetor.can_hold_office("quaestor", current_turn, config)
        assert not can
        assert "while holding higher office" in reason

        # 4. 曾担任执政官不能竞选大法官
        fig_ex_consul = Figure(id=3, name="Ex-Consul", faction_id="f1", age=50)
        fig_ex_consul.office_history = [OfficeTerm("consul", start_turn=5)]
        can, reason = fig_ex_consul.can_hold_office("praetor", current_turn, config)
        assert not can
        assert "Has held higher office" in reason

        # 5. 曾担任执政官不能竞选财务官
        can, reason = fig_ex_consul.can_hold_office("quaestor", current_turn, config)
        assert not can

        # 6. 曾担任大法官不能竞选财务官
        fig_ex_praetor = Figure(id=4, name="Ex-Praetor", faction_id="f1", age=45)
        fig_ex_praetor.office_history = [OfficeTerm("praetor", start_turn=7)]
        can, reason = fig_ex_praetor.can_hold_office("quaestor", current_turn, config)
        assert not can
        assert "Has held higher office" in reason

        # 7. 从未担任过高阶官职，可以竞选（仅检查高阶限制）
        fig_eligible = Figure(id=5, name="Eligible", faction_id="f1", age=35)
        fig_eligible.office_history = [OfficeTerm("quaestor", start_turn=8)]
        can, reason = fig_eligible.can_hold_office("praetor", current_turn, config)
        assert "higher office" not in reason  # 不应因高阶限制被拒绝

    def test_can_hold_office_higher_does_not_affect_same_level(self):
        config = {
            "political_rules": {
                "office_cooldowns": {"consul": 2, "praetor": 2, "quaestor": 2}
            }
        }
        current_turn = 10

        fig_ex_consul = Figure(id=1, name="Ex-Consul", faction_id="f1", age=50)
        fig_ex_consul.office_history = [OfficeTerm("consul", start_turn=5)]
        can, reason = fig_ex_consul.can_hold_office("consul", current_turn, config)
        # 只要不是因为高阶限制被拒绝即可（冷却期等由其他逻辑处理）
        assert "higher office" not in reason

        fig_ex_praetor = Figure(id=2, name="Ex-Praetor", faction_id="f1", age=45)
        fig_ex_praetor.office_history = [OfficeTerm("praetor", start_turn=7)]
        can, reason = fig_ex_praetor.can_hold_office("consul", current_turn, config)
        assert "higher office" not in reason

    def test_censor_prerequisite(self):
        """测试监察官需要曾担任执政官"""
        config = {
            "political_rules": {
                "office_cooldowns": {"consul": 2, "censor": 2}
            }
        }
        current_turn = 10

        # 曾担任执政官，可以竞选监察官
        fig_ex_consul = Figure(id=1, name="Ex-Consul", faction_id="f1", age=50)
        fig_ex_consul.office_history = [OfficeTerm("consul", start_turn=5)]
        can, reason = fig_ex_consul.can_hold_office("censor", current_turn, config)
        assert can, "曾担任执政官应能竞选监察官"

        # 从未担任执政官，不能竞选监察官
        fig_never_consul = Figure(id=2, name="No Consul", faction_id="f1", age=45)
        fig_never_consul.office_history = [OfficeTerm("praetor", start_turn=7)]
        can, reason = fig_never_consul.can_hold_office("censor", current_turn, config)
        assert not can
        assert "Requires prior Consul service" in reason


class TestFaction:
    """Faction 类 MVP 0.5 新增功能测试"""

    def test_fac_001_default_values(self, sample_faction):
        """FAC-001: 新增字段默认值"""
        fac = sample_faction
        assert fac.total_land == 0
        assert fac.province_owned == []
        assert fac.knight_contract_count == 0

    def test_fac_002_update_total_land_normal(self, sample_faction):
        """FAC-002: update_total_land 正确计算成员私地和"""
        fac = sample_faction
        class MockFigure:
            def __init__(self, land_private):
                self.land_private = land_private
        member1 = MockFigure(100)
        member2 = MockFigure(200)
        fac.update_total_land([member1, member2])
        assert fac.total_land == 300

    def test_fac_003_update_total_land_empty(self, sample_faction):
        """FAC-003: update_total_land 传入空列表"""
        fac = sample_faction
        fac.update_total_land([])
        assert fac.total_land == 0

    def test_fac_004_add_province_normal(self, sample_faction):
        """FAC-004: add_province 正常添加"""
        fac = sample_faction
        fac.add_province(1)
        assert 1 in fac.province_owned

    def test_fac_005_add_province_duplicate(self, sample_faction):
        """FAC-005: add_province 重复添加不应重复"""
        fac = sample_faction
        fac.add_province(1)
        fac.add_province(1)
        assert fac.province_owned == [1]

    def test_fac_006_update_knight_contract_count_normal(self, sample_faction):
        """FAC-006: update_equestrian_contract_count 正确统计有活跃合同的骑士数量"""
        fac = sample_faction
        class MockKnight:
            def __init__(self, has_active):
                self.has_active_contract = has_active
        knight1 = MockKnight(True)
        knight2 = MockKnight(False)
        fac.update_knight_contract_count([knight1, knight2])
        assert fac.knight_contract_count == 1

    def test_fac_007_update_knight_contract_count_empty(self, sample_faction):
        """FAC-007: update_knight_contract_count 传入空列表"""
        fac = sample_faction
        fac.update_knight_contract_count([])
        assert fac.knight_contract_count == 0

    def test_fac_008_province_owned_returns_copy(self, sample_faction):
        """FAC-008: province_owned 属性返回副本，修改副本不影响原字段"""
        fac = sample_faction
        fac.add_province(1)
        province_list = fac.province_owned
        province_list.append(2)
        assert fac.province_owned == [1]