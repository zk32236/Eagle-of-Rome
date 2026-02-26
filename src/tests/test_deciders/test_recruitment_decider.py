import pytest
from unittest.mock import MagicMock
from src.core.deciders.impl.auto_recruitment_decider import AutoRecruitmentDecider
from src.core.entities.entities import Faction
from src.core.entities.figure import Figure

class TestAutoRecruitmentDecider:
    def test_no_treasury(self):
        faction = Faction(id="test", name="测试派", treasury=0)
        decider = AutoRecruitmentDecider()
        bids = decider.decide_bids(faction, [], 3, None)
        assert bids == {}

    def test_vacancies_zero(self):
        faction = Faction(id="test", name="测试派", treasury=100)
        decider = AutoRecruitmentDecider()
        bids = decider.decide_bids(faction, [], 0, None)
        assert bids == {}

    def test_eligible_filter(self):
        faction = Faction(id="test", name="测试派", treasury=100)
        fig1 = Figure(id=1, name="A")
        fig1.abandoned_by = "test"
        fig2 = Figure(id=2, name="B")
        fig2.abandoned_by = "other"
        available = [fig1, fig2]
        decider = AutoRecruitmentDecider()
        bids = decider.decide_bids(faction, available, 2, None)
        assert 1 not in bids
        assert 2 in bids
        assert 1 <= bids[2] <= 100