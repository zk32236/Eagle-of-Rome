"""R13 DATA supplements: real registered owner chains, not GUI/G7 acceptance.
Only late initializer fault injection is MOCK_AUXILIARY; no executor success stub.
"""
import copy
import random
from types import MappingProxyType

import pytest

from src.api import forum_api, session_access
from src.api import session_turn_service as turns
from src.core.entities.contract import ContractStatus
from src.core.entities.player import PlayerType
from src.tests.test_gui.test_gui_readiness_a3 import _registered_forum_store, raw_state


@pytest.fixture(autouse=True)
def preserve_rng():
    before = random.getstate()
    random.seed(1313)
    yield
    random.setstate(before)


def market_store(mode):
    state, pids, store = _registered_forum_store(
        [PlayerType.HUMAN, PlayerType.AI, PlayerType.HUMAN], [])
    principal = pids[0]
    pids = [pids[1], pids[0], *pids[2:]]
    faction = state.get_faction(state.get_player(pids[0]).faction_id)
    # Deterministic real deciders: no contracts/triumphs/land; recruitment either
    # has no targets or genuinely declines available targets for lack of funds.
    for c in state.contracts:
        c.status = ContractStatus.PENDING
    assert not state.get_war_system().get_resolved_wars()
    state._pending_land_sale_quota = 0
    faction.treasury = 0
    if mode == "empty":
        state.curia.available_figures = []
    else:
        assert forum_api.generate_figures(
            state, caller_context=session_access.present_context(state))["success"]
        assert state.curia.get_all_available()
        # Legal eligible recruitment shape; the real decider declines on funds,
        # not because the faction is already structurally at capacity.
        member = next(m for m in faction.get_members(state) if not m.is_faction_leader)
        faction.remove_member(member.id)
        member.faction_id = None
        state.curia.add_figure(member)
        assert state.get_remaining_recruitment_slots(faction.id) > 0
    if mode == "mutation":
        state._pending_land_sale_quota = 1
        for m in faction.get_members(state):
            m.wealth = 100
    scope = turns.mint_scope(state, "forum")
    for pid in pids:
        assert store._record_forum_ledger_finish(pid, "retirement", f"prep:{pid}")["success"]
    assert store._record_forum_ledger_finish(principal, "market", "prep:market")["success"]
    state.add_forum_action("market_opened", True)
    assert turns.select_scheduled_actor(state, "forum", pids[0], scope.scope_id)["success"]
    return state, pids, store, scope


@pytest.mark.parametrize("mode,expected", [
    ("empty", turns.KIND_STRUCTURAL_NONE),
    ("no-choice", turns.KIND_EXPLICIT_FINISH),
])
def test_R13_F01_real_registered_market_no_command(mode, expected):
    state, pids, store, scope = market_store(mode)
    book = turns._book(state)
    oid = book.oid("forum", "market", ("player", pids[0]), scope.scope_id)
    before = raw_state(state)
    store._process_ai_factions_forum("market")
    recs = [r for r in book.records if r.obligation_id == oid]
    assert len(recs) == 1
    assert recs[0].satisfied_kind == expected
    assert not [r for r in book.records if r.satisfied_kind == turns.KIND_ACTION]
    assert not [f for f in book.committed_facts.values() if f["kind"] == turns.KIND_ACTION]
    # Cursor/ledger are deliberately outside to_dict; domain + RNG untouched.
    assert raw_state(state) == before
    store._process_ai_factions_forum("market")
    assert len([r for r in book.records if r.obligation_id == oid]) == 1
    assert raw_state(state) == before


def test_R13_F01_real_registered_market_mutation_exact_fact_no_replay():
    state, pids, store, scope = market_store("mutation")
    book = turns._book(state)
    oid = book.oid("forum", "market", ("player", pids[0]), scope.scope_id)
    revision = turns.current_revision(state)
    assert state.get_forum_pending()["land_purchases"] == []
    # Real service-issued, exact-command masked AI authority, not a fabricated
    # ACCEPTED executor. Direct owner dispatch is a DATA supplement, not QML.
    from src.ui.processors.auto_player_processor import AutoPlayerProcessor
    from src.core.deciders.impl.auto_retirement_decider import AutoRetirementDecider
    from src.core.deciders.impl.auto_recruitment_decider import AutoRecruitmentDecider
    from src.core.deciders.impl.auto_bid_decider import AutoBidDecider
    from src.core.deciders.impl.auto_triumph_decider import AutoTriumphDecider
    processor = AutoPlayerProcessor(state, AutoRetirementDecider(state),
        AutoRecruitmentDecider(), AutoBidDecider(), AutoTriumphDecider())
    session_access.begin_masked_execution(state, txn_id="r13-market", authorization_epoch=0,
        phase="forum", substep="market", revision=revision)
    cap = session_access.issue_ai_capability(state, operation="buy_land", phase="forum",
        substep="market", revision=revision, expected_actor=pids[0],
        txn_id="r13-market", authorization_epoch=0)
    outcome = turns.run_scheduled_actor(state, "forum", pids[0], processor.process_market,
        pids[0], state.get_faction(state.get_player(pids[0]).faction_id),
        scope_id=scope.scope_id, ai_capability=cap)
    assert outcome.kind == turns.OUTCOME_ACCEPTED, outcome
    assert outcome.receipts == ("buy_land",)
    assert store._record_forum_ai_completion(pids[0], "market", outcome)["success"]
    session_access.end_masked_execution(state)
    recs = [r for r in book.records if r.obligation_id == oid]
    assert len(recs) == 1 and recs[0].satisfied_kind == turns.KIND_ACTION
    purchases = state.get_forum_pending()["land_purchases"]
    assert len(purchases) == 1 and purchases[0][1] == 1
    assert state.get_member(purchases[0][0]).faction_id == state.get_player(pids[0]).faction_id
    fact = book.committed_facts[recs[0].authoritative_fact_ref]
    assert isinstance(fact, MappingProxyType)
    assert fact["command"] == "process_market"
    assert fact["actor_player_id"] == pids[0]
    assert fact["scope_id"] == scope.scope_id
    assert fact["obligation_id"] == oid
    assert fact["core_revision_before"] == revision
    assert fact["kind"] == turns.KIND_ACTION
    with pytest.raises(TypeError):
        fact["command"] = "altered"
    committed = raw_state(state)
    count = len(book.records)
    store._process_ai_factions_forum("market")
    assert raw_state(state) == committed and len(book.records) == count


@pytest.mark.parametrize("fault_step", ["generate_contracts", "check_province_unrest"])
def test_R13_F02_real_initializer_late_failure_resumes_owner_steps(monkeypatch, fault_step):
    state, pids, store = _registered_forum_store([PlayerType.HUMAN], [PlayerType.AI])
    for pid in pids:
        assert store._record_forum_ledger_finish(pid, "retirement", f"prep:{pid}")["success"]
    before_figures = {f.id for f in state.curia.get_all_available()}
    real_step = getattr(forum_api, fault_step)
    calls = []

    def fail(*args, **kwargs):
        # MOCK_AUXILIARY: refuse one late owner step, before its mutation.
        calls.append(fault_step)
        return {"success": False, "message": "R13 late-step fault", "data": {}}

    monkeypatch.setattr(forum_api, fault_step, fail)
    failed = store._adapter.open_forum_market(pids[0])
    assert not failed["success"]
    pending = state.get_forum_pending()
    assert not pending["forum_initialized"] and not pending["market_opened"]
    committed_figures = {f.id for f in state.curia.get_all_available()}
    assert committed_figures > before_figures, "real earlier figure batch must survive"
    ws = state.get_war_system()
    threats = {w.id: (w.status, w.threat_level) for w in ws.get_threat_wars()}
    assert "pyrrhic_war" in threats
    contracts = copy.deepcopy([c.to_dict() for c in state.get_all_contracts()])
    # A repeated refusal must not repeat *any* committed global owner work/RNG.
    post_commit = raw_state(state)
    failed_again = store._adapter.open_forum_market(pids[0])
    assert not failed_again["success"]
    assert raw_state(state) == post_commit
    monkeypatch.setattr(forum_api, fault_step, real_step)
    resumed = store._adapter.open_forum_market(pids[0])
    assert resumed["success"], resumed
    assert {f.id for f in state.curia.get_all_available()} == committed_figures
    assert {w.id: (w.status, w.threat_level) for w in ws.get_threat_wars()} == threats
    if fault_step == "check_province_unrest":
        assert [c.to_dict() for c in state.get_all_contracts()] == contracts
    pending = state.get_forum_pending()
    assert pending["forum_initialized"] == [True]
    assert pending["market_opened"] == [True]
    canonical = raw_state(state)
    assert store._adapter.open_forum_market(pids[0])["success"]
    assert raw_state(state) == canonical
    assert len(calls) == 2
