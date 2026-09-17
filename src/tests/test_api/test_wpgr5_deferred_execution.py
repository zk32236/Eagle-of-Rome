# src/tests/test_api/test_wpgr5_deferred_execution.py
"""WP-G-R5 DA-3（SA §4）— C-AC01~06/10~17 + §20 #25–30/#35–38 边界执行事务 DATA 断言。

纪律：真实 GameState/War/Figure/Legion 实体；全真公开调用（senate_api.propose_many /
resolve_senate / advance_senate_phase）；不代跑业务、不伪造默认。
"""

import copy
from unittest.mock import MagicMock, patch

import pytest

from src.api import senate_api
from src.core.systems.political_system import PoliticalSystem

from src.tests.fixtures.wpgr5_fixtures import (
    build_r5_base, command_draft, peace_draft, FIXED,
)


class _VoteDecider:
    """按 war_id 控制通过/否决：fail_war_ids 中的 War 提案被否（其余通过）。"""

    def __init__(self, fail_war_ids=()):
        self.fail = set(fail_war_ids)

    def decide_vote(self, issue, faction, state):
        wid = None
        if isinstance(issue, dict):
            wid = issue.get("war_id")
            if wid is None and issue.get("war") is not None:
                wid = getattr(issue["war"], "id", None)
        return wid not in self.fail


def _submit(state, war_drafts, session="S1", req_id="req-1", proposals=None):
    env = {"senate_session_id": session, "submit_request_id": req_id,
           "war_drafts": war_drafts, "proposals": proposals or []}
    return senate_api.propose_many(state, FIXED["player"], env)


def _resolve(state, fail_war_ids=()):
    return senate_api.resolve_senate(state, vote_decider=_VoteDecider(fail_war_ids))


def _proposal_id_for_war(state, war_id):
    for p in state.get_senate_proposals():
        if p.get("war_id") == war_id:
            return p.get("id")
    return None


def _boundary(bundle, war_drafts, fail_war_ids=(), veto_war_ids=(), session="S1", req_id="req-1"):
    state = bundle["state"]
    sub = _submit(state, war_drafts, session=session, req_id=req_id)
    assert sub["success"], sub.get("errors")
    for wid in veto_war_ids:
        pid = _proposal_id_for_war(state, wid)
        if pid is not None:
            state.record_senate_veto(pid)
    res = _resolve(state, fail_war_ids=fail_war_ids)
    adv = senate_api.advance_senate_phase(state, FIXED["player"])
    return sub, res, adv


def _pool_size(state):
    ms = state.get_military_system()
    return len(ms.get_available_legions()) if ms else 0


# --------------------------------------------------------------------------- #
# C-AC01 / §20 #25 — before boundary zero military mutation
# --------------------------------------------------------------------------- #

def test_no_early_mutation_before_boundary():
    b = build_r5_base()
    state = b["state"]
    war_a = b["war_ongoing"]
    a_before = war_a.commander_id
    pool_before = _pool_size(state)
    drafts = [command_draft(war_a.id, b["consul_id"], 2),
              peace_draft(b["war_peace"].id)]
    sub = _submit(state, drafts)
    assert sub["success"], sub.get("errors")
    _resolve(state)
    # Submit/Vote/Veto/Results 全链零军事写：Commander 不变、未征召、条约仍 pending
    assert war_a.commander_id == a_before
    assert _pool_size(state) == pool_before
    assert b["war_peace"].peace_treaty["status"] == "pending"
    assert not state.is_phase_executed("senate")


def test_boundary_resolves_atomically():
    """§20 #26 / C-AC07：active declaration 只在边界激活。"""
    b = build_r5_base()
    state = b["state"]
    war_threat = b["war_threat"]
    drafts = [command_draft(war_threat.id, b["consul_id"], 3)]
    sub, res, adv = _boundary(b, drafts)
    assert adv["success"], adv
    assert war_threat.status.value == "active"
    assert war_threat.commander_id == b["consul_id"]
    assert state.is_phase_executed("senate")


# --------------------------------------------------------------------------- #
# §20 #27/#28/#29 / C-AC03/05 — rejected / vacancy / survivors
# --------------------------------------------------------------------------- #

def test_rejected_gets_no_reinforcement_and_retains_original():
    b = build_r5_base()
    state = b["state"]
    war_a = b["war_ongoing"]
    pool_before = _pool_size(state)
    drafts = [command_draft(war_a.id, b["consul_id"], 2)]
    sub, res, adv = _boundary(b, drafts, fail_war_ids=[war_a.id])
    assert adv["success"], adv
    assert war_a.commander_id == b["cmd_a"].id          # 原将保留
    assert _pool_size(state) == pool_before             # 未征召


def test_swap_single_enacted_leaves_other_vacant():
    b = build_r5_base()
    state = b["state"]
    war_a, war_b = b["war_ongoing"], b["war_peace"]
    drafts = [command_draft(war_a.id, b["cmd_b"].id, 0),
              command_draft(war_b.id, b["cmd_a"].id, 0)]
    sub, res, adv = _boundary(b, drafts, fail_war_ids=[war_b.id])
    assert adv["success"], adv
    assert war_a.commander_id == b["cmd_b"].id
    assert war_b.commander_id is None                   # VACANT（合法）
    assert war_a.legion_numbers is not None


def test_swap_both_enacted():
    b = build_r5_base()
    state = b["state"]
    war_a, war_b = b["war_ongoing"], b["war_peace"]
    drafts = [command_draft(war_a.id, b["cmd_b"].id, 0),
              command_draft(war_b.id, b["cmd_a"].id, 0)]
    sub, res, adv = _boundary(b, drafts)
    assert adv["success"], adv
    assert war_a.commander_id == b["cmd_b"].id
    assert war_b.commander_id == b["cmd_a"].id


def test_order_independent_plan():
    """§20 #30 / C-AC03：Plan 与 card/decision 遍历顺序无关。"""
    b = build_r5_base()
    state = b["state"]
    pol = PoliticalSystem(state)
    real_wars = pol._real_wars()
    decisions = [
        {"proposal_id": 1, "war_id": b["war_ongoing"].id, "outcome": "ENACTED",
         "mode": "command", "source": "ongoing",
         "payload": {"target_commander_id": b["cmd_b"].id, "reinforcement_n": 0},
         "snapshot_ref": {}},
        {"proposal_id": 2, "war_id": b["war_passive"].id, "outcome": "ENACTED",
         "mode": "command", "source": "ongoing",
         "payload": {"target_commander_id": b["cmd_a"].id, "reinforcement_n": 0},
         "snapshot_ref": {}},
    ]
    base = {"current_turn": 1, "session_id": "S1", "real_wars": real_wars,
            "available_legion_ids": [], "pending_war_ids": [b["war_peace"].id]}
    p1 = pol.build_war_resolution_plan({**base, "decisions": decisions})
    p2 = pol.build_war_resolution_plan({**base, "decisions": list(reversed(decisions))})
    assert p1["final_commander_by_war"] == p2["final_commander_by_war"]
    assert p1["pending_fallback_set"] == p2["pending_fallback_set"]


# --------------------------------------------------------------------------- #
# C-AC06 — null commander / empty package advance
# --------------------------------------------------------------------------- #

def test_null_commander_advance_no_mandatory_gate():
    b = build_r5_base(with_passive=False)
    state = b["state"]
    b["war_ongoing"].commander_id = None       # 合法 commanderless
    sub = _submit(state, [])                    # 空包
    assert sub["success"], sub.get("errors")
    res = _resolve(state)
    assert res["success"]
    adv = senate_api.advance_senate_phase(state, FIXED["player"])
    assert adv["success"], adv                  # 不因 commanderless 阻止 advance
    assert state.is_phase_executed("senate")


# --------------------------------------------------------------------------- #
# C-AC10 — deterministic reinforcement allocation
# --------------------------------------------------------------------------- #

def test_reinforcement_allocated_exactly_n():
    b = build_r5_base(with_passive=False)
    state = b["state"]
    drafts = [command_draft(b["war_ongoing"].id, b["cmd_a"].id, 2)]
    before = _pool_size(state)
    sub, res, adv = _boundary(b, drafts)
    assert adv["success"], adv
    assert _pool_size(state) == before - 2
    assert len(b["war_ongoing"].legion_numbers) >= 2


# --------------------------------------------------------------------------- #
# C-AC11 — atomic rollback injection
# --------------------------------------------------------------------------- #

def test_atomic_rollback_on_apply_failure():
    b = build_r5_base(with_passive=False)
    state = b["state"]
    war_a = b["war_ongoing"]
    drafts = [command_draft(war_a.id, b["consul_id"], 1)]
    sub = _submit(state, drafts)
    assert sub["success"], sub.get("errors")
    _resolve(state)
    before = {
        "cmd": war_a.commander_id, "pool": _pool_size(state),
        "treasury": state.treasury, "phase": state.is_phase_executed("senate"),
        "status": war_a.status,
    }
    with patch.object(PoliticalSystem, "_strict_recruit_and_bind",
                      side_effect=RuntimeError("injected")):
        adv = senate_api.advance_senate_phase(state, FIXED["player"])
    assert not adv["success"]
    assert adv["data"]["committed"] is False
    # 12 域零部分变更（S0 深值保留）
    assert war_a.commander_id == before["cmd"]
    assert _pool_size(state) == before["pool"]
    assert state.treasury == before["treasury"]
    assert state.is_phase_executed("senate") == before["phase"]
    assert state.get_war_execution_receipt_for_session("S1") is None
    # 修复后同身份一次完整成功
    adv2 = senate_api.advance_senate_phase(state, FIXED["player"])
    assert adv2["success"], adv2


# --------------------------------------------------------------------------- #
# C-AC12 — empty E still processes PF
# --------------------------------------------------------------------------- #

def test_empty_package_still_processes_pending_fallback():
    b = build_r5_base(with_passive=False)
    state = b["state"]
    war_peace = b["war_peace"]
    sub = _submit(state, [])
    assert sub["success"], sub.get("errors")
    _resolve(state)
    adv = senate_api.advance_senate_phase(state, FIXED["player"])
    assert adv["success"], adv
    # 未提交 Peace → 终止 pending 草案 + TRUCE→ACTIVE
    assert war_peace.status.value == "active"
    assert war_peace.peace_treaty is None


# --------------------------------------------------------------------------- #
# C-AC13 — receipt exactly-once / replay
# --------------------------------------------------------------------------- #

def test_receipt_exactly_once_replay():
    b = build_r5_base(with_passive=False)
    state = b["state"]
    drafts = [command_draft(b["war_ongoing"].id, b["consul_id"], 1)]
    sub, res, adv = _boundary(b, drafts)
    assert adv["success"], adv
    assert adv["data"]["replayed"] is False
    pool_after = _pool_size(state)
    treasury_after = state.treasury
    # 第二次 advance：receipt 重放（不再部署）
    adv2 = senate_api.advance_senate_phase(state, FIXED["player"])
    assert adv2["success"]
    assert adv2["data"]["replayed"] is True
    assert _pool_size(state) == pool_after
    assert state.treasury == treasury_after


# --------------------------------------------------------------------------- #
# C-AC14 — drift recheck
# --------------------------------------------------------------------------- #

def test_drift_pending_universe_handled():
    b = build_r5_base(with_passive=False)
    state = b["state"]
    war_a = b["war_ongoing"]
    drafts = [command_draft(war_a.id, b["consul_id"], 0)]
    sub = _submit(state, drafts)
    assert sub["success"], sub.get("errors")
    _resolve(state)
    # 提交后真实 pending universe 变化：TT 新增一场 pending-peace war
    from src.tests.fixtures.wpgr4_fixtures import make_war, attach_truce
    from src.core.entities.war import WarStatus
    intruder = make_war("intruder_war", "Intruder", status=WarStatus.TRUCE,
                        treaty={"indemnity": 10, "duration": 2, "status": "pending",
                                "generated_turn": 1})
    attach_truce(state, intruder)
    adv = senate_api.advance_senate_phase(state, FIXED["player"])
    # 漂移的 pending universe：边界仍须处理它（不静默遗漏）——作为 PF 恢复
    assert adv["success"], adv
    assert intruder.status.value == "active"


# --------------------------------------------------------------------------- #
# C-AC15 / §20 #38 — no-op continue legal
# --------------------------------------------------------------------------- #

def test_noop_continue_legal_with_receipt():
    b = build_r5_base(with_passive=False)
    state = b["state"]
    war_a = b["war_ongoing"]
    drafts = [command_draft(war_a.id, war_a.commander_id, 0)]   # 同将 N=0
    sub, res, adv = _boundary(b, drafts)
    assert adv["success"], adv
    assert war_a.commander_id == b["cmd_a"].id
    assert state.get_war_execution_receipt_for_session("S1") is not None


# --------------------------------------------------------------------------- #
# C-AC16 — entry parity (human submit/resolve/advance vs direct core)
# --------------------------------------------------------------------------- #

def test_entry_parity_same_plan_fingerprint():
    b = build_r5_base(with_passive=False)
    state = b["state"]
    pol = PoliticalSystem(state)
    drafts = [command_draft(b["war_ongoing"].id, b["consul_id"], 0)]
    sub = _submit(state, drafts)
    assert sub["success"], sub.get("errors")
    _resolve(state)
    decisions = [d for (s, _p), d in state.get_war_decisions().items() if s == "S1"]
    assert len(decisions) == 1
    plan = pol.build_war_resolution_plan({
        "current_turn": 1, "session_id": "S1", "decisions": decisions,
        "real_wars": pol._real_wars(), "available_legion_ids": [],
        "pending_war_ids": [b["war_peace"].id]})
    assert plan["execution_id"] == "S1:senate_to_combat:v1"
    assert plan["final_commander_by_war"][b["war_ongoing"].id] == b["consul_id"]


# --------------------------------------------------------------------------- #
# C-AC17 — receipt priority over phase door; no mandatory door
# --------------------------------------------------------------------------- #

def test_receipt_replay_priority_over_phase_door():
    b = build_r5_base(with_passive=False)
    state = b["state"]
    drafts = [command_draft(b["war_ongoing"].id, b["consul_id"], 0)]
    sub, res, adv = _boundary(b, drafts)
    assert adv["success"], adv
    # phase 已 executed，但 receipt 重放优先（非 "already executed" 错误）
    adv2 = senate_api.advance_senate_phase(state, FIXED["player"])
    assert adv2["success"] and adv2["data"]["replayed"] is True


def test_no_mandatory_takeover_gate_blocks_settle():
    b = build_r5_base(with_passive=False)
    state = b["state"]
    b["war_ongoing"].commander_id = None       # commanderless ACTIVE（旧 mandatory 门会拒）
    sub = _submit(state, [])
    assert sub["success"], sub.get("errors")
    res = _resolve(state)
    assert res["success"]                       # 不因 mandatory 门拒绝结算
    adv = senate_api.advance_senate_phase(state, FIXED["player"])
    assert adv["success"], adv
