# src/tests/test_commands/test_phase_resolution_truce.py
"""
WP-G G3C（Owner Correction 2026-09-01）— truce 到期机制恢复测试。

G3C 冻结语义：approved = TEMPORARY TRUCE（非战争结束），truce_end_turn 到期 →
TRUCE→THREAT（threat_level=1，commander_id=None，不恢复旧绑定，Sea Control 保持）
→ 正常威胁自动升级（≥3 爆发）→ ACTIVE。禁 expiry→ACTIVE directly / preserve_commander。
框架复用 HEAD@04a6829（plan/apply 分层、is_truce_expired、_move_to_threat、shell）。
"""
import pytest

from src.core.game_state import GameState
from src.core.entities.war import War, WarStatus
from src.core.systems.war_system import WarSystem
from src.ui.commands.phase_resolution import ResolutionCommand


@pytest.fixture
def state():
    return GameState.create_for_testing({})


def test_resolution_command_check_truce_expiry_shell_restored(state):
    """_check_truce_expiry shell 恢复（G3C）：委托 GameState 到期处理，返回 list。"""
    cmd = ResolutionCommand(state)
    assert hasattr(cmd, "_check_truce_expiry")
    assert isinstance(cmd._check_truce_expiry(), list)


def test_game_state_truce_expiry_mechanism_restored(state):
    """GameState 到期机制入口恢复（G3C）：plan/apply/process 三入口在位，A7 接线含键。"""
    assert hasattr(state, "_plan_truce_expiry")
    assert hasattr(state, "_apply_truce_expiry")
    assert hasattr(state, "process_truce_expiry")
    assert "truce_expiries" in state._plan_settlement()


def test_war_system_move_to_threat_restored(state):
    """_move_to_threat 恢复（G3C 到期目标 = THREAT，禁 direct ACTIVE）。"""
    ws = WarSystem(state)
    assert hasattr(ws, "_move_to_threat")
    # 冻结路径保留：enter_truce（STALEMATE→TRUCE）与 approved → TRUCE 原语
    assert hasattr(ws, "enter_truce")
    assert hasattr(ws, "move_truce_war_to_active")
    assert hasattr(ws, "restore_rejected_peace_treaty")
    assert hasattr(ws, "deactivate_war_to_threat")
    # _move_to_active 不恢复（GD 冻结路径 move_truce_war_to_active 承担 TRUCE→ACTIVE）
    assert not hasattr(ws, "_move_to_active")


def test_war_is_truce_expired_restored():
    """war.is_truce_expired 恢复（G3C：current_turn >= truce_end_turn → 到期）。"""
    war = War(id="w1", name="Truce War", start_year=-270, threat_level=0, strength=5)
    war.set_truce_end_turn(15)
    assert war.truce_end_turn == 15
    assert war.is_truce_expired(14) is False
    assert war.is_truce_expired(15) is True


def test_approved_truce_war_expires_to_threat_on_advance_year(state):
    """approved + truce_end_turn 到期的 TRUCE 战争经年度推进 → THREAT（G3C 恢复语义）。"""
    from src.core.entities.entities import GameTurn
    state.turn = GameTurn(turn_number=10, year=-260)
    ws = WarSystem(state)
    state._war_system = ws
    war = War(id="w1", name="Truce War", start_year=-270, threat_level=0, strength=5)
    war.status = WarStatus.TRUCE
    war.set_peace_treaty({"status": "approved"})
    war.set_truce_end_turn(4)  # 已到期（4 <= 10）
    war.commander_id = 1
    ws._truce_wars.append(war)

    state.advance_year()

    assert war not in ws._truce_wars
    assert war in ws._threats
    assert war.status == WarStatus.THREAT
    assert war.threat_level == 1
    assert war.commander_id is None
    assert war not in ws._active_wars


def test_approved_truce_war_not_expired_stays_truce(state):
    """未到期 approved TRUCE 战争经年度推进保持 TRUCE（G3C：truce_end_turn 未达）。"""
    from src.core.entities.entities import GameTurn
    state.turn = GameTurn(turn_number=3, year=-260)
    ws = WarSystem(state)
    state._war_system = ws
    war = War(id="w1", name="Truce War", start_year=-270, threat_level=0, strength=5)
    war.status = WarStatus.TRUCE
    war.set_peace_treaty({"status": "approved"})
    war.set_truce_end_turn(8)  # 未到期（3 < 8）
    ws._truce_wars.append(war)

    state.advance_year()

    assert war in ws._truce_wars
    assert war.status == WarStatus.TRUCE
    assert war not in ws._active_wars
    assert war not in ws._threats


def test_truce_expiry_exactly_once_no_requeue(state):
    """S33 exactly-once：到期战争迁移一次后，重试零重复迁移 / 零重复 threat 插入。"""
    from src.core.entities.entities import GameTurn
    state.turn = GameTurn(turn_number=10, year=-260)
    ws = WarSystem(state)
    state._war_system = ws
    war = War(id="w1", name="Truce War", start_year=-270, threat_level=0, strength=5)
    war.status = WarStatus.TRUCE
    war.set_peace_treaty({"status": "approved"})
    war.set_truce_end_turn(4)
    ws._truce_wars.append(war)

    expired1 = state.process_truce_expiry()
    expired2 = state.process_truce_expiry()

    assert expired1 == ["Truce War"]
    assert expired2 == []
    assert ws._threats.count(war) == 1
    assert war not in ws._truce_wars
    assert war.status == WarStatus.THREAT
