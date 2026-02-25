"""
T1-2 实体层校验测试：Figure 和 Faction 增量功能
测试用例对应指令集中的 FIG-001 至 FIG-007 和 FAC-001 至 FAC-008
"""

import pytest
from src.core.entities.figure import Figure
from src.core.entities.entities import Faction


class TestFigure:
    """Figure 类 MVP 0.5 新增功能测试"""

    def test_fig_001_default_values(self, sample_figure):
        """FIG-001: 新增字段默认值"""
        fig = sample_figure
        # 设计文档要求字段默认值：land_private=0, contract_ids=[], has_active_contract=False,
        # figure_type="patrician", tribute_profit=0, project_profit=0
        # 注意：实际代码中可能使用 land 而非 land_private，但测试按设计文档执行
        assert fig.land_private == 0          # 期望有 land_private 属性
        assert fig.contract_ids == []          # 期望有 contract_ids 列表
        assert fig.has_active_contract is False  # 期望有 has_active_contract
        assert fig.figure_type == "plebeian"     # 期望有 figure_type
        assert fig.tribute_profit == 0           # 期望有 tribute_profit
        assert fig.project_profit == 0           # 期望有 project_profit

    def test_fig_002_set_figure_type(self, sample_figure):
        """FIG-002: 设置 _figure_type（直接赋值）"""
        fig = sample_figure
        fig._figure_type = "equestrian"
        assert fig.figure_type == "equestrian"

    def test_fig_003_add_contract_normal(self, sample_figure):
        """FIG-003: add_contract 正常添加"""
        fig = sample_figure
        fig.add_contract(1)
        assert 1 in fig.contract_ids
        assert fig.has_active_contract is True

    def test_fig_004_add_contract_duplicate(self, sample_figure):
        """FIG-004: add_contract 重复添加应抛出 ValueError"""
        fig = sample_figure
        fig.add_contract(1)
        with pytest.raises(ValueError, match="Contract ID 1 already exists"):
            fig.add_contract(1)
        # 验证列表不变
        assert fig.contract_ids == [1]
        assert fig.has_active_contract is True

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
        fig.remove_contract(999)  # 不存在，应无异常
        assert fig.contract_ids == [1]
        assert fig.has_active_contract is True

    def test_fig_007_settle_contract_profit(self, sample_figure):
        """FIG-007: settle_contract_profit 增加财富"""
        fig = sample_figure
        initial_wealth = fig.wealth
        fig.settle_contract_profit(50)
        assert fig.wealth == initial_wealth + 50


class TestFaction:
    """Faction 类 MVP 0.5 新增功能测试"""

    def test_fac_001_default_values(self, sample_faction):
        """FAC-001: 新增字段默认值"""
        fac = sample_faction
        assert fac.total_land == 0                # 期望有 total_land 属性
        assert fac.province_owned == []           # 期望有 province_owned 列表
        assert fac.knight_contract_count == 0     # 期望有 knight_contract_count

    def test_fac_002_update_total_land_normal(self, sample_faction):
        """FAC-002: update_total_land 正确计算成员私地和"""
        fac = sample_faction
        # 创建两个模拟成员，并设置 land_private
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
        fac.add_province(1)  # 重复添加
        assert fac.province_owned == [1]  # 列表应保持不变

    def test_fac_006_update_knight_contract_count_normal(self, sample_faction):
        """FAC-006: update_equestrian_contract_count 正确统计有活跃合同的骑士数量"""
        fac = sample_faction
        # 创建两个模拟骑士，设置 has_active_contract
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
        province_list.append(2)  # 修改副本
        assert fac.province_owned == [1]  # 原字段应不变