"""EOR20261013-02 · D4/D6 I2-R3 (末段) — senate owning contract + §5.2.

RED-first contract for the item3-final slice (Store §2a S1–S6 + §5.2 Store
wiring + the I2-R2 non-blocking observations), per:

  * ``01-pm/DA-Brief-D4D6-I2-R3_2026-10-17.md`` §1 task 1–5;
  * ``00-gates/G5-PM-Ruling-D4D6-I2-R2-PASS_2026-10-17.md`` §2 (3 observations);
  * ``00-gates/PM-Disposition-D4D6-I2-R2-Amendment_2026-10-17.md`` §3 (PM narrow
    write-face extension: ``api_adapter.recovery_resume_kind()``);
  * ``02-sa-design/Rework-D3D6-D4D6-Item3-Residual-Disposition_2026-10-17.md``
    §3 (S7/S8) / §4 (owning-possession gate) / §5 (owner-checkpoint resume-kind);
  * ``00-gates/PM-Ruling-D4D6-Item3-Residual-Accepted-Errata-Overlay_2026-10-17.md``
    (E1–E5).

Covered:
  * I2R3-OBS2  the ``_terminal_senate_phase`` guard-denial fallback carries the
    ``processed`` field (observation ② of the I2-R2 G5 ruling).
  * I2R3-OBS3  ``registered_veto_required`` semantics (observation ③: literal
    alignment with the item5 disposition; the produced boolean is unchanged).
  * I2R3-§5.2  ``GuiApiAdapter.recovery_resume_kind()`` reads the owner checkpoint
    (read-only) and the Store's no-argument recovery intent uses it (NOT the I1
    cardinality proxy).

S7 NOTE (honest, STOP): wiring the owner-exit continuation into ``vote`` /
``veto`` (Disposition §3.2 S7 lower half) was attempted and STOPPED — see the
implementation report. Driving the continuation from a bare owner vote/veto
changes the legacy Store convergence (``senateCurrentStep``) and breaks existing
assertions (e.g. ``test_wpj_groupc_g7testr7``), and the only available
"owning possession" signal (``has_owning_possession``) is polluted by an
``id()``-reuse leak from a sibling test's un-ended dispatch nesting. NO TOUCH →
the vote/veto continuation is NOT wired; the additive ``propose_many`` passthrough
(delivered in I2-R2) stands.

Provenance: real factory / real service primitives; ``source_kind =
CONSTRUCTED_STATE``; ``test_chain_quality = UNIT-LOCAL-ONLY``.
NO TOUCH: every pre-existing test assertion; this file is new.
"""
from __future__ import annotations

import os
import sys

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(
    os.path.abspath(__file__)))))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

from src.api import senate_api
from src.api import session_access
from src.api import session_turn_service as sts
from src.core.entities.entities import Faction, GameTurn
from src.core.entities.figure import Figure, ClassTier
from src.core.entities.player import Player, PlayerType
from src.core.game_state import GameState
from src.core.systems.military_system import MilitarySystem
from src.core.systems.naval_system import NavalSystem
from src.core.systems.war_system import WarSystem
from src.ui.gui.api_adapter import GuiApiAdapter


def _senate_state(*, passed=0, current="player1", tribune_ai=True,
                  decision_complete=True):
    state = GameState.create_for_testing({})
    state.turn = GameTurn(turn_number=1, year=-264)
    for phase in ["mortality", "revenue", "forum", "population"]:
        state.mark_phase_executed(phase)
    state._war_system = WarSystem(state)
    state._military_system = MilitarySystem(state)
    state._naval_system = NavalSystem(state)

    f1 = Faction(id="optimates", name="Optimates", treasury=50)
    f2 = Faction(id="populares", name="Populares", treasury=30)
    state.add_faction(f1)
    state.add_faction(f2)

    consul = Figure(id=1, name="consul", faction_id="optimates", age=40)
    consul.office = "consul"
    consul.class_tier = ClassTier.NOBILE
    consul.influence = 50
    state.add_member(consul)
    f1.member_ids.append(1)

    tribune = Figure(id=3, name="tribune", faction_id="populares", age=35)
    tribune.office = "tribune"
    tribune.class_tier = ClassTier.PLEBEIAN
    state.add_member(tribune)
    f2.member_ids.append(3)

    state.add_player(Player(player_id="player1", faction_id="optimates",
                            player_type=PlayerType.HUMAN))
    state.add_player(Player(player_id="player2", faction_id="populares",
                            player_type=PlayerType.AI if tribune_ai
                            else PlayerType.HUMAN))
    state._turn_order = ["player1", "player2"]
    state.set_current_player(current)
    state.senate_proposal_decision_complete = bool(decision_complete)
    for _ in range(passed):
        pid = state.add_senate_proposal(
            {"type": "land", "act_type": "distribution",
             "amount_C": 10, "percent": 0.1})
        state.record_senate_vote("player1", pid, True)
        state.record_senate_vote("player2", pid, True)
    return state


def _registered_sealed_store(command="propose_many"):
    """A registered store whose armed mandate is sealed FAILED_RECOVERABLE, with
    the senate phase READY (checkpoint -> TERMINAL_PENDING)."""
    from src.ui.gui.session_store import GuiSessionStore
    state = _senate_state(passed=0, current="player1", decision_complete=True)
    session_access.register_hotseat_session(state, "player1", epoch=0)
    ctx = session_access.present_context(state)
    lease = session_access.authorize_and_lease(
        state, command=command, actor="player1", payload_digest="pd",
        session_id=ctx.session_id, txn_id="txn-i2r3")
    assert lease is not None
    assert session_access.recovery_mandate(state) is not None
    assert session_access.seal_recovery_mandate_for_failure(state) is True
    assert session_access.has_failed_recoverable_mandate(state) is True
    store = GuiSessionStore(state)
    return store, state


# ===========================================================================
# I2R3-OBS2 — guard-denial fallback carries the processed field
# ===========================================================================
def test_i2r3_obs2_guard_denial_fallback_carries_processed():
    state = _senate_state(passed=0, current="player1", decision_complete=True)
    session_access.register_hotseat_session(state, "player1", epoch=0)
    scope = sts.mint_scope(state, "senate")
    # registered but NO owning scope -> the finalize guard denies -> the historical
    # ready stop; observation ② asks the fallback to carry the ``processed`` field.
    res = sts._terminal_senate_phase(state, scope, None, processed=("player2",))
    assert res.status == sts.STATUS_PHASE_READY, (res.status, res.reason)
    assert res.processed == ("player2",), res.processed
    assert res.terminal is None


# ===========================================================================
# I2R3-OBS3 — registered_veto_required semantics (semantic control)
# ===========================================================================
def test_i2r3_obs3_registered_veto_required_semantics():
    # passed candidates + all ballots in -> the veto IS required
    s1 = _senate_state(passed=2, current="player2", tribune_ai=True)
    session_access.register_hotseat_session(s1, "player2", epoch=0)
    sts.mint_scope(s1, "senate")
    reg1 = senate_api._registered_role_capabilities(s1, "player2", "tribune_veto")
    assert reg1["registered_veto_required"] is True, reg1
    # zero passed candidates -> the veto is a structural absence (not required)
    s2 = _senate_state(passed=0, current="player1", decision_complete=True)
    session_access.register_hotseat_session(s2, "player1", epoch=0)
    sts.mint_scope(s2, "senate")
    reg2 = senate_api._registered_role_capabilities(s2, "player1", "tribune_veto")
    assert reg2["registered_veto_required"] is False, reg2


# ===========================================================================
# I2R3-§5.2 — read-only adapter + Store wiring
# ===========================================================================
def test_i2r3_s52_adapter_recovery_resume_kind_reads_checkpoint():
    store, state = _registered_sealed_store()
    kind = store._adapter.recovery_resume_kind()
    assert kind == "TERMINAL_PENDING", kind
    # read-only: no attempt was minted, no scope opened, the mandate unchanged
    assert session_access.current_recovery_invocation(state) is not None
    assert sts._book(state) is not None


def test_i2r3_s52_adapter_none_without_sealed_mandate():
    from src.ui.gui.session_store import GuiSessionStore
    state = _senate_state(passed=0, current="player1", decision_complete=True)
    session_access.register_hotseat_session(state, "player1", epoch=0)
    store = GuiSessionStore(state)
    assert store._adapter.recovery_resume_kind() is None


def test_i2r3_s52_store_intent_uses_adapter_resolver(monkeypatch):
    store, state = _registered_sealed_store()

    def _boom(_state):
        raise AssertionError(
            "the I1 cardinality proxy determinate_recovery_resume_kind must NOT "
            "be used by the Store intent")
    monkeypatch.setattr(session_access, "determinate_recovery_resume_kind", _boom)

    calls = {"adapter": 0, "recover": 0}
    orig = GuiApiAdapter.recovery_resume_kind

    def _spy(self):
        calls["adapter"] += 1
        return orig(self)
    monkeypatch.setattr(GuiApiAdapter, "recovery_resume_kind", _spy)

    def _fake_recover(self, viewer_id):
        calls["recover"] += 1
        return {"success": True, "message": "ok", "data": {}, "errors": []}
    monkeypatch.setattr(GuiApiAdapter, "recover_continuation", _fake_recover)

    out = store._dispatch_recovery_authority_intent()
    assert calls["adapter"] == 1, calls
    assert calls["recover"] == 1, (calls, out)
    assert out.get("success") is True, out
    # the attempt was minted for the resolved kind (consumption happens at the
    # public guard, not in the Store's no-argument intent)
    rec = session_access._record(state)
    assert rec.recovery_attempt is not None
    assert rec.recovery_attempt.get("resume_kind") == "TERMINAL_PENDING"
