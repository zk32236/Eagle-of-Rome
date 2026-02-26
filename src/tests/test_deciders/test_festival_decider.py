import pytest
from unittest.mock import MagicMock
from src.core.deciders.impl.auto_festival_decider import AutoFestivalDecider
from src.core.entities.entities import Faction
from src.core.entities.figure import Figure
from src.core.game_state import GameState

class TestAutoFestivalDecider:
    def test_eligible_figure(self):
        faction = Faction(id="test", name="Test")
        fig = Figure(id=1, name="Fig", faction_id="test", age=35)
        fig.wealth = 100
        fig.office = None
        fig.is_dead = False
        state = MagicMock(spec=GameState)
        candidates = [fig]
        decider = AutoFestivalDecider()
        decisions = decider.decide_festivals(faction, candidates, state)
        assert 1 in decisions
        assert 1 <= decisions[1] <= 100

    def test_exclude_office_holder(self):
        faction = Faction(id="test", name="Test")
        fig = Figure(id=1, name="Fig", faction_id="test", age=35)
        fig.wealth = 100
        fig.office = "consul"
        fig.is_dead = False
        state = MagicMock()
        candidates = [fig]
        decider = AutoFestivalDecider()
        decisions = decider.decide_festivals(faction, candidates, state)
        assert 1 not in decisions

    def test_exclude_dead(self):
        faction = Faction(id="test", name="Test")
        fig = Figure(id=1, name="Fig", faction_id="test", age=35)
        fig.wealth = 100
        fig.office = None
        fig.is_dead = True
        state = MagicMock()
        candidates = [fig]
        decider = AutoFestivalDecider()
        decisions = decider.decide_festivals(faction, candidates, state)
        assert 1 not in decisions

    def test_exclude_young(self):
        faction = Faction(id="test", name="Test")
        fig = Figure(id=1, name="Fig", faction_id="test", age=25)
        fig.wealth = 100
        fig.office = None
        fig.is_dead = False
        state = MagicMock()
        candidates = [fig]
        decider = AutoFestivalDecider()
        decisions = decider.decide_festivals(faction, candidates, state)
        assert 1 not in decisions