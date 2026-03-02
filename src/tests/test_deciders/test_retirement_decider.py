# src/tests/test_deciders/test_retirement_decider.py
import pytest
from src.core.deciders.impl.auto_retirement_decider import AutoRetirementDecider
from src.core.entities.entities import Faction
from src.core.entities.figure import Figure
from unittest.mock import patch, MagicMock



class TestAutoRetirementDecider:
    def test_no_eligible(self):
        """测试没有合格候选人的情况"""
        state = MagicMock()
        state.config.get.return_value = 0.3
        faction = Faction(id="test", name="测试派系")
        fig = Figure(id=1, name="A", faction_id="test")
        fig.is_faction_leader = True   # 唯一成员是领袖
        fig.office = None
        fig._has_active_contract = False  # 使用私有字段

        faction.get_members = MagicMock(return_value=[fig])
        decider = AutoRetirementDecider(state)
        chosen_id = decider.decide_whom_to_retire(faction)
        assert chosen_id is None

    # 在文件顶部导入 patch
    from unittest.mock import patch, MagicMock

    # 修改 test_eligible_candidate
    def test_eligible_candidate(self):
        state = MagicMock()
        state.config.get.return_value = 0.3
        faction = Faction(id="test", name="测试派系")
        fig1 = Figure(id=1, name="A", faction_id="test")
        fig1.is_faction_leader = False
        fig1.office = None
        fig1._has_active_contract = False

        fig2 = Figure(id=2, name="B", faction_id="test")
        fig2.is_faction_leader = True
        fig2.office = None
        fig2._has_active_contract = False

        def get_member_side_effect(mid):
            return fig1 if mid == 1 else fig2

        state.get_member.side_effect = get_member_side_effect
        faction.get_members = MagicMock(return_value=[fig1, fig2])

        decider = AutoRetirementDecider(state)
        with patch('random.random', return_value=0.1):  # 确保概率条件通过
            chosen_id = decider.decide_whom_to_retire(faction)
        assert chosen_id == 1

    # 修改 test_filter_by_office
    def test_filter_by_office(self):
        state = MagicMock()
        state.config.get.return_value = 0.3
        faction = Faction(id="test", name="测试派系")
        fig1 = Figure(id=1, name="A", faction_id="test")
        fig1.is_faction_leader = False
        fig1.office = "consul"
        fig1._has_active_contract = False

        fig2 = Figure(id=2, name="B", faction_id="test")
        fig2.is_faction_leader = False
        fig2.office = "ex-consul"
        fig2._has_active_contract = False

        faction.get_members = MagicMock(return_value=[fig1, fig2])
        decider = AutoRetirementDecider(state)
        with patch('random.random', return_value=0.1):
            chosen_id = decider.decide_whom_to_retire(faction)
        assert chosen_id == 2

    # 修改 test_filter_by_contract
    def test_filter_by_contract(self):
        state = MagicMock()
        state.config.get.return_value = 0.3
        faction = Faction(id="test", name="测试派系")
        fig1 = Figure(id=1, name="A", faction_id="test")
        fig1.is_faction_leader = False
        fig1.office = None
        fig1._has_active_contract = True

        fig2 = Figure(id=2, name="B", faction_id="test")
        fig2.is_faction_leader = False
        fig2.office = None
        fig2._has_active_contract = False

        faction.get_members = MagicMock(return_value=[fig1, fig2])
        decider = AutoRetirementDecider(state)
        with patch('random.random', return_value=0.1):
            chosen_id = decider.decide_whom_to_retire(faction)
        assert chosen_id == 2