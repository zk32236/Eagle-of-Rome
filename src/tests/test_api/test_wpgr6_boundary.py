# src/tests/test_api/test_wpgr6_boundary.py
"""WP-G-R6 DA-3 B1（SA-Design v1.1 §C.1 / §C.4；DA-Plan §2 DA-3 B1）— 双输入 plan / receipt / identity。

本片独立验收面（严格限定 DA-3 B1 范围）：
- `build_war_resolution_plan` **显式双输入** `senate_decisions` / `consul_decisions`，
  集合定义 `V/D/AD/PE/EC/PT/PF` + assert（D 仅真实 War command；V command 只能 active；
  同 War 跨 route / 重复 intent 拒绝，**不 last-write-wins**）；
- receipt 追加 `direct_decision_refs`；`package_id` **从 PackageRecord 读**
  （direct-only / 空包下不得丢）；
- execution ID = `(session_id, package_id, senate_to_combat, protocol_version=2)`；
- input fingerprint 含全部 snapshots / outcomes / context 深值 + treaty 条款 + 协议版本，
  **order-independent**；
- 21 code 机器身份不变。

证据分类 = DATA（RENDER 归 SO；`〔r〕` 帧不在本批自产）。既有 R5 用例**不迁移**（归 DA-6 B1）。
"""
import os
import sys
import unittest
from unittest import mock

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(__file__))))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

from src.api import senate_api
from src.core.entities.war import WarStatus
from src.core.game_state import GameState, WarResolutionTransaction
from src.core.systems.military_system import MilitarySystem
from src.core.systems.political_system import (
    WAR_RESOLUTION_PROTOCOL_VERSION,
    PoliticalSystem,
)
from src.core.systems.war_system import WarSystem
from src.tests.fixtures.wpgr4_fixtures import add_ready_fleets, attach_truce, make_war
from src.tests.fixtures.wpgr5_fixtures import (
    FIXED,
    build_r5_base,
    command_draft,
    add_province,
    add_figure,
)
from src.tests.fixtures.wpgr6_fixtures import (
    build_f6_base,
    build_f6,
    pool_legion_ids,
    submit_api,
)

SUBMIT_ERROR_CODES_21 = (
    "SUBMIT_REQUEST_INVALID", "SUBMIT_NOT_AUTHORIZED", "SUBMIT_PHASE_INVALID",
    "PACKAGE_ALREADY_SUBMITTED", "SUBMIT_REQUEST_REUSED", "WAR_PROPOSAL_DUPLICATE",
    "WAR_TARGET_INVALID", "WAR_NOT_PROPOSABLE", "WAR_MODE_INVALID", "COMMANDER_REQUIRED",
    "COMMANDER_TARGET_INVALID", "COMMANDER_INELIGIBLE", "REINFORCEMENT_INVALID",
    "PEACE_DRAFT_INVALID", "COMMANDER_CLAIM_DUPLICATE", "GOVERNOR_COMMANDER_CONFLICT",
    "GOVERNOR_NOMINATION_DUPLICATE", "NON_WAR_PROPOSAL_INVALID", "LEGION_POOL_EXCEEDED",
    "SUBMIT_CONTEXT_CHANGED", "SUBMIT_PUBLISH_FAILED",
)


class _PassDecider:
    def decide_vote(self, issue, faction, state):
        return True


def _senate_decision(war_id, target, n, source="active_declaration", proposal_id=1):
    return {"proposal_id": proposal_id, "war_id": war_id, "outcome": "ENACTED",
            "mode": "command", "source": source,
            "payload": {"target_commander_id": target, "reinforcement_n": n},
            "snapshot_ref": {}}


def _direct_decision(war_id, target, n, direct_id="cd-1"):
    return {"direct_decision_id": direct_id, "war_id": war_id, "mode": "command",
            "source": "ongoing", "authority": "consul_direct", "decision_state": "FROZEN",
            "payload": {"target_commander_id": target, "reinforcement_n": n},
            "snapshot_ref": {"kind": "consul_direct", "direct_decision_id": direct_id}}


def _resolve_and_advance(state):
    res = senate_api.resolve_senate(state, vote_decider=_PassDecider())
    assert res["success"], res.get("message")
    return senate_api.advance_senate_phase(state, FIXED["player"])


class TestPlanExplicitDualInput(unittest.TestCase):
    """Exit (a)：显式双输入 + V/D/AD/PE/EC/PT/PF + assert。"""

    def test_sets_from_authentic_mixed_session(self):
        """F6-MIX（1 direct ongoing + 1 Senate threat + unchecked pending-peace）逐集合实测。"""
        ctx = build_f6("F6-MIX")
        state = ctx["state"]
        sub = submit_api(state, ctx["drafts"])
        self.assertTrue(sub["success"], sub.get("errors"))
        res = senate_api.resolve_senate(state, vote_decider=_PassDecider())
        self.assertTrue(res["success"], res.get("message"))
        decisions = [d for (s, _p), d in state.get_war_decisions().items() if s == "S1"]
        consul = list(state.get_consul_war_decisions("S1").values())
        pol = PoliticalSystem(state)
        plan = pol.build_war_resolution_plan(
            decisions, consul, current_turn=1, session_id="S1",
            real_wars=pol._real_wars(), available_legion_ids=pool_legion_ids(state),
            pending_war_ids=[FIXED["war_peace"]], package_id=sub["data"]["package_id"])

        threat, ongoing, peace = FIXED["war_threat"], FIXED["war_ongoing"], FIXED["war_peace"]
        # V = ENACTED Senate；AD 仅 active_declaration；PE 空（本包未选 peace）
        self.assertEqual([d["war_id"] for d in plan["enacted"]], [threat])
        self.assertEqual(plan["activation_set"], [threat])
        self.assertEqual(plan["peace_set"], [])
        # D = FROZEN direct（仅真实 War command）
        self.assertEqual(plan["direct_set"], [ongoing])
        # EC = command intents(V) ∪ D
        self.assertEqual(plan["command_set"], sorted([threat, ongoing]))
        # PT = 冻结输入 pending-peace；PF = PT − PE
        self.assertEqual(plan["pending_peace_set"], [peace])
        self.assertEqual(plan["pending_fallback_set"], [peace])
        # 未勾选真实 War 的 current claim 仍在 R（保留原将）
        self.assertEqual(plan["final_commander_by_war"][peace], ctx["cmd_b"].id)
        self.assertEqual(plan["input_conflicts"], [])

    def test_direct_must_be_real_war_command(self):
        pol = PoliticalSystem(build_f6_base()["state"])
        plan = pol.build_war_resolution_plan(
            [], [_direct_decision("not_a_real_war", 1, 0),
                 _direct_decision(FIXED["war_ongoing"], 1, 0, direct_id="cd-2")],
            current_turn=1, session_id="S1")
        kinds = sorted(c["kind"] for c in plan["input_conflicts"])
        self.assertIn("direct_not_real_war", kinds)
        self.assertNotIn("direct_not_command", kinds)

    def test_direct_cannot_be_peace_mode(self):
        pol = PoliticalSystem(build_f6_base()["state"])
        bad = _direct_decision(FIXED["war_ongoing"], 1, 0)
        bad["mode"] = "peace"
        plan = pol.build_war_resolution_plan([], [bad], current_turn=1, session_id="S1")
        self.assertIn("direct_not_command", [c["kind"] for c in plan["input_conflicts"]])

    def test_direct_conflicting_with_peace_set_rejected(self):
        b = build_f6_base()
        pol = PoliticalSystem(b["state"])
        peace_v = {"proposal_id": 9, "war_id": FIXED["war_peace"], "outcome": "ENACTED",
                   "mode": "peace", "source": "pending_peace",
                   "payload": {"treaty_snapshot": {}}, "snapshot_ref": {}}
        direct = _direct_decision(FIXED["war_peace"], b["cmd_a"].id, 0)
        plan = pol.build_war_resolution_plan(
            [peace_v], [direct], current_turn=1, session_id="S1",
            real_wars=pol._real_wars(), pending_war_ids=[FIXED["war_peace"]])
        kinds = [c["kind"] for c in plan["input_conflicts"]]
        self.assertIn("direct_peace_conflict", kinds)
        self.assertIn("cross_route_conflict", kinds)

    def test_senate_command_must_be_active_declaration(self):
        b = build_f6_base()
        pol = PoliticalSystem(b["state"])
        plan = pol.build_war_resolution_plan(
            [_senate_decision(FIXED["war_ongoing"], b["cmd_b"].id, 0, source="ongoing")],
            [], current_turn=1, session_id="S1", real_wars=pol._real_wars())
        self.assertIn("senate_command_not_active", [c["kind"] for c in plan["input_conflicts"]])
        # 拒绝 ≠ 静默丢弃：该 War 不进入 activation_set
        self.assertEqual(plan["activation_set"], [])

    def test_senate_peace_must_be_pending(self):
        b = build_f6_base()
        pol = PoliticalSystem(b["state"])
        peace_v = {"proposal_id": 4, "war_id": FIXED["war_ongoing"], "outcome": "ENACTED",
                   "mode": "peace", "source": "pending_peace",
                   "payload": {"treaty_snapshot": {}}, "snapshot_ref": {}}
        plan = pol.build_war_resolution_plan(
            [peace_v], [], current_turn=1, session_id="S1", real_wars=pol._real_wars(),
            pending_war_ids=[FIXED["war_peace"]])
        self.assertIn("senate_peace_not_pending", [c["kind"] for c in plan["input_conflicts"]])

    def test_cross_route_and_duplicate_intent_not_last_write_wins(self):
        """同 War 跨 route + 重复 intent → 均登记冲突；结果与输入顺序无关（无覆写）。"""
        b = build_f6_base()
        pol = PoliticalSystem(b["state"])
        v = [_senate_decision(FIXED["war_ongoing"], b["cmd_b"].id, 1)]
        d = [_direct_decision(FIXED["war_ongoing"], b["cmd_a"].id, 0),
             _direct_decision(FIXED["war_ongoing"], b["consul_id"], 3, direct_id="cd-3")]
        p1 = pol.build_war_resolution_plan(v, list(reversed(d)), current_turn=1,
                                           session_id="S1", real_wars=pol._real_wars())
        p2 = pol.build_war_resolution_plan(list(v), d, current_turn=1, session_id="S1",
                                           real_wars=pol._real_wars())
        kinds = sorted(c["kind"] for c in p1["input_conflicts"])
        self.assertIn("cross_route_conflict", kinds)
        self.assertIn("duplicate_direct_intent", kinds)
        # 不 last-write-wins：两种顺序得到同一 final commander / allocations
        self.assertEqual(p1["final_commander_by_war"], p2["final_commander_by_war"])
        self.assertEqual(p1["reinforcement_allocations"], p2["reinforcement_allocations"])

    def test_legacy_container_call_still_supported(self):
        """旧容器式调用（R5 形状）兼容保留，但不再承载 direct 输入。"""
        b = build_r5_base(with_passive=False)
        pol = PoliticalSystem(b["state"])
        plan = pol.build_war_resolution_plan({
            "current_turn": 1, "session_id": "S1",
            "decisions": [_senate_decision(FIXED["war_ongoing"], b["cmd_b"].id, 0)],
            "real_wars": pol._real_wars(), "available_legion_ids": [],
            "pending_war_ids": [FIXED["war_peace"]]})
        self.assertEqual(plan["final_commander_by_war"][FIXED["war_ongoing"]], b["cmd_b"].id)
        self.assertEqual(plan["direct_set"], [])

    def test_legacy_container_accepts_consul_decisions_key(self):
        b = build_f6_base()
        pol = PoliticalSystem(b["state"])
        plan = pol.build_war_resolution_plan({
            "current_turn": 1, "session_id": "S1", "decisions": [],
            "consul_decisions": [_direct_decision(FIXED["war_ongoing"], b["cmd_b"].id, 0)],
            "real_wars": pol._real_wars()})
        self.assertEqual(plan["command_set"], [FIXED["war_ongoing"]])
        self.assertEqual(plan["final_commander_by_war"][FIXED["war_ongoing"]], b["cmd_b"].id)


class TestInputFingerprint(unittest.TestCase):
    """Exit (c)：fingerprint 覆盖全部输入深值 + 协议版本；order-independent。"""

    def test_order_independent(self):
        b = build_f6_base()
        pol = PoliticalSystem(b["state"])
        v = [_senate_decision(FIXED["war_threat"], b["consul_id"], 1, proposal_id=1)]
        d = [_direct_decision(FIXED["war_ongoing"], b["cmd_b"].id, 1, direct_id="cd-1"),
             _direct_decision(FIXED["war_peace"], b["cmd_a"].id, 2, direct_id="cd-2")]
        kw = dict(current_turn=1, session_id="S1", real_wars=pol._real_wars(),
                  available_legion_ids=pool_legion_ids(b["state"]),
                  pending_war_ids=[FIXED["war_peace"]], package_id="pkg-1")
        p1 = pol.build_war_resolution_plan(list(v), list(d), **kw)
        p2 = pol.build_war_resolution_plan(list(reversed(v)), list(reversed(d)), **kw)
        self.assertEqual(p1["input_fingerprint"], p2["input_fingerprint"])
        self.assertEqual(p1["execution_id"], p2["execution_id"])
        self.assertEqual(p1["final_commander_by_war"], p2["final_commander_by_war"])
        self.assertEqual(p1["treaty_effects"], p2["treaty_effects"])

    def test_covers_treaty_deep_values_and_context(self):
        b = build_f6_base()
        pol = PoliticalSystem(b["state"])
        peace_v = [{"proposal_id": 7, "war_id": FIXED["war_peace"], "outcome": "ENACTED",
                    "mode": "peace", "source": "pending_peace",
                    "payload": {"treaty_snapshot": {"indemnity": 80, "duration": 3,
                                                    "status": "pending"}},
                    "snapshot_ref": {"proposal_id": 7}}]
        kw = dict(current_turn=1, session_id="S1", real_wars=pol._real_wars(),
                  pending_war_ids=[FIXED["war_peace"]], package_id="pkg-1")
        base = pol.build_war_resolution_plan(peace_v, [], **kw)
        # treaty 条款深值变化（±1 赔款）→ 指纹变化
        tweaked = [dict(peace_v[0])]
        tweaked[0]["payload"] = {"treaty_snapshot": {"indemnity": 81, "duration": 3,
                                                     "status": "pending"}}
        self.assertNotEqual(base["input_fingerprint"],
                            pol.build_war_resolution_plan(tweaked, [], **kw)["input_fingerprint"])
        # context 深值变化 → 指纹变化
        with_ctx = pol.build_war_resolution_plan(
            peace_v, [], submission_context={"wars": {FIXED["war_peace"]: {"status": "TRUCE"}}},
            **kw)
        self.assertNotEqual(base["input_fingerprint"], with_ctx["input_fingerprint"])
        # 协议版本变化 → 指纹变化
        v3 = pol.build_war_resolution_plan(peace_v, [], protocol_version=3, **kw)
        self.assertNotEqual(base["input_fingerprint"], v3["input_fingerprint"])
        self.assertEqual(base["protocol_version"], WAR_RESOLUTION_PROTOCOL_VERSION)

    def test_direct_snapshot_identity_participates(self):
        b = build_f6_base()
        pol = PoliticalSystem(b["state"])
        kw = dict(current_turn=1, session_id="S1", real_wars=pol._real_wars())
        d1 = [_direct_decision(FIXED["war_ongoing"], b["cmd_b"].id, 0, direct_id="cd-1")]
        d2 = [_direct_decision(FIXED["war_ongoing"], b["cmd_b"].id, 0, direct_id="cd-2")]
        self.assertNotEqual(
            pol.build_war_resolution_plan([], d1, **kw)["input_fingerprint"],
            pol.build_war_resolution_plan([], d2, **kw)["input_fingerprint"])


class TestExecutionIdentityAndReceipt(unittest.TestCase):
    """Exit (a)(b)：execution ID 复合身份 + receipt `direct_decision_refs` + package_id 来源。"""

    def test_execution_id_tuple_form(self):
        b = build_f6_base()
        pol = PoliticalSystem(b["state"])
        plan = pol.build_war_resolution_plan(
            [], [_direct_decision(FIXED["war_ongoing"], b["cmd_b"].id, 0)],
            current_turn=1, session_id="S1", package_id="pkg-9",
            protocol_version=WAR_RESOLUTION_PROTOCOL_VERSION)
        self.assertEqual(plan["execution_id"], "S1:pkg-9:senate_to_combat:v2")
        self.assertEqual(plan["protocol_version"], 2)

    def test_boundary_consumes_direct_and_writes_receipt_refs(self):
        """F6-DD（direct-only，零 Senate 提案）→ 边界消费 direct + receipt 身份实测。"""
        ctx = build_f6("F6-DD")
        state = ctx["state"]
        sub = submit_api(state, ctx["drafts"])
        self.assertTrue(sub["success"], sub.get("errors"))
        package_id = sub["data"]["package_id"]
        direct_ids = sorted(d["direct_decision_id"] for d in sub["data"]["direct_decisions"])
        # 前置：direct-only ⇒ 零 Senate 提案（baseline「从第一条 Senate decision 找 package_id」会丢）
        self.assertEqual(state.get_senate_proposals(), [])
        pool_before = pool_legion_ids(state)

        adv = _resolve_and_advance(state)
        self.assertTrue(adv["success"], adv.get("message"))
        receipt = state.get_war_execution_receipt(adv["data"]["execution_id"])
        self.assertIsNotNone(receipt)
        # (b) package_id 从 PackageRecord 读（= Submit 返回的 package_id）
        record = state.get_senate_package_record(package_id)
        self.assertIsNotNone(record)
        self.assertEqual(receipt["package_id"], package_id)
        self.assertEqual(receipt["package_id"], record["package_id"])
        # (b) receipt 追加 direct_decision_refs（无 proposal_id）
        self.assertEqual([r["direct_decision_id"] for r in receipt["direct_decision_refs"]],
                         direct_ids)
        for ref in receipt["direct_decision_refs"]:
            self.assertIsNone(ref.get("proposal_id"))
        self.assertEqual(receipt["proposal_refs"], [])
        # (a) 执行身份 = (session_id, package_id, senate_to_combat, protocol_version=2)
        self.assertEqual(receipt["execution_id"],
                         f"S1:{package_id}:senate_to_combat:v2")
        self.assertEqual(receipt["protocol_version"], 2)
        # direct 被边界消费（Submit 零军事写 → 边界一次生效）
        self.assertEqual(ctx["war_ongoing"].commander_id, ctx["cmd_a"].id)
        self.assertEqual(ctx["war_peace"].commander_id, ctx["cmd_b"].id)
        self.assertEqual(ctx["war_peace"].status.value, "active")
        self.assertEqual(len(pool_legion_ids(state)), len(pool_before) - 3)

    def test_replay_same_execution_id_zero_redeploy(self):
        ctx = build_f6("F6-DD")
        state = ctx["state"]
        submit_api(state, ctx["drafts"])
        adv = _resolve_and_advance(state)
        self.assertTrue(adv["success"], adv.get("message"))
        self.assertFalse(adv["data"]["replayed"])
        pool_after = pool_legion_ids(state)
        adv2 = senate_api.advance_senate_phase(state, FIXED["player"])
        self.assertTrue(adv2["success"])
        self.assertTrue(adv2["data"]["replayed"])
        self.assertEqual(adv2["data"]["execution_id"], adv["data"]["execution_id"])
        self.assertEqual(pool_legion_ids(state), pool_after)

    def test_boundary_rejects_input_conflicts_zero_military_write(self):
        """跨 route 冲突（同一 War 同时是 Senate 决定与 FROZEN direct）→ 拒绝 + 零军事写。"""
        b = build_f6_base()
        state = b["state"]
        state.set_senate_session("S1")
        state.record_war_decision("S1", 1, {
            "proposal_id": 1, "war_id": FIXED["war_ongoing"], "outcome": "ENACTED",
            "mode": "command", "source": "active_declaration",
            "payload": {"target_commander_id": b["cmd_b"].id, "reinforcement_n": 0},
            "snapshot_ref": {}})
        self.assertTrue(state.register_consul_war_decision({
            "direct_decision_id": "cd-x", "war_id": FIXED["war_ongoing"], "mode": "command",
            "source": "ongoing", "senate_session_id": "S1", "package_id": "pkg-x",
            "payload": {"target_commander_id": b["consul_id"], "reinforcement_n": 0},
            "snapshot_ref": {"kind": "consul_direct", "direct_decision_id": "cd-x"}}))
        before = {"cmd": b["war_ongoing"].commander_id, "pool": pool_legion_ids(state),
                  "treasury": state.treasury, "phase": state.is_phase_executed("senate")}

        result = senate_api._execute_war_resolution_boundary(state, FIXED["player"])

        self.assertFalse(result["success"])
        self.assertEqual(result["data"]["code"], "WAR_EXECUTION_INPUT_INVALID")
        self.assertIn("cross_route_conflict",
                      [c["kind"] for c in result["data"]["offending_refs"]])
        self.assertEqual(b["war_ongoing"].commander_id, before["cmd"])
        self.assertEqual(pool_legion_ids(state), before["pool"])
        self.assertEqual(state.treasury, before["treasury"])
        self.assertEqual(state.is_phase_executed("senate"), before["phase"])
        self.assertIsNone(state.get_war_execution_receipt_for_session("S1"))


class TestIdentityPreservation(unittest.TestCase):
    """Exit：21 code 身份不变；本批未新增/改名/删除任何 code。"""

    def test_21_code_machine_identity_unchanged(self):
        self.assertEqual(tuple(PoliticalSystem._SUBMIT_ERROR_CODES), SUBMIT_ERROR_CODES_21)
        self.assertEqual(len(PoliticalSystem._SUBMIT_ERROR_CODES), 21)


# --------------------------------------------------------------------------- #
# DA-3 B2（SA v1.1 §C.3 / §C.1）— 12 域原子 + 故障注入 + PT 口径收口
# --------------------------------------------------------------------------- #
def _prepared(fixture_name):
    """提交 + resolve（投票通过），返回可 advance 的 ctx（边界 S0 = 此处）。"""
    ctx = build_f6(fixture_name)
    state = ctx["state"]
    sub = submit_api(state, ctx["drafts"])
    assert sub["success"], sub.get("errors")
    res = senate_api.resolve_senate(state, vote_decider=_PassDecider())
    assert res["success"], res.get("message")
    return ctx


class TestCommitRequiresTransaction(unittest.TestCase):
    """Exit (a)：`commit_war_resolution(plan, transaction=None)` 直接调用 = 拒绝执行（§C.3）。"""

    def _plan(self, ctx):
        state = ctx["state"]
        pol = PoliticalSystem(state)
        return pol, pol.build_war_resolution_plan(
            [], [_direct_decision(FIXED["war_ongoing"], ctx["cmd_b"].id, 2)],
            current_turn=1, session_id="S1", real_wars=pol._real_wars(),
            available_legion_ids=pool_legion_ids(state),
            pending_war_ids=[FIXED["war_peace"]])

    def test_direct_call_none_transaction_refused_zero_write(self):
        ctx = build_f6_base()
        state = ctx["state"]
        pol, plan = self._plan(ctx)
        before = state.snapshot_war_resolution_domains()
        with self.assertRaises(RuntimeError) as cm:
            pol.commit_war_resolution(plan)          # transaction=None
        self.assertIn("war_resolution_transaction_required", str(cm.exception))
        # 零军事写：12 域深值完全保留
        self.assertEqual(state.snapshot_war_resolution_domains(), before)

    def test_unheld_or_state_mismatch_transaction_refused(self):
        ctx = build_f6_base()
        other = build_f6_base()
        state = ctx["state"]
        pol, plan = self._plan(ctx)
        before = state.snapshot_war_resolution_domains()
        # 未进入（未持锁）的事务 → 拒绝
        with self.assertRaises(RuntimeError) as cm1:
            pol.commit_war_resolution(plan, WarResolutionTransaction(state))
        self.assertIn("war_resolution_transaction_not_held", str(cm1.exception))
        # 绑定到别的 state 的事务 → 拒绝
        stray = WarResolutionTransaction(other["state"])
        stray._acquired = True  # 伪造持锁，仍须被 state 身份校验拒绝
        with self.assertRaises(RuntimeError) as cm2:
            pol.commit_war_resolution(plan, stray)
        self.assertIn("war_resolution_transaction_state_mismatch", str(cm2.exception))
        self.assertEqual(state.snapshot_war_resolution_domains(), before)

    def test_session_mismatch_transaction_refused(self):
        ctx = build_f6_base()
        state = ctx["state"]
        state.set_senate_session("S9")
        pol, plan = self._plan(ctx)                       # plan.session_id == "S1"
        txn = WarResolutionTransaction(state)
        txn._acquired = True
        with self.assertRaises(RuntimeError) as cm:
            pol.commit_war_resolution(plan, txn)
        self.assertIn("war_resolution_session_mismatch", str(cm.exception))


class TestFaultMatrixAtomicRecovery(unittest.TestCase):
    """Exit (a)：逐子步 / receipt / phase 故障注入 ⇒ 12 域全部恢复（无部分生效）。"""

    _RAISING_FAULTS = (
        ("peace_effect", "F6-VV", PoliticalSystem, "_apply_peace_effects"),
        ("activation", "F6-MIX", WarSystem, "activate_war"),
        ("pending_fallback", "F6-MIX", WarSystem, "move_truce_war_to_active"),
        ("recruit_strict", "F6-DD", PoliticalSystem, "_strict_recruit_and_bind"),
        ("receipt_write", "F6-DD", GameState, "record_war_execution_receipt"),
        ("phase_mark", "F6-DD", GameState, "mark_phase_executed"),
        ("commit_point", "F6-DD", WarResolutionTransaction, "commit"),
    )

    def _assert_full_recovery(self, fixture, target, attr, patch_kw):
        ctx = _prepared(fixture)
        state = ctx["state"]
        before = state.snapshot_war_resolution_domains()
        with mock.patch.object(target, attr, **patch_kw):
            adv = senate_api.advance_senate_phase(state, FIXED["player"])
        self.assertFalse(adv["success"], adv.get("message"))
        self.assertEqual(adv["data"]["code"], "WAR_EXECUTION_APPLY_FAILED")
        # 12 域深值完全相等 = 零部分生效
        self.assertEqual(state.snapshot_war_resolution_domains(), before)
        self.assertIsNone(state.get_war_execution_receipt_for_session("S1"))
        self.assertFalse(state.is_phase_executed("senate"))
        return state

    def test_each_substep_exception_rolls_back_all_12_domains(self):
        for label, fixture, target, attr in self._RAISING_FAULTS:
            with self.subTest(fault=label):
                self._assert_full_recovery(fixture, target, attr,
                                           {"side_effect": RuntimeError(f"inject:{label}")})

    def test_false_return_and_assign_shortfall_are_faults(self):
        # false 后条件（fallback 移动失败）
        self._assert_full_recovery("F6-MIX", WarSystem, "move_truce_war_to_active",
                                   {"return_value": False})
        # 少募 / assign count mismatch（严格恰 N）
        self._assert_full_recovery("F6-DD", MilitarySystem, "assign_to_war",
                                   {"return_value": (0, "injected")})

    def test_empty_package_fault_recovery(self):
        """空包形态：无任何 checked 卡 ⇒ 仍须原子（故障 → 全域恢复）。"""
        ctx = build_f6_base()
        state = ctx["state"]
        drafts = [command_draft(FIXED["war_ongoing"], ctx["cmd_a"].id, 0, checked=False)]
        sub = submit_api(state, drafts)
        self.assertTrue(sub["success"], sub.get("errors"))
        self.assertTrue(senate_api.resolve_senate(state, vote_decider=_PassDecider())["success"])
        before = state.snapshot_war_resolution_domains()
        with mock.patch.object(GameState, "record_war_execution_receipt",
                               side_effect=RuntimeError("inject:empty")):
            adv = senate_api.advance_senate_phase(state, FIXED["player"])
        self.assertFalse(adv["success"])
        self.assertEqual(adv["data"]["code"], "WAR_EXECUTION_APPLY_FAILED")
        self.assertEqual(state.snapshot_war_resolution_domains(), before)

    def test_retry_same_identity_after_full_rollback(self):
        """回滚后可同身份重试：同 execution_id、恰一次生效。"""
        ctx = _prepared("F6-DD")
        state = ctx["state"]
        with mock.patch.object(GameState, "mark_phase_executed", side_effect=RuntimeError("x")):
            first = senate_api.advance_senate_phase(state, FIXED["player"])
        self.assertFalse(first["success"])
        second = senate_api.advance_senate_phase(state, FIXED["player"])
        self.assertTrue(second["success"], second.get("message"))
        self.assertEqual(second["data"]["execution_id"], first["data"]["execution_id"])
        self.assertFalse(second["data"]["replayed"])
        self.assertEqual(len(pool_legion_ids(state)), len(ctx["pool_ids"]) - 3)  # ΣN=3 恰一次


class TestLockWindowNoExternalObserver(unittest.TestCase):
    """Exit (a)：持锁期禁止 external observer（fail-closed）；半部署事实不可见。"""

    def test_external_observer_blocked_during_lock_window(self):
        ctx = _prepared("F6-DD")
        state = ctx["state"]
        observed = {}
        orig = PoliticalSystem._strict_recruit_and_bind

        def probe(self_, war, commander_id, planned_ids):
            try:
                state.acquire_senate_transaction("external_observer")
                observed["blocked"] = False
                state.release_senate_transaction("external_observer")
            except RuntimeError as exc:
                observed["blocked"] = True
                observed["error"] = str(exc)
            # 持锁期：receipt / phase 等半部署事实尚不可外部观察
            observed["receipt_visible"] = (
                state.get_war_execution_receipt_for_session("S1") is not None)
            observed["phase_marked"] = state.is_phase_executed("senate")
            return orig(self_, war, commander_id, planned_ids)

        with mock.patch.object(PoliticalSystem, "_strict_recruit_and_bind", probe):
            adv = senate_api.advance_senate_phase(state, FIXED["player"])
        self.assertTrue(adv["success"], adv.get("message"))
        self.assertTrue(observed.get("blocked"))
        self.assertIn("non-reentrant", observed.get("error", ""))
        self.assertFalse(observed.get("receipt_visible"))
        self.assertFalse(observed.get("phase_marked"))

    def test_lock_released_after_rollback(self):
        """故障回滚后锁必须释放（可再次进入事务，不残留 owner）。"""
        ctx = _prepared("F6-DD")
        state = ctx["state"]
        with mock.patch.object(GameState, "record_war_execution_receipt",
                               side_effect=RuntimeError("x")):
            self.assertFalse(senate_api.advance_senate_phase(state, FIXED["player"])["success"])
        self.assertIsNone(state._senate_transaction_owner)
        state.acquire_senate_transaction("probe")
        state.release_senate_transaction("probe")


class TestSnapshotDomainClosure(unittest.TestCase):
    """Exit (b)：`snapshot_war_resolution_domains` 覆盖新增字段与 helper 可达写域。"""

    def test_war_entity_fields_roundtrip(self):
        """War.assigned_fleet_ids / legions_assigned / fleets_assigned 必须被捕获并精确恢复。"""
        ctx = build_f6_base()
        state = ctx["state"]
        war = ctx["war_ongoing"]
        war._assigned_fleet_ids[:] = [5, 6]
        war.legions_assigned = 4
        war.fleets_assigned = 2
        snap = state.snapshot_war_resolution_domains()
        # 后置突变
        war.remove_fleet(5)
        war._assigned_fleet_ids.append(9)
        war.legions_assigned = 99
        war.fleets_assigned = 99
        state.restore_war_resolution_domains(snap)
        self.assertEqual(war.assigned_fleet_ids, [5, 6])
        self.assertEqual(war.legions_assigned, 4)
        self.assertEqual(war.fleets_assigned, 2)

    def test_snapshot_records_war_entity_fields(self):
        ctx = build_f6_base()
        state = ctx["state"]
        war = ctx["war_ongoing"]
        war._assigned_fleet_ids[:] = [3]
        war.legions_assigned = 7
        war.fleets_assigned = 1
        row = state.snapshot_war_resolution_domains()["wars"][war.id]
        self.assertEqual(row["assigned_fleet_ids"], [3])
        self.assertEqual(row["legions_assigned"], 7)
        self.assertEqual(row["fleets_assigned"], 1)

    def test_peace_recall_fault_rolls_back_fleet_binding(self):
        """真实 PE 路径：`_apply_peace_effects` → naval recall → war.remove_fleet；
        后续子步故障 ⇒ 舰队绑定必须回滚（证明可达写域被覆盖）。"""
        ctx = _prepared("F6-VV")                       # peace on war_peace（PE 效果）
        state = ctx["state"]
        peace = ctx["war_peace"]
        peace._naval_required = True
        fleets = add_ready_fleets(state, peace, count=1)
        num = fleets[0].number
        self.assertEqual(peace.assigned_fleet_ids, [num])
        before = state.snapshot_war_resolution_domains()
        with mock.patch.object(GameState, "mark_phase_executed", side_effect=RuntimeError("x")):
            adv = senate_api.advance_senate_phase(state, FIXED["player"])
        self.assertFalse(adv["success"])
        self.assertEqual(state.snapshot_war_resolution_domains(), before)
        self.assertEqual(peace.assigned_fleet_ids, [num])   # recall 被回滚
        self.assertEqual(fleets[0].assigned_war_id, peace.id)
        # 正控：同一场景无故障 → PE recall 确实清空 war 侧绑定（证明路径非空转）
        ctx2 = _prepared("F6-VV")
        state2, peace2 = ctx2["state"], ctx2["war_peace"]
        peace2._naval_required = True
        f2 = add_ready_fleets(state2, peace2, count=1)
        self.assertEqual(peace2.assigned_fleet_ids, [f2[0].number])
        adv2 = senate_api.advance_senate_phase(state2, FIXED["player"])
        self.assertTrue(adv2["success"], adv2.get("message"))
        self.assertEqual(peace2.assigned_fleet_ids, [])

    def test_senate_session_id_owned_by_publication_domain_only(self):
        """`_senate_session_id` 不在解析域（由 B3 publication 域负责）→ 无重叠所有权。"""
        ctx = build_f6_base()
        state = ctx["state"]
        state.set_senate_session("S1")
        war_snap = state.snapshot_war_resolution_domains()
        self.assertNotIn("senate_session_id", war_snap)
        pub = state.snapshot_senate_publication_domains()
        self.assertIn("senate_session_id", pub)
        state.set_senate_session("S-other")
        state.restore_senate_publication_domains(pub)
        self.assertEqual(state.get_senate_session(), "S1")

    def test_boundary_never_mutates_senate_session_identity(self):
        ctx = _prepared("F6-DD")
        state = ctx["state"]
        self.assertEqual(state.get_senate_session(), "S1")
        with mock.patch.object(GameState, "mark_phase_executed", side_effect=RuntimeError("x")):
            self.assertFalse(senate_api.advance_senate_phase(state, FIXED["player"])["success"])
        self.assertEqual(state.get_senate_session(), "S1")
        self.assertTrue(senate_api.advance_senate_phase(state, FIXED["player"])["success"])
        self.assertEqual(state.get_senate_session(), "S1")


class TestFrozenPT(unittest.TestCase):
    """Exit (c)：`PT` = frozen Context 的真实 pending-peace War（非边界当次 live）。"""

    def test_pt_from_frozen_context_not_live(self):
        b = build_r5_base(with_passive=False)
        state = b["state"]
        drafts = [command_draft(b["war_ongoing"].id, b["consul_id"], 0)]
        sub = senate_api.propose_many(state, FIXED["player"], {"war_drafts": drafts})
        self.assertTrue(sub["success"], sub.get("errors"))
        self.assertTrue(senate_api.resolve_senate(state, vote_decider=_PassDecider())["success"])
        # 提交后漂移：新增一场 pending-peace War（不属于冻结面）
        intruder = make_war("intruder_war", "Intruder", status=WarStatus.TRUCE,
                            treaty={"indemnity": 10, "duration": 2, "status": "pending",
                                    "generated_turn": 1})
        attach_truce(state, intruder)
        adv = senate_api.advance_senate_phase(state, FIXED["player"])
        self.assertTrue(adv["success"], adv.get("message"))
        receipt = state.get_war_execution_receipt(adv["data"]["execution_id"])
        self.assertEqual(receipt["pt_source"], "frozen_context")
        # 冻结时即存在的 pending-peace（war_peace）→ PF 恢复 ACTIVE
        self.assertIn(b["war_peace"].id, receipt["pending_fallback_war_ids"])
        self.assertEqual(b["war_peace"].status.value, "active")
        # 漂移新增者不在冻结 PT/PF → 不静默吸收（口径唯一性）
        self.assertNotIn("intruder_war", receipt["pending_fallback_war_ids"])
        self.assertEqual(intruder.status.value, "truce")

    def test_legacy_path_without_context_uses_live_fallback(self):
        """无冻结上下文（无包/legacy）→ 回退 live（显式登记，不静默）。"""
        from src.api.senate_api import _frozen_pending_peace_ids
        self.assertIsNone(_frozen_pending_peace_ids(None))
        self.assertIsNone(_frozen_pending_peace_ids({}))
        ctx = build_f6_base()
        frozen = {ctx["war_peace"].id: {"status": "truce",
                                        "peace_treaty": {"status": "pending"}}}
        self.assertEqual(_frozen_pending_peace_ids({"wars": frozen}), [ctx["war_peace"].id])


# ===========================================================================
# DA-3 B3（SA v1.1 §C.2.1 / §C.2.2 / §C.5.1）：冻结层/自动层分离 + hook 集成契约
# ===========================================================================

def _restrict_pool(state, keep_numbers):
    """把权威池限制为 `keep_numbers`（其余真实实体置 DESTROYED，仅改池口径）。"""
    from src.core.entities.legion import LegionStatus
    ms = state.get_military_system()
    keep = set(keep_numbers)
    for legion in list(ms._legions):
        if legion.number not in keep and legion.status in (
                LegionStatus.UNRAISED, LegionStatus.DISBANDED):
            legion.status = LegionStatus.DESTROYED


def _add_available_fleets(state, numbers):
    """真实 NavalSystem 实体、状态 AVAILABLE（未指派）——自动层舰队残量面。"""
    from src.core.entities.fleet import Fleet, FleetStatus
    ns = state.naval_system
    out = []
    for number in numbers:
        fleet = Fleet(number=number, fleet_type="trireme")
        fleet._strength_base = 3
        fleet._status = FleetStatus.AVAILABLE
        ns._fleets[number] = fleet
        out.append(fleet)
    return out


def _add_rebellion(state, province_id=991, governor_id=None):
    """新增 commanderless 起义（province governor = 自动层候选）+ 登记 active。"""
    from src.core.entities.province import Province
    ws = state.get_war_system()
    province = Province(province_id=province_id, name=f"Rebel Province {province_id}",
                        total_land=1000, conquered=True,
                        governor_id=governor_id, governor_designate_id=None)
    state.add_province(province)
    war = ws.create_rebellion_war(province)
    ws._active_wars.append(war)
    return war


def _effect_summary(state, adv):
    receipt = state.get_war_execution_receipt(adv["data"]["execution_id"])
    return receipt["effect_summary"]


class TestFrozenAutomaticLayerSeparation(unittest.TestCase):
    """Exit：自动层用 `available_pool_residual`；残量不足 → defer（零失败/不重试）。"""

    def _n21_setup(self, keep_pool=None):
        ctx = _prepared("F6-DD")               # Submit + resolve（边界 S0）
        state = ctx["state"]
        if keep_pool is not None:
            _restrict_pool(state, pool_legion_ids(state)[:keep_pool])
        rebellion = _add_rebellion(state, governor_id=ctx["cmd_gov"].id)
        return ctx, state, rebellion

    def test_n21_residual_exhausted_defers_rebellion_zero_failure_no_retry(self):
        """N21（C.2.2 反例①）：池 3 + direct ΣN=3 + 未选 commanderless 起义请求 2。

        唯一后条件：包成功、冻结恰额、`retained_effects_deferred=[{rebellion, RESIDUAL_POOL_EXHAUSTED}]`、
        起义本轮 commanderless/0 兵；**不是 CONTEXT_CHANGED、不是包失败、不重试**（P-1 方向 A）。
        """
        ctx, state, rebellion = self._n21_setup(keep_pool=3)
        self.assertEqual(len(pool_legion_ids(state)), 3)          # ΣN=3 ≤ 池 3（Submit 已冻结）
        adv = senate_api.advance_senate_phase(state, FIXED["player"])
        self.assertTrue(adv["success"], adv.get("message"))
        es = _effect_summary(state, adv)
        # 冻结层恰额消化 3 → 残量 0
        self.assertEqual(len(es["recruited"]), 3)
        self.assertEqual(es["available_pool_residual"], [])
        # 自动层按既有 `if not available: continue` 让位（defer），零失败/不重试
        self.assertEqual(es["retained_effects"], [])
        self.assertEqual(es["retained_effects_deferred"], [
            {"war_id": rebellion.id, "kind": "rebellion_assign",
             "reason": "RESIDUAL_POOL_EXHAUSTED",
             "source_rule": "assign_rebellion_commanders"}])
        # 起义本轮保持 commanderless / 0 兵（不强征）、Governor 不出征
        self.assertIsNone(rebellion.commander_id)
        self.assertEqual(state.get_military_system().get_legions_for_battle(rebellion.id), [])
        self.assertFalse(ctx["cmd_gov"].is_absent)
        # 冻结结果不被追改（不改冻结兵/target/N）
        self.assertEqual(ctx["war_ongoing"].commander_id, ctx["cmd_a"].id)
        self.assertEqual(ctx["war_peace"].commander_id, ctx["cmd_b"].id)
        self.assertNotEqual(adv["data"].get("code"), "WAR_EXECUTION_CONTEXT_CHANGED")
        self.assertFalse(adv["data"].get("retryable"))

    def test_residual_pool_admits_auto_effect_when_frozen_layer_leaves_room(self):
        """残量 ≥ 需求 → 既有语义执行（`min(legion_count, pool)`）并写入 `retained_effects[]`。"""
        ctx, state, rebellion = self._n21_setup()
        expected_legions = pool_legion_ids(state)[3:6]      # 冻结 ΣN=3 之后的残量前 min(3, residual) 个
        adv = senate_api.advance_senate_phase(state, FIXED["player"])
        self.assertTrue(adv["success"], adv.get("message"))
        es = _effect_summary(state, adv)
        self.assertEqual(len(es["available_pool_residual"]), 22)
        self.assertEqual(es["retained_effects_deferred"], [])
        self.assertEqual(es["retained_effects"], [
            {"war_id": rebellion.id, "kind": "rebellion_assign",
             "commander_id": ctx["cmd_gov"].id, "fleet_ids": [],
             "legion_numbers": expected_legions,
             "source_rule": "assign_rebellion_commanders",
             "time_slice": "post_frozen_plan"}])
        self.assertEqual(rebellion.commander_id, ctx["cmd_gov"].id)
        self.assertTrue(ctx["cmd_gov"].is_absent)

    def test_auto_commander_conflicting_with_frozen_claim_defers(self):
        """C.2.1(3) Commander 唯一性**含自动层**：与任一冻结 claim 冲突 → defer（不让路）。"""
        ctx = _prepared("F6-DD")
        state = ctx["state"]
        rebellion = _add_rebellion(state, governor_id=ctx["cmd_a"].id)  # cmd_a = 冻结 direct target
        adv = senate_api.advance_senate_phase(state, FIXED["player"])
        self.assertTrue(adv["success"], adv.get("message"))
        es = _effect_summary(state, adv)
        self.assertEqual(es["retained_effects"], [])
        self.assertEqual(es["retained_effects_deferred"], [
            {"war_id": rebellion.id, "kind": "rebellion_assign",
             "reason": "COMMANDER_CLAIM_CONFLICT",
             "source_rule": "assign_rebellion_commanders"}])
        self.assertIsNone(rebellion.commander_id)
        self.assertFalse(ctx["cmd_a"].is_dead)

    def test_auto_vs_auto_second_rebellion_defers_on_commander_claim(self):
        """B2-R1 窄项（C.2.1(3) 自动层**内部**互斥）：两条 commanderless 起义争夺同一候选。

        唯一后条件：按 `war_id` 定序，第一条按既有语义补位（恰额征召 + Governor 出征）；
        第二条因同一候选已属自动层 → **defer**（`COMMANDER_CLAIM_CONFLICT`，不让路/不重试）；
        冻结层 F/newN **不被追改**；再次 advance 幂等重放、**无重试环**。
        """
        ctx = _prepared("F6-DD")
        state = ctx["state"]
        first = _add_rebellion(state, province_id=991, governor_id=ctx["cmd_gov"].id)
        second = _add_rebellion(state, province_id=992, governor_id=ctx["cmd_gov"].id)
        self.assertLess(first.id, second.id)            # 自动层按 war_id 定序（991 先于 992）
        frozen = {ctx["war_ongoing"].id: (ctx["cmd_a"].id, 1),
                  ctx["war_peace"].id: (ctx["cmd_b"].id, 2)}
        pool_before = pool_legion_ids(state)

        adv = senate_api.advance_senate_phase(state, FIXED["player"])
        self.assertTrue(adv["success"], adv.get("message"))
        es = _effect_summary(state, adv)
        # 第一条补位；第二条同一候选已被自动层占用 → defer（非残量耗尽、不重试）
        self.assertEqual([e["war_id"] for e in es["retained_effects"]], [first.id])
        self.assertEqual(es["retained_effects"][0]["commander_id"], ctx["cmd_gov"].id)
        self.assertEqual(es["retained_effects_deferred"], [
            {"war_id": second.id, "kind": "rebellion_assign",
             "reason": "COMMANDER_CLAIM_CONFLICT",
             "source_rule": "assign_rebellion_commanders"}])
        # 同一候选只出征一次：第一条获将 + 恰额兵；第二条保持 commanderless / 0 兵
        self.assertEqual(first.commander_id, ctx["cmd_gov"].id)
        self.assertIsNone(second.commander_id)
        self.assertEqual(state.get_military_system().get_legions_for_battle(second.id), [])
        # 池恰额消耗：冻结 ΣN=3 + 第一条 3（第二条 defer 不征召）
        self.assertEqual(len(pool_legion_ids(state)), len(pool_before) - 6)
        # 冻结层 F / newN 未被追改（自动层不写冻结集合）
        for war_id, (commander_id, n) in frozen.items():
            war = state.get_war_system().get_war_by_id(war_id)
            self.assertEqual(war.commander_id, commander_id)
            self.assertEqual(len(state.get_military_system().get_legions_for_battle(war_id)), n)
        # 无重试环：再次 advance 幂等重放（零再次执行）→ 第二条仍不补位、出账逐字不变
        adv_again = senate_api.advance_senate_phase(state, FIXED["player"])
        self.assertTrue(adv_again["success"])
        self.assertTrue(adv_again["data"].get("replayed"))
        self.assertIsNone(second.commander_id)
        self.assertEqual(_effect_summary(state, adv_again)["retained_effects_deferred"],
                         es["retained_effects_deferred"])

    def test_reconciliation_distinguishes_no_object_vs_yield(self):
        """reconciliation 契约：区分「本就无对象」与「因让位未应用」。"""
        # (i) 无对象：无起义候选 + 无需舰队的 War → intents / applied / deferred 三者皆空
        ctx = _prepared("F6-DD")
        state = ctx["state"]
        adv = senate_api.advance_senate_phase(state, FIXED["player"])
        self.assertTrue(adv["success"], adv.get("message"))
        es = _effect_summary(state, adv)
        self.assertEqual(es["retained_effect_intents"], [])
        self.assertEqual(es["retained_effects"], [])
        self.assertEqual(es["retained_effects_deferred"], [])
        # (ii) 让位：对象存在（intent 非空）但残量耗尽（deferred 非空）→ 与 (i) 可区分
        ctx2, state2, rebellion = self._n21_setup(keep_pool=3)
        adv2 = senate_api.advance_senate_phase(state2, FIXED["player"])
        self.assertTrue(adv2["success"], adv2.get("message"))
        es2 = _effect_summary(state2, adv2)
        self.assertEqual([i["kind"] for i in es2["retained_effect_intents"]],
                         ["rebellion_assign"])
        self.assertTrue(es2["retained_effects_deferred"])

    def test_n22_auto_effect_never_rewrites_frozen_f_new_n(self):
        """N22（C.2.2 反例②）：c0=null 未选起义 + 自动 hook 置 Governor 为将。

        唯一后条件：claim-consistent apply 为终态；冻结层 F/newN **不被追改**、无重试环。
        """
        ctx = _prepared("F6-DD")
        state = ctx["state"]
        rebellion = _add_rebellion(state, governor_id=ctx["cmd_gov"].id)
        frozen = {ctx["war_ongoing"].id: (ctx["cmd_a"].id, 1),
                  ctx["war_peace"].id: (ctx["cmd_b"].id, 2)}
        adv = senate_api.advance_senate_phase(state, FIXED["player"])
        self.assertTrue(adv["success"], adv.get("message"))
        # 自动效果只写起义自身（claim-consistent），不写冻结集合
        for war_id, (commander_id, n) in frozen.items():
            war = state.get_war_system().get_war_by_id(war_id)
            self.assertEqual(war.commander_id, commander_id)
            self.assertEqual(len(state.get_military_system().get_legions_for_battle(war_id)), n)
        self.assertEqual(rebellion.commander_id, ctx["cmd_gov"].id)
        # 无「清回 null vs 保留 Governor」二义：单次 advance 即终态
        adv_again = senate_api.advance_senate_phase(state, FIXED["player"])
        self.assertTrue(adv_again["success"])
        self.assertTrue(adv_again["data"].get("replayed"))
        self.assertEqual(rebellion.commander_id, ctx["cmd_gov"].id)

    def test_fleet_target_set_is_post_frozen_projection(self):
        """时间截面 = post-frozen-plan 投影：AD 激活后需海战无舰队者才进目标集。"""
        ctx = _prepared("F6-MIX")
        state = ctx["state"]
        threat = ctx["war_threat"]
        threat._naval_required = True
        threat._enemy_naval_current = 3
        _add_available_fleets(state, [11])
        self.assertEqual(list(threat.assigned_fleet_ids), [])   # 边界前零军事写
        adv = senate_api.advance_senate_phase(state, FIXED["player"])
        self.assertTrue(adv["success"], adv.get("message"))
        es = _effect_summary(state, adv)
        self.assertEqual(es["retained_effect_intents"], [
            {"kind": "fleet_assign", "war_id": threat.id,
             "source_rule": "assign_fleets_to_active_wars",
             "time_slice": "post_frozen_plan"}])
        self.assertEqual(es["retained_effects"][0]["fleet_ids"], [11])
        self.assertEqual(es["retained_effects"][0]["war_id"], threat.id)
        self.assertEqual(list(threat.assigned_fleet_ids), [11])

    def test_plan_exposes_available_pool_residual_after_frozen_sum_n(self):
        """P-1 方向 A：冻结所选 direct ΣN 优先吃池；残量 = 池 − ΣN（plan 级可复算）。"""
        ctx = build_f6("F6-DD")
        state = ctx["state"]
        sub = submit_api(state, ctx["drafts"])
        self.assertTrue(sub["success"], sub.get("errors"))
        self.assertTrue(senate_api.resolve_senate(state, vote_decider=_PassDecider())["success"])
        pol = PoliticalSystem(state)
        decisions = [d for (s, _p), d in state.get_war_decisions().items() if s == "S1"]
        consul = list(state.get_consul_war_decisions("S1").values())
        pool = pool_legion_ids(state)
        plan = pol.build_war_resolution_plan(
            decisions, consul, current_turn=1, session_id="S1", real_wars=pol._real_wars(),
            available_legion_ids=pool, pending_war_ids=[FIXED["war_peace"]],
            package_id=sub["data"]["package_id"],
            submission_context=state.get_submission_context(sub["data"]["submission_context_id"]))
        self.assertEqual(plan["available_pool"], pool)
        self.assertEqual(sum(plan["new_reinforcement"].values()), 3)
        self.assertEqual(plan["available_pool_residual"], pool[3:])
        self.assertEqual(sorted(plan["frozen_claim_targets"]),
                         sorted([ctx["cmd_a"].id, ctx["cmd_b"].id]))

    def test_resolve_senate_registers_intents_without_military_write(self):
        """C.5.1 调用方唯一化：resolve_senate 零军事写，只登记 `retained_effect_intents`。"""
        ctx = build_f6("F6-DD")
        state = ctx["state"]
        rebellion = _add_rebellion(state, governor_id=ctx["cmd_gov"].id)
        sub = submit_api(state, ctx["drafts"])
        self.assertTrue(sub["success"], sub.get("errors"))
        pool_before = pool_legion_ids(state)
        res = senate_api.resolve_senate(state, vote_decider=_PassDecider())
        self.assertTrue(res["success"], res.get("message"))
        data = state.get_phase_result("senate")["data"]
        self.assertEqual([i["kind"] for i in data["retained_effect_intents"]],
                         ["rebellion_assign"])
        self.assertEqual(data["fleet_assignments"], [])
        self.assertEqual(data["rebellion_commander_assignments"], [])
        # 零军事写（pre-boundary 军事投影不变）
        self.assertIsNone(rebellion.commander_id)
        self.assertEqual(state.get_military_system().get_legions_for_battle(rebellion.id), [])
        self.assertEqual(pool_legion_ids(state), pool_before)
        # 军事自动层未运行：起义无将/零兵（Governor 政治步骤在本函数内保留，见 C.5.3）
        self.assertEqual(state.get_phase_result("senate")["data"].get("governor_assignments") is not None,
                         True)


class TestP22AutoLayerFaultContract(unittest.TestCase):
    """Exit（P2-2）：确定性短fall → defer；**未预期异常** → `APPLY_FAILED` 整域回滚 + 同身份重试。"""

    def test_unexpected_exception_in_auto_layer_apply_failed_full_rollback_retry(self):
        ctx = _prepared("F6-DD")
        state = ctx["state"]
        rebellion = _add_rebellion(state, governor_id=ctx["cmd_gov"].id)
        before = state.snapshot_war_resolution_domains()
        with mock.patch.object(MilitarySystem, "recruit_multiple",
                               side_effect=RuntimeError("auto-layer boom")):
            adv = senate_api.advance_senate_phase(state, FIXED["player"])
        self.assertFalse(adv["success"])
        self.assertEqual(adv["data"]["code"], "WAR_EXECUTION_APPLY_FAILED")
        self.assertTrue(adv["data"]["retryable"])
        # 整域回滚（含冻结层已应用的军事写）→ 12 域深值完全相等（写集合 ⊆ 12 域）
        self.assertEqual(state.snapshot_war_resolution_domains(), before)
        self.assertIsNone(state.get_war_execution_receipt(adv["data"]["execution_id"]))
        self.assertFalse(state.is_phase_executed("senate"))
        self.assertIsNone(rebellion.commander_id)
        # 同执行身份重试成功（异常消除后），恰一次生效
        adv2 = senate_api.advance_senate_phase(state, FIXED["player"])
        self.assertTrue(adv2["success"], adv2.get("message"))
        self.assertEqual(adv2["data"]["execution_id"], adv["data"]["execution_id"])
        self.assertFalse(adv2["data"].get("replayed"))
        self.assertEqual(rebellion.commander_id, ctx["cmd_gov"].id)

    def test_deterministic_shortfall_is_not_an_exception(self):
        """确定性短fall 与未预期异常**显式并列**：前者零失败/不重试，后者回滚/可重试。"""
        ctx, state, rebellion = TestFrozenAutomaticLayerSeparation()._n21_setup(keep_pool=3)
        adv = senate_api.advance_senate_phase(state, FIXED["player"])
        self.assertTrue(adv["success"])
        self.assertNotEqual(adv["data"].get("code"), "WAR_EXECUTION_APPLY_FAILED")
        self.assertFalse(adv["data"].get("retryable"))
        es = _effect_summary(state, adv)
        self.assertEqual(es["retained_effects_deferred"][0]["reason"], "RESIDUAL_POOL_EXHAUSTED")


# ===========================================================================
# DA-3 B4（SA v1.1 §C.6）— 三孤儿退役为无副作用 shim：直接调用零 mutation
# ===========================================================================

class TestLegacyWarExecutionRetired(unittest.TestCase):
    """Exit：`execute_war_takeover_deploy` / `_direct` / `_continue_direct` 直调零 mutation。"""

    ORPHANS = ("execute_war_takeover_deploy", "execute_war_takeover_direct",
               "execute_war_continue_direct")

    def _fixture(self):
        ctx = build_f6_base()          # war_ongoing=ACTIVE（有将 cmd_a）；war_peace=TRUCE+pending
        state = ctx["state"]
        return ctx, state, PoliticalSystem(state), state.get_member(ctx["consul_id"])

    def test_orphans_return_retired_code_and_zero_mutation(self):
        ctx, state, pol, consul = self._fixture()
        before_military = state.snapshot_war_resolution_domains()
        proposals_before = list(state.get_senate_proposals())
        treaty_before = dict(ctx["war_peace"].peace_treaty or {})
        status_before = (ctx["war_ongoing"].status, ctx["war_peace"].status)
        for name in self.ORPHANS:
            with self.subTest(method=name):
                res = getattr(pol, name)(ctx["war_peace"], consul, reinforcement_n=1)
                self.assertFalse(res["success"])
                self.assertEqual(res["code"], PoliticalSystem.LEGACY_WAR_EXECUTION_RETIRED)
                self.assertEqual(res["message"], "use package and advance")
        # 零 mutation：军事/人物域深值不变；政治面（提案/条约/状态）不变
        self.assertEqual(state.snapshot_war_resolution_domains(), before_military)
        self.assertEqual(list(state.get_senate_proposals()), proposals_before)
        self.assertEqual(dict(ctx["war_peace"].peace_treaty or {}), treaty_before)
        self.assertEqual((ctx["war_ongoing"].status, ctx["war_peace"].status), status_before)

    def test_orphans_active_takeover_direct_zero_mutation(self):
        """原 P2（ACTIVE 接管）路径：旧执行体不接管、不换将、不置出征。"""
        ctx, state, pol, consul = self._fixture()
        war = ctx["war_ongoing"]
        before = state.snapshot_war_resolution_domains()
        res = pol.execute_war_takeover_direct(war, consul, reinforcement_n=1)
        self.assertFalse(res["success"])
        self.assertEqual(res["code"], PoliticalSystem.LEGACY_WAR_EXECUTION_RETIRED)
        self.assertEqual(state.snapshot_war_resolution_domains(), before)
        self.assertEqual(war.commander_id, ctx["cmd_a"].id, "旧执行体不得换将")


# ===========================================================================
# DA-3 B5（SA v1.1 §C.5.3 / §D.1.2 / §C.2.1）— 自动 Governor claim-aware（N24）
# ===========================================================================

class TestGovernorClaimAware(unittest.TestCase):
    """Exit：自动 `assign_governors` 以**冻结 claims 为硬排除**；N24 唯一后条件。

    N24（§C.5.3 确定性正例）：F6 base + figure4（ex-consul、有已结束 consul 任期、在城、非
    Governor）+ 空 proconsul Province（figure4 = 唯一合格历史候选）+ ongoing 卡 direct→4、N=0；
    pending War→3。后条件：Province **留空**、**无** Governor×Commander 双角色、**无永久
    CONTEXT_CHANGED**、**无重试环**；**另有合格候选 ⇒ 分配给他人**（非跳过、非报错）。
    """

    def _fixture(self, extra_candidate=False):
        """F6 base + 空 proconsul Province（figure4 = 唯一/首个合格候选）。"""
        ctx = build_f6_base()
        state = ctx["state"]
        province = add_province(state, 77, "Provincia Nova", governor_type="proconsul")
        ctx["empty_province"] = province
        if extra_candidate:
            # 另一合格候选（更早卸任 → 默认排序在 figure4 之后，排除后由它补位）
            ctx["cmd_alt"] = add_figure(
                state, ctx["faction"], 5, "Governor H", office="ex-consul",
                history=[{"office_type": "consul", "start_turn": -5, "end_turn": -4}])
        return ctx

    def _drafts(self, ctx):
        return [command_draft(FIXED["war_ongoing"], ctx["cmd_gov"].id, 0),
                command_draft(FIXED["war_peace"], ctx["cmd_b"].id, 0)]

    def test_mechanism_excludes_frozen_commander_but_default_unchanged(self):
        """机制面：无排除（legacy 直调）→ figure4 被任命；排除 figure4 → 无候选即留空。"""
        # (a) 缺省（legacy 直调，行为与 baseline 逐字一致）：唯一合格候选 figure4 被任命
        ctx_a = self._fixture()
        res_a = senate_api.assign_governors(ctx_a["state"])
        self.assertEqual([r["governor_id"] for r in res_a], [ctx_a["cmd_gov"].id])
        self.assertEqual(ctx_a["empty_province"].governor_designate_id, ctx_a["cmd_gov"].id)
        # (b) 冻结 claims 硬排除 figure4：无候选 → 不分配（不报错、不跳过步骤、不置 absent）
        ctx_b = self._fixture()
        res_b = senate_api.assign_governors(ctx_b["state"],
                                            excluded_commander_ids={ctx_b["cmd_gov"].id})
        self.assertEqual(res_b, [])
        self.assertIsNone(ctx_b["empty_province"].governor_designate_id)
        self.assertIsNone(ctx_b["empty_province"].governor_id, "Province 应留空")
        self.assertFalse(ctx_b["cmd_gov"].is_absent, "禁提前置军事 absent")

    def test_n24_unique_postconditions_vacant_no_double_role_no_retry(self):
        """N24 唯一后条件：Province 留空 / 无双角色 / 无永久 CONTEXT_CHANGED / 无重试环。"""
        ctx = self._fixture()
        state = ctx["state"]
        sub = submit_api(state, self._drafts(ctx))
        self.assertTrue(sub["success"], sub.get("errors"))
        prov = ctx["empty_province"]
        # —— finalization（claim-aware Governor 步骤）——
        res = senate_api.resolve_senate(state, vote_decider=_PassDecider())
        self.assertTrue(res["success"], res.get("message"))
        data = state.get_phase_result("senate")["data"]
        self.assertEqual(data["governor_assignments"], [], "无候选即不分配（空位合法）")
        self.assertIsNone(prov.governor_designate_id, "Province 留空")
        self.assertIsNone(prov.governor_id)
        self.assertFalse(ctx["cmd_gov"].is_absent, "禁提前置军事 absent")
        # 无 Governor×Commander 双角色（figure4 仅 Commander，不是 Governor）
        self.assertNotEqual(prov.governor_designate_id, ctx["cmd_gov"].id)
        # —— 边界 advance：无永久 CONTEXT_CHANGED、无重试环 ——
        adv = senate_api.advance_senate_phase(state, FIXED["player"])
        self.assertTrue(adv["success"], adv.get("message"))
        self.assertNotEqual(adv["data"].get("code"), "WAR_EXECUTION_CONTEXT_CHANGED")
        self.assertNotEqual(adv["data"].get("code"), "WAR_EXECUTION_APPLY_FAILED")
        self.assertFalse(adv["data"].get("retryable"))
        # 冻结 direct 生效：ongoing War 的 Commander = figure4
        self.assertEqual(state.get_war_system().get_war_by_id(FIXED["war_ongoing"]).commander_id,
                         ctx["cmd_gov"].id)
        # 无重试环：再 advance 幂等重放（receipt 重放，零再次执行）
        adv2 = senate_api.advance_senate_phase(state, FIXED["player"])
        self.assertTrue(adv2["success"])
        self.assertTrue(adv2["data"].get("replayed"))
        self.assertIsNone(prov.governor_designate_id, "重放后 Province 仍留空")

    def test_n24_other_eligible_candidate_assigned_not_skipped(self):
        """另有合格候选 ⇒ 按既有语义**分配给他人**（非跳过、非报错）。"""
        ctx = self._fixture(extra_candidate=True)
        state = ctx["state"]
        sub = submit_api(state, self._drafts(ctx))
        self.assertTrue(sub["success"], sub.get("errors"))
        prov = ctx["empty_province"]
        res = senate_api.resolve_senate(state, vote_decider=_PassDecider())
        self.assertTrue(res["success"], res.get("message"))
        data = state.get_phase_result("senate")["data"]
        # figure4 硬排除 → 另一合格候选补位（不是空位、不是报错）
        self.assertEqual(prov.governor_designate_id, ctx["cmd_alt"].id)
        self.assertEqual([r["governor_id"] for r in data["governor_assignments"]],
                         [ctx["cmd_alt"].id])
        self.assertNotEqual(prov.governor_designate_id, ctx["cmd_gov"].id)
        self.assertFalse(ctx["cmd_gov"].is_absent)


# ===========================================================================
# DA-3 B6（SA v1.1 §C.4；DA-Plan §2 DA-3 B6）：save/load + 兼容边界
#   (a) 完整 package/context/direct/decisions/receipt/phase 同版存读；
#   (b) 四时点 + **真实 serializer round-trip**（json 序列化/反序列化，非 dict deepcopy）；
#   (c) legacy R5 已 COMMITTED 只读重放；已提交未执行 R5 中途存档 = 版本不兼容 +
#       旧快照只读保留 + 受控重新开始（**禁静默伪造 R6 上下文**，B2-PM-3 / B5-PM-2）。
# 既有 R5 用例**不迁移**（取代面红账归 DA-6 B1）。证据分类 = DATA。
# ===========================================================================
import copy as _copy
import json as _json

from src.tests.fixtures.wpgr5_fixtures import _base_config


class _Recorder:
    """只记录、不改行为的事件 sink（用于兼容边界日志断言）。"""

    def __init__(self):
        self.events = []

    def __call__(self, message, level=None, extra=None):
        self.events.append((message, extra or {}))


def _clone_via_json(state):
    """**真实 serializer round-trip**：to_dict → json.dumps → json.loads → load_from_dict。"""
    payload = _json.loads(_json.dumps(state.to_dict(), ensure_ascii=False))
    clone = GameState.create_for_testing(_base_config())
    clone.load_from_dict(payload)
    return clone, payload


def _senate_projection(state):
    """会期身份 + 内容投影（存读前后逐项比较的唯一口径）。"""
    ledger = state.get_war_execution_ledger()
    return {
        "session": state.get_senate_session(),
        "registry": state.get_senate_package_registry(),
        "consul_decisions": state.get_consul_war_decisions(state.get_senate_session() or ""),
        "decisions": state.get_war_decisions(),
        "receipts": ledger["receipts"],
        "by_session": ledger["by_session"],
        "phase_result_senate": _copy.deepcopy(state.get_phase_result("senate")),
        "senate_executed": state.is_phase_executed("senate"),
    }


def _war_projection(state):
    """军事投影（治理面零早写/重放零再次执行的比较口径）。"""
    ws = state.get_war_system()
    out = {}
    for war_id in (FIXED["war_ongoing"], FIXED["war_peace"], FIXED["war_threat"]):
        war = ws.get_war_by_id(war_id)
        if war is None:
            continue
        out[war_id] = {
            "status": war.status.value if hasattr(war.status, "value") else str(war.status),
            "commander_id": getattr(war, "commander_id", None),
            "legions": sorted(list(getattr(war, "legion_numbers", []) or [])),
            "fleets": sorted(list(getattr(war, "assigned_fleet_ids", []) or [])),
        }
    return {"wars": out, "pool": pool_legion_ids(state), "treasury": state.treasury}


class TestSaveLoadFourTimepoints(unittest.TestCase):
    """Exit (a)(b)：四时点（Submit / Results 未 advance / commit / 重复 advance）同版存读。"""

    def _fixture(self):
        ctx = build_f6("F6-MIX")
        return ctx, ctx["state"]

    def test_timepoint_1_after_submit(self):
        """时点 1：Submit 后（package/context/direct/war_items/requests 同版）。"""
        ctx, state = self._fixture()
        sub = submit_api(state, ctx["drafts"])
        self.assertTrue(sub["success"], sub.get("errors"))
        before = _senate_projection(state)
        self.assertTrue(before["session"])

        clone, payload = _clone_via_json(state)
        after = _senate_projection(clone)
        self.assertEqual(after, before)
        # 内容级：PackageRecord 同版 + 真注册 Context + 1 direct + 1 Senate snapshot
        reg = clone.get_senate_package_registry()
        self.assertGreaterEqual(len(reg["contexts"]), 1)
        package_id = reg["by_session"][before["session"]]
        package = reg["packages"][package_id]
        self.assertEqual(package["schema_version"], 2)
        self.assertEqual(package["package_id"], sub["data"]["package_id"])
        self.assertEqual(package["submission_context_id"], sub["data"]["submission_context_id"])
        self.assertIn(package["submission_context_id"], reg["contexts"])
        self.assertEqual(len(reg["consul_war_decisions"]), 1)
        self.assertEqual(len(reg["war_snapshots"]), 1)
        self.assertEqual(len(reg["requests"]), 1)
        # 复合键 request key = (session, actor, request_id) 三元绑定（字符串嵌套编码）
        request_key = next(iter(reg["requests"]))
        parts = request_key.split("\x1f")
        self.assertEqual(len(parts), 3)
        self.assertEqual(parts[0], before["session"])
        self.assertEqual(parts[2], "req-1")
        # 军事投影零早写（Submit 不部署）
        self.assertEqual(_war_projection(clone), _war_projection(state))
        self.assertFalse(after["senate_executed"])

    def test_timepoint_2_after_results_before_advance(self):
        """时点 2：Results 后未 advance（decision 冻结、receipt 尚无）。"""
        ctx, state = self._fixture()
        sub = submit_api(state, ctx["drafts"])
        self.assertTrue(sub["success"], sub.get("errors"))
        res = senate_api.resolve_senate(state, vote_decider=_PassDecider())
        self.assertTrue(res["success"], res.get("message"))
        self.assertTrue(state.get_war_decisions(), "resolve 必须冻结 decision")
        self.assertIsNone(state.get_war_execution_receipt_for_session(state.get_senate_session()))

        before = _senate_projection(state)
        clone, _ = _clone_via_json(state)
        self.assertEqual(_senate_projection(clone), before)
        self.assertEqual(set(clone.get_war_decisions().keys()),
                         set(state.get_war_decisions().keys()))
        self.assertTrue(clone.get_phase_result("senate"), "phase result 同版保留")
        self.assertIsNone(clone.get_war_execution_receipt_for_session(clone.get_senate_session()))

    def test_timepoint_3_after_commit(self):
        """时点 3：commit 后（receipt + by_session + phase 标记同版）。"""
        ctx, state = self._fixture()
        sub = submit_api(state, ctx["drafts"])
        self.assertTrue(sub["success"], sub.get("errors"))
        self.assertTrue(senate_api.resolve_senate(state, vote_decider=_PassDecider())["success"])
        adv = senate_api.advance_senate_phase(state, FIXED["player"])
        self.assertTrue(adv["success"], adv.get("message"))
        receipt = state.get_war_execution_receipt_for_session(state.get_senate_session())
        self.assertIsNotNone(receipt)
        self.assertEqual(receipt["status"], "COMMITTED")

        before = _senate_projection(state)
        clone, _ = _clone_via_json(state)
        after = _senate_projection(clone)
        # receipt 身份字段 JSON 复原：`commit_revision` 在线 tuple → JSON list → 加载复原 tuple
        eid = next(iter(before["receipts"]))
        self.assertIsInstance(before["receipts"][eid]["commit_revision"], tuple)
        self.assertEqual(after["receipts"][eid]["commit_revision"],
                         before["receipts"][eid]["commit_revision"])
        self.assertEqual(after, before)
        self.assertEqual(after["receipts"], before["receipts"])
        self.assertEqual(after["by_session"], before["by_session"])
        self.assertTrue(after["senate_executed"])
        self.assertEqual(_war_projection(clone), _war_projection(state))

    def test_timepoint_4_repeated_advance(self):
        """时点 4：重复 advance（receipt 重放，零再次执行；round-trip 不变量）。"""
        ctx, state = self._fixture()
        sub = submit_api(state, ctx["drafts"])
        self.assertTrue(sub["success"], sub.get("errors"))
        self.assertTrue(senate_api.resolve_senate(state, vote_decider=_PassDecider())["success"])
        first = senate_api.advance_senate_phase(state, FIXED["player"])
        self.assertTrue(first["success"])
        war_after_first = _war_projection(state)
        second = senate_api.advance_senate_phase(state, FIXED["player"])
        self.assertTrue(second["success"])
        self.assertTrue(second["data"].get("replayed"))
        self.assertEqual(_war_projection(state), war_after_first, "重放零再次部署")

        before = _senate_projection(state)
        clone, _ = _clone_via_json(state)
        self.assertEqual(_senate_projection(clone), before)
        self.assertEqual(_war_projection(clone), war_after_first)


class TestRealSerializerRoundTrip(unittest.TestCase):
    """Exit (b)：真实 serializer round-trip（rows/list 编码；**不靠 dict deepcopy**）。"""

    def _submitted(self):
        ctx = build_f6("F6-VV")
        state = ctx["state"]
        sub = submit_api(state, ctx["drafts"])
        self.assertTrue(sub["success"], sub.get("errors"))
        self.assertTrue(senate_api.resolve_senate(state, vote_decider=_PassDecider())["success"])
        return ctx, state

    def test_composite_keys_encoded_as_rows_not_tuple_key_dict(self):
        """复合键索引序列化外形 = rows/list（JSON-native），加载后重建为 tuple 键。"""
        _ctx, state = self._submitted()
        encoded = state.to_dict()["_senate_package_ledger"]
        for index, key_fields in (("war_snapshots", ("senate_session_id", "war_id")),
                                  ("war_items", ("senate_session_id", "war_id")),
                                  ("consul_war_decisions",
                                   ("senate_session_id", "direct_decision_id"))):
            self.assertIsInstance(encoded[index], list, f"{index} 必须是 rows/list")
            for row in encoded[index]:
                self.assertIsInstance(row, dict)
                for field in key_fields:
                    self.assertIn(field, row)
        self.assertIsInstance(state.to_dict()["_war_execution_ledger"]["decisions"], list)
        # 反面证据：复合键内存 mapping **无法**直接 JSON 序列化 → deepcopy 冒称 round-trip 不成立
        with self.assertRaises(TypeError):
            _json.dumps(state.get_senate_package_registry()["war_snapshots"])

    def test_json_roundtrip_rebuilds_indices_and_preserves_identity(self):
        """json 往返后重建索引 + 身份/内容逐项相等（真实序列化，非 deepcopy）。"""
        _ctx, state = self._submitted()
        before = _senate_projection(state)
        clone, payload = _clone_via_json(state)
        after = _senate_projection(clone)
        self.assertEqual(after, before)
        # 载荷确实经过 JSON 文本：复合键索引为 list（非 tuple 键 dict）
        self.assertIsInstance(payload["_senate_package_ledger"]["war_snapshots"], list)
        # 重建后索引为 tuple 键，与原件逐键相等
        reg = clone.get_senate_package_registry()
        self.assertTrue(all(isinstance(k, tuple) and len(k) == 2
                            for k in reg["war_snapshots"]))
        self.assertEqual(reg["war_snapshots"],
                         state.get_senate_package_registry()["war_snapshots"])
        self.assertEqual(clone.validate_senate_ledger_consistency(), [])


class TestLegacyCompatibilityBoundary(unittest.TestCase):
    """Exit (c)：legacy R5 只读重放 / 版本不兼容 + 旧快照只读 + 受控重开。"""

    def _legacy_archive(self, ctx, *, committed=False, decisions=None, session="S-legacy"):
        """构造 legacy R5 外形存档（无 R6 package 账本键）。"""
        arch = ctx["state"].to_dict()
        arch.pop("_senate_package_ledger", None)
        arch.pop("_senate_legacy_archive", None)
        arch["_senate_session_id"] = session
        arch["_war_execution_ledger"] = {"receipts": {}, "by_session": {},
                                        "decisions": decisions or {}}
        if committed:
            receipt = {"execution_id": "exec-legacy-1", "senate_session_id": session,
                       "status": "COMMITTED", "protocol_version": 1,
                       "proposal_refs": [7], "direct_decision_refs": [],
                       "pending_fallback_war_ids": [], "retained_effects": [],
                       "retained_effects_deferred": []}
            arch["_war_execution_ledger"]["receipts"]["exec-legacy-1"] = receipt
            arch["_war_execution_ledger"]["by_session"][session] = "exec-legacy-1"
        return arch

    def _load(self, arch, recorder=None):
        clone = GameState.create_for_testing(_base_config())
        if recorder is not None:
            clone.log_event = recorder
        clone.load_from_dict(arch)
        return clone

    def test_legacy_committed_read_only_replay(self):
        """legacy R5 已 COMMITTED：保持旧身份只读重放，零再次执行、零 R6 上下文伪造。"""
        ctx = build_f6_base()
        arch = self._legacy_archive(ctx, committed=True)
        rec = _Recorder()
        clone = self._load(arch, rec)
        compat = clone.get_senate_archive_compat()
        self.assertTrue(compat["legacy"] and compat["committed_legacy"])
        self.assertFalse(compat["compatible"])
        self.assertFalse(compat["requires_controlled_restart"])
        self.assertEqual(compat["reason"], "legacy_r5_committed_read_only_replay")
        # 不伪造 R6 上下文：包/上下文/war_items 恒空，get_submission_context 不编造
        reg = clone.get_senate_package_registry()
        self.assertEqual(reg["contexts"], {})
        self.assertEqual(reg["packages"], {})
        self.assertEqual(reg["war_items"], {})
        self.assertIsNone(clone.get_submission_context("any"))
        # 只读重放：同会期 receipt 原样返回（旧 execution_id 身份不变）
        before_war = _war_projection(clone)
        adv = senate_api.advance_senate_phase(clone, FIXED["player"])
        self.assertTrue(adv["success"], adv.get("message"))
        self.assertTrue(adv["data"].get("replayed"))
        self.assertEqual(adv["data"]["execution_id"], "exec-legacy-1")
        self.assertEqual(adv["data"]["receipt"]["status"], "COMMITTED")
        self.assertEqual(_war_projection(clone), before_war, "重放零军事 mutation")
        self.assertEqual(clone.get_senate_package_registry()["contexts"], {})
        self.assertTrue(any(extra.get("type") == "senate_archive_legacy_detected"
                            for _msg, extra in rec.events), rec.events)

    def test_legacy_submitted_unexecuted_is_explicitly_incompatible(self):
        """已提交未执行 R5 中途存档 = 明确版本不兼容（不静默吸收、不伪造上下文）。"""
        ctx = build_f6_base()
        decisions = {("S-legacy", 7): {
            "proposal_id": 7, "war_id": FIXED["war_ongoing"], "outcome": "ENACTED",
            "mode": "command", "source": "active_declaration",
            "payload": {"target_commander_id": ctx["cmd_a"].id, "reinforcement_n": 0}}}
        arch = self._legacy_archive(ctx, decisions=decisions)
        rec = _Recorder()
        clone = self._load(arch, rec)
        compat = clone.get_senate_archive_compat()
        self.assertTrue(compat["pending_unexecuted"])
        self.assertTrue(compat["requires_controlled_restart"])
        self.assertFalse(compat["compatible"])
        self.assertEqual(compat["reason"],
                         "legacy_r5_submitted_unexecuted_incompatible")
        self.assertEqual(clone.get_senate_session(), "S-legacy")
        self.assertTrue(clone.get_war_decisions(), "旧决定只读可见（不迁移）")
        reg = clone.get_senate_package_registry()
        self.assertEqual((reg["contexts"], reg["packages"], reg["war_items"]), ({}, {}, {}))
        self.assertTrue(any(extra.get("type") == "senate_archive_legacy_detected"
                            for _msg, extra in rec.events), rec.events)

    def test_controlled_restart_preserves_snapshot_and_fabricates_nothing(self):
        """受控重开：旧快照只读保留 + 新会期开始 + 零 R6 截图伪造；二次调用 fail-closed。"""
        ctx = build_f6_base()
        decisions = {("S-legacy", 7): {"proposal_id": 7, "war_id": FIXED["war_ongoing"],
                                        "outcome": "ENACTED", "mode": "command",
                                        "source": "active_declaration",
                                        "payload": {"target_commander_id": ctx["cmd_a"].id,
                                                    "reinforcement_n": 0}}}
        arch = self._legacy_archive(ctx, decisions=decisions)
        clone = self._load(arch)
        res = clone.begin_controlled_senate_restart()
        self.assertTrue(res["success"], res)
        self.assertEqual(res["code"], "SENATE_ARCHIVE_CONTROLLED_RESTART")
        self.assertEqual(res["restarted_from_session"], "S-legacy")
        self.assertTrue(res["legacy_snapshot_preserved"])
        self.assertFalse(res["r6_context_fabricated"])
        # 新会期：会期身份清空、旧未执行决定不迁移到 live、包/上下文仍空
        self.assertIsNone(clone.get_senate_session())
        self.assertEqual(clone.get_war_decisions(), {})
        reg = clone.get_senate_package_registry()
        self.assertEqual((reg["contexts"], reg["packages"], reg["war_items"]), ({}, {}, {}))
        self.assertEqual(clone.get_senate_proposals(), [])
        self.assertFalse(clone.is_phase_executed("senate"))
        # 旧快照只读保留（含旧决定原文；复合键 → rows/list = JSON-native）
        snap = clone.get_senate_legacy_archive()
        self.assertEqual(snap["senate_session_id"], "S-legacy")
        preserved_rows = snap["war_execution_ledger"]["decisions"]
        self.assertIsInstance(preserved_rows, list, "只读快照必须为 JSON-native rows/list")
        self.assertEqual([(r["senate_session_id"], r["proposal_id"]) for r in preserved_rows],
                         [("S-legacy", 7)])
        self.assertEqual(preserved_rows[0]["decision"], decisions[("S-legacy", 7)])
        # 快照可 JSON 序列化（不携带 tuple 键）
        self.assertIsInstance(
            _json.dumps(clone.get_senate_legacy_archive(), ensure_ascii=False), str)
        # 只读：取回修改不影响底层
        expected_rows = _copy.deepcopy(preserved_rows)
        snap["war_execution_ledger"]["decisions"].clear()
        self.assertEqual(clone.get_senate_legacy_archive()["war_execution_ledger"]["decisions"],
                         expected_rows)
        # 二次调用 fail-closed 且零 mutation
        again = clone.begin_controlled_senate_restart()
        self.assertFalse(again["success"])
        self.assertEqual(again["code"], "SENATE_ARCHIVE_RESTART_NOT_REQUIRED")
        # 重开后 round-trip：快照随存档保留，分类为 R6……
        clone2, _payload = _clone_via_json(clone)
        self.assertEqual(clone2.get_senate_legacy_archive()["war_execution_ledger"]["decisions"],
                         expected_rows)
        self.assertTrue(clone2.get_senate_archive_compat()["r6_ledger"])

    def test_restart_on_r6_archive_is_refused_zero_mutation(self):
        """非 legacy（R6 同版）存档不得受控重开（fail-closed、零 mutation）。"""
        ctx = build_f6("F6-DD")
        state = ctx["state"]
        self.assertTrue(submit_api(state, ctx["drafts"])["success"])
        before = _senate_projection(state)
        res = state.begin_controlled_senate_restart()
        self.assertFalse(res["success"])
        self.assertEqual(res["code"], "SENATE_ARCHIVE_RESTART_NOT_REQUIRED")
        self.assertEqual(_senate_projection(state), before)

    def test_controlled_restart_then_full_new_session(self):
        """B6-PM-3：受控重开后**端到端跑通一轮完整新会期**（submit → resolve → advance → receipt），
        且旧快照全程只读（零迁移、零改写）。

        既有载体只证明「重开机制正确」；本条补「重开 → 新会期完整一轮」的端到端面。
        """
        ctx = build_f6("F6-MIX")
        decisions = {("S-legacy", 7): {
            "proposal_id": 7, "war_id": FIXED["war_ongoing"], "outcome": "ENACTED",
            "mode": "command", "source": "active_declaration",
            "payload": {"target_commander_id": ctx["cmd_a"].id, "reinforcement_n": 0}}}
        arch = self._legacy_archive(ctx, decisions=decisions)
        clone = self._load(arch)
        res = clone.begin_controlled_senate_restart()
        self.assertTrue(res["success"], res)
        self.assertEqual(res["code"], "SENATE_ARCHIVE_CONTROLLED_RESTART")
        self.assertEqual(res["restarted_from_session"], "S-legacy")
        snapshot_before = _json.dumps(clone.get_senate_legacy_archive(),
                                      ensure_ascii=False, sort_keys=True)
        war_before = _war_projection(clone)

        # ---- 新会期第 1 步：唯一整包 Submit（新会期身份，与旧会期分立）----
        sub = submit_api(clone, ctx["drafts"], session_id="S-new")
        self.assertTrue(sub["success"], sub.get("errors"))
        new_session = clone.get_senate_session()
        self.assertEqual(new_session, "S-new")
        self.assertNotEqual(new_session, "S-legacy")
        self.assertEqual(_war_projection(clone), war_before, "Submit 阶段零早写")
        reg = clone.get_senate_package_registry()
        self.assertIn(new_session, reg["by_session"], "新会期包必须注册") 
        self.assertIn(sub["data"]["submission_context_id"], reg["contexts"])

        # ---- 第 2 步 resolve（冻结 decision）→ 第 3 步 advance（边界部署）----
        resolved = senate_api.resolve_senate(clone, vote_decider=_PassDecider())
        self.assertTrue(resolved["success"], resolved.get("message"))
        self.assertTrue(clone.get_war_decisions(), "新会期 resolve 必须冻结 decision")
        advanced = senate_api.advance_senate_phase(clone, FIXED["player"])
        self.assertTrue(advanced["success"], advanced.get("message"))

        # ---- 第 4 步 receipt（四事实同版 + 身份绑定新会期）----
        receipt = clone.get_war_execution_receipt_for_session(new_session)
        self.assertIsNotNone(receipt, "新会期必须产出 receipt")
        self.assertEqual(receipt["status"], "COMMITTED")
        self.assertEqual(receipt["senate_session_id"], new_session)
        self.assertEqual(receipt["protocol_version"], WAR_RESOLUTION_PROTOCOL_VERSION)
        self.assertTrue(clone.is_phase_executed("senate"))
        self.assertTrue(clone.get_phase_result("senate"), "phase result 同版")
        self.assertNotEqual(_war_projection(clone), war_before, "边界必须实际部署")

        # ---- 旧快照只读：重开 + 新会期全轮后逐字不变、不迁移 ----
        self.assertEqual(_json.dumps(clone.get_senate_legacy_archive(),
                                     ensure_ascii=False, sort_keys=True), snapshot_before)
        self.assertEqual(clone.get_senate_legacy_archive()["senate_session_id"], "S-legacy")
        self.assertTrue(clone.get_senate_archive_compat()["r6_ledger"])
        self.assertNotIn(("S-legacy", 7), clone.get_war_decisions())

    def test_21_code_machine_identity_unchanged(self):
        self.assertEqual(tuple(PoliticalSystem._SUBMIT_ERROR_CODES), SUBMIT_ERROR_CODES_21)


if __name__ == "__main__":
    unittest.main()
