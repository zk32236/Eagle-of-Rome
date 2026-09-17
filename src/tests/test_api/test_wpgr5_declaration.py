# src/tests/test_api/test_wpgr5_declaration.py
"""WP-G-R5 DA-3（SA §4.4）— C-AC07 + §20 #31–34 Declaration 语义 DATA 断言。"""

from src.api import senate_api

from src.tests.fixtures.wpgr5_fixtures import build_r5_base, command_draft, FIXED


def _submit(state, war_drafts, session="S1", req_id="req-1"):
    env = {"senate_session_id": session, "submit_request_id": req_id,
           "war_drafts": war_drafts, "proposals": []}
    return senate_api.propose_many(state, FIXED["player"], env)


class _Pass:
    def decide_vote(self, issue, faction, state):
        return True


def _run(bundle, war_drafts, pass_vote=True):
    state = bundle["state"]
    sub = _submit(state, war_drafts)
    assert sub["success"], sub.get("errors")
    senate_api.resolve_senate(state, vote_decider=_Pass() if pass_vote else _Fail())
    return senate_api.advance_senate_phase(state, FIXED["player"])


class _Fail:
    def decide_vote(self, issue, faction, state):
        return False


def test_active_unchecked_no_war():
    """§20 #31 / A-I10：active declaration unchecked → 不宣战。"""
    b = build_r5_base(with_passive=False)
    state = b["state"]
    war_threat = b["war_threat"]
    adv = _run(b, [command_draft(war_threat.id, b["consul_id"], 2, checked=False)])
    assert adv["success"], adv
    assert war_threat.status.value == "threat"


def test_active_rejected_no_war():
    """§20 #32 / A-I10。"""
    b = build_r5_base(with_passive=False)
    state = b["state"]
    war_threat = b["war_threat"]
    adv = _run(b, [command_draft(war_threat.id, b["consul_id"], 2)], pass_vote=False)
    assert adv["success"], adv
    assert war_threat.status.value == "threat"


def test_active_enacted_activates_at_boundary():
    """§20 #33 / C-AC07：只在边界激活；target 与 proposer 分离。"""
    b = build_r5_base(with_passive=False)
    state = b["state"]
    war_threat = b["war_threat"]
    adv = _run(b, [command_draft(war_threat.id, b["consul_id"], 1)])
    assert adv["success"], adv
    assert war_threat.status.value == "active"
    assert war_threat.commander_id == b["consul_id"]
    assert war_threat.activation_origin == "active_declaration"


def test_passive_persists_with_null_zero():
    """§20 #34 / A-I10/A-I14：passive 真实战不清除、不重激活，可 null/0 进入军事后续。"""
    b = build_r5_base()
    state = b["state"]
    war_passive = b["war_passive"]
    war_passive.commander_id = None
    adv = _run(b, [])
    assert adv["success"], adv
    assert war_passive.status.value == "active"
    assert war_passive.commander_id is None
    assert war_passive.activation_origin == "passive_declaration"
