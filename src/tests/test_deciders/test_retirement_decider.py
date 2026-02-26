# src/tests/test_deciders/test_retirement_decider.py
import pytest
from unittest.mock import MagicMock
from src.core.deciders.impl.auto_retirement_decider import AutoRetirementDecider
from src.core.entities.entities import Faction
from src.core.entities.figure import Figure


class TestAutoRetirementDecider:
    def test_eligible_candidate(self):
        """测试有合格候选人的情况"""
        state = MagicMock()
        faction = Faction(id="test", name="测试派系")
        fig1 = Figure(id=1, name="A", faction_id="test")
        fig1.is_faction_leader = False
        fig1.office = None
        fig1._has_active_contract = False  # 使用私有字段

        fig2 = Figure(id=2, name="B", faction_id="test")
        fig2.is_faction_leader = True   # 领袖，不应被选
        fig2.office = None
        fig2._has_active_contract = False  # 使用私有字段

        def get_member_side_effect(mid):
            return fig1 if mid == 1 else fig2

        state.get_member.side_effect = get_member_side_effect

        # 模拟 faction.get_members 返回成员列表
        faction.get_members = MagicMock(return_value=[fig1, fig2])

        decider = AutoRetirementDecider(state)
        chosen_id = decider.decide_whom_to_retire(faction)
        assert chosen_id == 1   # 应该选中 fig1

    def test_no_eligible(self):
        """测试没有合格候选人的情况"""
        state = MagicMock()
        faction = Faction(id="test", name="测试派系")
        fig = Figure(id=1, name="A", faction_id="test")
        fig.is_faction_leader = True   # 唯一成员是领袖
        fig.office = None
        fig._has_active_contract = False  # 使用私有字段

        faction.get_members = MagicMock(return_value=[fig])
        decider = AutoRetirementDecider(state)
        chosen_id = decider.decide_whom_to_retire(faction)
        assert chosen_id is None

    def test_filter_by_office(self):
        """测试现任公职被过滤"""
        state = MagicMock()
        faction = Faction(id="test", name="测试派系")
        fig1 = Figure(id=1, name="A", faction_id="test")
        fig1.is_faction_leader = False
        fig1.office = "consul"   # 现任公职，不应被选
        fig1._has_active_contract = False  # 使用私有字段

        fig2 = Figure(id=2, name="B", faction_id="test")
        fig2.is_faction_leader = False
        fig2.office = "ex-consul"  # 前公职，应该可以
        fig2._has_active_contract = False  # 使用私有字段

        faction.get_members = MagicMock(return_value=[fig1, fig2])
        decider = AutoRetirementDecider(state)
        chosen_id = decider.decide_whom_to_retire(faction)
        assert chosen_id == 2

    def test_filter_by_contract(self):
        """测试有活跃合同被过滤"""
        state = MagicMock()
        faction = Faction(id="test", name="测试派系")
        fig1 = Figure(id=1, name="A", faction_id="test")
        fig1.is_faction_leader = False
        fig1.office = None
        fig1._has_active_contract = True   # 有合同，不应被选

        fig2 = Figure(id=2, name="B", faction_id="test")
        fig2.is_faction_leader = False
        fig2.office = None
        fig2._has_active_contract = False

        faction.get_members = MagicMock(return_value=[fig1, fig2])
        decider = AutoRetirementDecider(state)
        chosen_id = decider.decide_whom_to_retire(faction)
        assert chosen_id == 2