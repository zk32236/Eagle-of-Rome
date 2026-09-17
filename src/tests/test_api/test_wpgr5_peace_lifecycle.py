# src/tests/test_api/test_wpgr5_peace_lifecycle.py
"""WP-G-R5 DA-3（SA §4.4）— C-AC08/09 + §20 #35–38 Peace 语义 DATA 断言。"""

from src.api import senate_api

from src.tests.fixtures.wpgr5_fixtures import build_r5_base, command_draft, peace_draft, FIXED


def _submit(state, war_drafts, session="S1", req_id="req-1"):
    env = {"senate_session_id": session, "submit_request_id": req_id,
           "war_drafts": war_drafts, "proposals": []}
    return senate_api.propose_many(state, FIXED["player"], env)


class _Pass:
    def decide_vote(self, issue, faction, state):
        return True


class _FailWar:
    def __init__(self, fail_ids):
        self.fail = set(fail_ids)

    def decide_vote(self, issue, faction, state):
        wid = issue.get("war_id") if isinstance(issue, dict) else None
        return wid not in self.fail


def _run(bundle, war_drafts, decider=None):
    state = bundle["state"]
    sub = _submit(state, war_drafts)
    assert sub["success"], sub.get("errors")
    senate_api.resolve_senate(state, vote_decider=decider or _Pass())
    return senate_api.advance_senate_phase(state, FIXED["player"])


def test_peace_enacted_effects():
    """§20 #35 / C-AC08：边界 approved/TRUCE + 赔款 + 释放/召回 + 不入 Combat。"""
    b = build_r5_base(with_passive=False)
    state = b["state"]
    war_peace = b["war_peace"]
    adv = _run(b, [peace_draft(war_peace.id)])
    assert adv["success"], adv
    assert war_peace.status.value == "truce"          # 保持 TRUCE（非 RESOLVED）
    assert war_peace.peace_treaty["status"] == "approved"
    assert war_peace.indemnity_due == 80
    assert war_peace.truce_end_turn is not None
    assert war_peace.commander_id is None              # Commander 释放
    assert state.naval_system is not None


def test_peace_rejected_terminates_and_resumes():
    """§20 #36：pending 草案终止、TRUCE→ACTIVE。"""
    b = build_r5_base(with_passive=False)
    state = b["state"]
    war_peace = b["war_peace"]
    adv = _run(b, [peace_draft(war_peace.id)], decider=_FailWar([war_peace.id]))
    assert adv["success"], adv
    assert war_peace.status.value == "active"
    assert war_peace.peace_treaty is None


def test_peace_unchecked_resumes_no_reinforcement():
    """§20 #37：unchecked → 不追和约；恢复 ACTIVE 且无新兵。"""
    b = build_r5_base(with_passive=False)
    state = b["state"]
    war_peace = b["war_peace"]
    ms = state.get_military_system()
    pool_before = len(ms.get_available_legions())
    adv = _run(b, [peace_draft(war_peace.id, checked=False)])
    assert adv["success"], adv
    assert war_peace.status.value == "active"
    assert len(ms.get_available_legions()) == pool_before


def test_noop_continue_on_pending_peac_war():
    """§20 #38 / A-I13：pending-peace 同将 N=0 → 拒和继续（TRUCE→ACTIVE）。"""
    b = build_r5_base(with_passive=False)
    state = b["state"]
    war_peace = b["war_peace"]
    adv = _run(b, [command_draft(war_peace.id, war_peace.commander_id, 0)])
    assert adv["success"], adv
    assert war_peace.status.value == "active"
    assert war_peace.commander_id == b["cmd_b"].id     # 同将保留
    assert war_peace.peace_treaty is None


def test_pending_all_outcomes_fallback():
    """C-AC09：pending War 的 command enacted → 终止草案 + 增援；确认 F=target。"""
    b = build_r5_base(with_passive=False)
    state = b["state"]
    war_peace = b["war_peace"]
    adv = _run(b, [command_draft(war_peace.id, b["consul_id"], 1)])
    assert adv["success"], adv
    assert war_peace.status.value == "active"
    assert war_peace.commander_id == b["consul_id"]
