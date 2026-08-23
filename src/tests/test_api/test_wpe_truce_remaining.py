# src/tests/test_api/test_wpe_truce_remaining.py
"""
WP-E（GUI-BETA-R1）E-G7-11：TRUCE 剩余回合 DTO 多态测试（T-5）。

覆盖 _war_card（combat_api.py:47-76）新增字段：
- truce_end_turn / truce_remaining_turns（权威计算 = max(0, truce_end_turn - current_turn)；
  state 参数已在签名内，禁 QML 猜测 R-05）
- 多剩余回合态（4/5 → 3/5 → … → 0/5）
- truce_end_turn 为 None → truce_remaining_turns = None（null → QML 不显示）
"""
import pytest

from src.core.game_state import GameState
from src.core.entities.entities import GameTurn
from src.core.entities.war import War, WarStatus
from src.core.systems.war_system import WarSystem
from src.api import combat_api


def _make_state_with_truce(turn_number: int, truce_end_turn):
    state = GameState.create_for_testing({})
    state.turn = GameTurn(turn_number=turn_number, year=-260)
    ws = WarSystem(state)
    state._war_system = ws
    war = War(id="w1", name="Truce War", start_year=-270, threat_level=0, strength=5)
    war.status = WarStatus.TRUCE
    if truce_end_turn is not None:
        war.set_truce_end_turn(truce_end_turn)
    ws._truce_wars.append(war)
    return state, war


def test_truce_remaining_counts_down():
    """多剩余回合态：4/5 → 3/5 → … → 0/5（truce_end_turn=5 固定）。"""
    expectations = {
        1: 4,  # 5-1
        2: 3,
        3: 2,
        4: 1,
        5: 0,
    }
    for turn_number, expected_remaining in expectations.items():
        state, war = _make_state_with_truce(turn_number, truce_end_turn=5)
        card = combat_api._war_card(war, state)
        assert card["truce_end_turn"] == 5
        assert card["truce_remaining_turns"] == expected_remaining, (
            f"turn={turn_number}: expected {expected_remaining}, got {card['truce_remaining_turns']}"
        )


def test_truce_remaining_never_negative():
    """过期后（current > end）→ 0（max(0, …) 下限）。"""
    state, war = _make_state_with_truce(turn_number=8, truce_end_turn=5)
    card = combat_api._war_card(war, state)
    assert card["truce_remaining_turns"] == 0


def test_truce_remaining_none_when_no_end_turn():
    """truce_end_turn 为 None → truce_remaining_turns = None（null → QML 不显示）。"""
    state, war = _make_state_with_truce(turn_number=3, truce_end_turn=None)
    card = combat_api._war_card(war, state)
    assert card["truce_end_turn"] is None
    assert card["truce_remaining_turns"] is None


def test_war_card_existing_fields_preserved():
    """_war_card 既有字段不变（兼容性）。"""
    state, war = _make_state_with_truce(turn_number=3, truce_end_turn=5)
    card = combat_api._war_card(war, state)
    assert card["war_id"] == "w1"
    assert card["status"] == "truce"
    assert "legion_count" in card
    assert "total_power" in card
    assert "has_commander" in card
