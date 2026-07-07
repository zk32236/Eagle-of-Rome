# src/tests/test_systems/test_war_system.py

import pytest
from unittest.mock import MagicMock
from src.core.systems.war_system import WarSystem
from src.core.entities.war import War, WarStatus
from src.core.game_state import GameState
from src.core.entities.entities import GameTurn


@pytest.fixture
def game_state():
    state = GameState.create_for_testing({})
    state.turn = GameTurn(turn_number=1, year=-280)
    return state


@pytest.fixture
def war_system(game_state):
    ws = WarSystem(game_state)
    war = War(
        id="pyrrhic_war",
        name="皮洛士战争",
        start_year=-280,
        threat_level=0,
        auto_escalate=True,
        escalate_rate=1,
        strength=8,
        naval_support_required=True,
        naval_strength=3
    )
    war.status = WarStatus.INACTIVE
    ws._war_deck = [war]
    return ws


class TestWarThreatMechanism:
    """战争威胁机制单元测试"""

    def test_war_loading_with_new_fields(self, war_system):
        """测试战争卡加载时新字段被正确解析"""
        war = war_system._war_deck[0]
        assert war.start_year == -280
        assert war.threat_level == 0
        assert war.auto_escalate is True
        assert war.escalate_rate == 1

    def test_trigger_when_year_reaches_start(self, game_state, war_system):
        war_system.check_triggers(game_state.turn.year)
        assert len(war_system._threats) == 1
        assert war_system._threats[0].status == WarStatus.THREAT
        assert war_system._threats[0].threat_level == 1  # 触发时为1

    def test_no_trigger_before_start_year(self, game_state, war_system):
        """测试年份未达到时，战争不触发"""
        game_state.turn.year = -281
        war_system.check_triggers(game_state.turn.year)
        assert len(war_system._threats) == 0
        assert len(war_system._war_deck) == 1
        assert war_system._war_deck[0].status == WarStatus.INACTIVE

    def test_auto_escalation(self, game_state, war_system):
        # 触发战争
        war_system.check_triggers(-280)
        assert len(war_system._threats) == 1
        assert war_system._threats[0].threat_level == 1

        # 触发当年不应升级
        events = war_system.escalate_threats()
        assert len(events) == 0
        assert war_system._threats[0].threat_level == 1

        # 第2年：升到2
        events = war_system.escalate_threats()
        assert war_system._threats[0].threat_level == 2
        assert "升级至：大军压境" in events[0]

        # 第3年：爆发
        events = war_system.escalate_threats()
        assert len(war_system._threats) == 0
        assert len(war_system._active_wars) == 1
        assert war_system._active_wars[0].status == WarStatus.ACTIVE
        assert war_system._active_wars[0].threat_level == 3
        assert "战争爆发" in events[0]

    def test_escalation_stops_when_war_active(self, game_state, war_system):
        war_system.check_triggers(-280)
        war_system.escalate_threats()  # 触发当年，无事件
        war_system.escalate_threats()  # 到2
        war_system.escalate_threats()  # 爆发
        events = war_system.escalate_threats()
        assert len(events) == 0
        assert len(war_system._active_wars) == 1
        assert war_system._active_wars[0].threat_level == 3


class TestWarSystemPublicInterfaces:
    def test_resolved_and_naval_queries_return_copies(self, game_state):
        ws = WarSystem(game_state)
        resolved = War(id="resolved", name="Resolved")
        resolved.status = WarStatus.RESOLVED
        naval = War(id="naval", name="Naval", naval_required=True)
        naval.status = WarStatus.THREAT
        land = War(id="land", name="Land", naval_required=False)
        land.status = WarStatus.THREAT
        ws._war_discard = [resolved]
        ws._threats = [naval, land]

        resolved_copy = ws.get_resolved_wars()
        naval_copy = ws.get_naval_threat_wars()
        resolved_copy.clear()
        naval_copy.clear()

        assert ws.get_resolved_wars() == [resolved]
        assert ws.get_naval_threat_wars() == [naval]

    def test_rebellion_registration_is_idempotent_and_active(self, game_state):
        ws = WarSystem(game_state)
        province = MagicMock()
        province.province_id = 7
        province.name = "Sicilia"
        war = ws.create_rebellion_war(province)

        assert ws.register_rebellion_war(war) is True
        assert ws.register_rebellion_war(war) is False
        assert war.status == WarStatus.ACTIVE
        assert ws.get_active_wars() == [war]

    def test_clear_legions_to_disband_returns_copy_and_clears(self, game_state):
        ws = WarSystem(game_state)
        ws.add_legions_to_disband([1, 2])

        pending = ws.clear_legions_to_disband()
        pending.append(3)

        assert pending == [1, 2, 3]
        assert ws.clear_legions_to_disband() == []
