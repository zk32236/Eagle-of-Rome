# src/tests/test_api/test_wpgr4_s1_takeover_session.py
"""WP-G-R4 S1 → WP-G-R5 整包/边界改写（Plan §4.2 L1；SA §4.6/§4.10 C-M09，DA-2~DA-4）。

R5 supersede：旧 `takeover_war(action=reserve|submit)` 单槽锁 T + pending 部署单元退役；
「出征任命」统一经唯一整包入口 `senate_api.propose_many`（Submit 零军事写）→ resolve
（R 只 finalize Decision）→ Senate→Combat 边界 `advance_senate_phase` 原子部署
（receipt exactly-once，12 域回滚）。

保留反例（原 T01/T02/T03 语义）：Submit 零部署；整包失败零写入；部署失败全回滚 + 可重试；
重复 advance receipt 重放；audit 失败不回滚业务且不重复征召。
Evidence Class=DATA。
"""
import unittest
from unittest import mock
from unittest.mock import MagicMock

from src.core.game_state import GameState
from src.core.systems.political_system import PoliticalSystem
from src.core.systems.military_system import MilitarySystem
from src.core.entities.war import WarStatus
from src.api import senate_api
from src.tests.fixtures import wpgr4_fixtures as F

P1 = F.P1


class _PassVoteDecider:
    def decide_vote(self, issue, faction, state):
        return True


def _view(state, player=P1):
    view = senate_api.get_senate_view(state, player)
    assert view["success"], view.get("message")
    return view["data"]


def _command(war, target, n=0):
    return {"war_id": war.id, "checked": True, "mode": "command",
            "target_commander_id": target, "reinforcement_n": n}


def _submit(state, drafts, player=P1):
    return senate_api.propose_many(state, player, {"war_drafts": drafts})


def _resolve(state):
    return senate_api.resolve_senate(state, vote_decider=_PassVoteDecider())


def _codes(result):
    return [e.get("code") for e in (result.get("errors") or [])]


class TestT01DeferredDeploymentPreservesSelection(unittest.TestCase):
    """T-R4-01 → R5：Submit 零部署 → resolve 只 finalize → 边界 advance 原子部署 exactly-once；
    receipt 跨重入重放（不重复部署）。"""

    def test_t01_reserve_submit_zero_deploy_then_second_proposal_then_advance(self):
        ctx = F.build_fix01()
        state, consul, war_a = ctx["state"], ctx["consul"], ctx["war_a"]
        dto = _view(state)
        card = next(c for c in dto["war_cards"] if c["war_id"] == war_a.id)
        self.assertIsNone(card["current_commander_id"])  # commanderless C 战活在卡中

        sub = _submit(state, [_command(war_a, consul.id, 2)])
        self.assertTrue(sub["success"], sub.get("errors"))
        # Submit 零部署副作用：Commander/legion/absent 均未变
        self.assertIsNone(war_a.commander_id)
        self.assertEqual(war_a.legion_numbers, [])
        self.assertFalse(consul.is_absent, "Submit 不置 absent（执政官留城）")
        self.assertTrue(state.senate_proposal_decision_complete)
        self.assertFalse(state.get_phase_result("senate"), "Submit 不收敛 R")
        self.assertEqual(state.get_senate_direct_actions(), [], "Submit 不写边界记录")

        resolved = _resolve(state)
        self.assertTrue(resolved["success"], resolved.get("message"))
        self.assertTrue(state.get_phase_result("senate"))
        self.assertFalse(state.is_phase_executed("senate"), "R 不等于执行")

        deploy = senate_api.advance_senate_phase(state, P1)
        self.assertTrue(deploy["success"], deploy.get("message"))
        self.assertEqual(war_a.commander_id, consul.id)
        self.assertTrue(consul.is_absent, "部署边界才 absent")
        self.assertEqual(len(war_a.legion_numbers), 2, "完整 N 兑现")
        self.assertTrue(state.is_phase_executed("senate"))
        receipt = state.get_war_execution_receipt_for_session(state.get_senate_session())
        self.assertIsNotNone(receipt)
        self.assertEqual(receipt["status"], "COMMITTED")
        das = [a for a in state.get_senate_direct_actions() if a.get("kind") == "war_resolution"]
        self.assertEqual(len(das), 1, "边界恰一次")

        # refresh/重入：receipt 重放优先 → 不重复部署
        again = senate_api.advance_senate_phase(state, P1)
        self.assertTrue(again["success"])
        self.assertIs(again["data"]["replayed"], True)
        self.assertEqual(len([a for a in state.get_senate_direct_actions()
                              if a.get("kind") == "war_resolution"]), 1)

    def test_t01_oracle_a_assign_fleets_skips_locked_pending_target(self):
        """Oracle-A → R5：Submit 对 naval-required commanderless 战零舰队/Commander/absent
        变化；部署仅边界承担。"""
        state = F.make_base_state(turn_number=1, year=-282)
        faction = F.add_faction(state, treasury=500)
        F.add_player(state)
        consul = F.add_consul(state, faction)
        state._treasury = 500
        war = F.make_war("naval_cmdless", "Naval Commanderless", status=WarStatus.ACTIVE,
                         naval_required=True, enemy_naval=18, commander_id=None)
        F.attach_active(state, war)
        ns = state.naval_system
        from src.core.entities.fleet import Fleet, FleetStatus
        fl = Fleet(number=1, fleet_type="trireme")
        fl._strength_base = 3
        fl._status = FleetStatus.AVAILABLE
        ns._fleets[1] = fl

        sub = _submit(state, [_command(war, consul.id, 1)])
        self.assertTrue(sub["success"], sub.get("errors"))
        # Submit 零绑舰/零任命
        self.assertIsNone(war.commander_id)
        self.assertEqual(war.assigned_fleet_ids, [], "Submit 不得绑舰")
        self.assertEqual(ns.get_fleets_by_war(war.id), [], "Fleet owner 零变化")
        self.assertEqual(fl.status, FleetStatus.AVAILABLE)
        self.assertFalse(consul.is_absent)

        resolved = _resolve(state)
        self.assertTrue(resolved["success"], resolved.get("message"))
        adv = senate_api.advance_senate_phase(state, P1)
        self.assertTrue(adv["success"], adv.get("message"))
        self.assertEqual(war.commander_id, consul.id)


class TestT02SubmitNeverDeploysOrSettles(unittest.TestCase):
    """T-R4-02 → R5：Submit 零部署（边界事务 0 次）；提案进入 Vote/Veto 链；整包失败零写入；
    AI 路径无直连 mutation。"""

    def test_t02_submit_deploy_owner_zero_and_no_settlement(self):
        ctx = F.build_fix01()
        state, consul, war_a = ctx["state"], ctx["consul"], ctx["war_a"]
        calls = {"commit": 0}
        orig_commit = PoliticalSystem.commit_war_resolution

        def counting_commit(self_, plan, transaction=None):
            calls["commit"] += 1
            return orig_commit(self_, plan, transaction)

        with mock.patch.object(PoliticalSystem, "commit_war_resolution", counting_commit):
            s = _submit(state, [_command(war_a, consul.id, 2)])
            self.assertTrue(s["success"], s.get("errors"))
        self.assertEqual(calls["commit"], 0, "Submit 不得触发部署事务")
        self.assertIsNone(war_a.commander_id)
        self.assertFalse(consul.is_absent)
        self.assertEqual(state.get_senate_direct_actions(), [], "Submit 不写边界记录")
        # R6（SA §A.1/§A.3，DA-2 B1）：ongoing command ⇒ route=`consul_direct`
        # ⇒ Senate 账本空 + 恰一条 FROZEN direct 决策（Submit 只冻结、不早部署/不结算）。
        self.assertEqual(state.get_senate_proposals(), [])
        self.assertEqual((s.get("data") or {}).get("created"), [])
        session = state.get_senate_session()
        decisions = state.get_consul_war_decisions(session)
        self.assertEqual(len(decisions), 1, "direct 决策恰一条（冻结）")
        rec = list(decisions.values())[0]
        self.assertEqual(rec["authority"], "consul_direct")
        self.assertEqual(rec["decision_state"], "FROZEN")
        self.assertEqual(rec["war_id"], war_a.id)
        self.assertEqual(rec["payload"]["target_commander_id"], consul.id)
        self.assertEqual(rec["payload"]["reinforcement_n"], 2)
        # 边界前恒 awaiting_boundary（不宣称早部署）+ 阶段未结算/未推进
        row = next(r for r in _view(state)["consul_direct_decisions"] if r["war_id"] == war_a.id)
        self.assertEqual(row["execution"], "awaiting_boundary",
                         "Submit 后边界未执行（零部署）")
        self.assertFalse(state.get_phase_result("senate"))
        self.assertFalse(state.is_phase_executed("senate"))
        self.assertFalse(_view(state)["can_advance"], "未结算 ⇒ 不可推进")

    def test_t02_whole_package_failure_zero_write(self):
        """同一 Commander 被两张卡 claim → COMMANDER_CLAIM_DUPLICATE → 整包零发布；
        改为合法包可重试。"""
        ctx = F.build_fix01()
        state, consul = ctx["state"], ctx["consul"]
        war_a, war_b = ctx["war_a"], ctx["war_b"]
        s = _submit(state, [_command(war_a, consul.id, 0), _command(war_b, consul.id, 0)])
        self.assertFalse(s["success"], "同人双 claim → 整包拒绝")
        self.assertIn("COMMANDER_CLAIM_DUPLICATE", _codes(s))
        self.assertEqual(state.get_senate_proposals(), [], "失败零发布（Senate 账本空）")
        self.assertFalse(state.senate_proposal_decision_complete)
        # R6 双账本：失败零发布 ⇒ direct 账本亦零写
        self.assertEqual(state.get_consul_war_decisions(state.get_senate_session()), {},
                         "失败零发布（direct 账本空）")
        # 可重试：单卡合法包成功（ongoing command ⇒ direct，无 Senate 提案）
        s2 = _submit(state, [_command(war_a, consul.id, 0)])
        self.assertTrue(s2["success"], s2.get("errors"))
        self.assertEqual(state.get_senate_proposals(), [], "ongoing command ⇒ 无 Senate 提案")
        self.assertEqual((s2.get("data") or {}).get("created"), [])
        decisions = state.get_consul_war_decisions(state.get_senate_session())
        self.assertEqual(len(decisions), 1, "重试成功 ⇒ direct 决策恰一条")
        rec = list(decisions.values())[0]
        self.assertEqual(rec["war_id"], war_a.id)
        self.assertEqual(rec["authority"], "consul_direct")
        self.assertEqual(rec["decision_state"], "FROZEN")

    def test_t02_ai_single_commitment_no_direct_mutation(self):
        """AI parity → R5：旧 AI 直连接管入口退役；AI 路径经唯一整包入口、零边界 mutation。"""
        state = F.make_base_state(turn_number=1, year=-282)
        faction = F.add_faction(state, treasury=500)
        F.add_player(state)
        consul = F.add_consul(state, faction)
        state._treasury = 500
        war1 = F.make_war("c1", "C War 1", status=WarStatus.ACTIVE)
        war2 = F.make_war("c2", "C War 2", status=WarStatus.ACTIVE)
        F.attach_active(state, war1)
        F.attach_active(state, war2)
        politics = PoliticalSystem(state)
        self.assertFalse(hasattr(politics, "plan_ai_takeovers"))
        self.assertFalse(hasattr(politics, "execute_ai_takeover_direct_action"))

        calls = {"commit": 0}
        orig_commit = PoliticalSystem.commit_war_resolution

        def counting_commit(self_, plan, transaction=None):
            calls["commit"] += 1
            return orig_commit(self_, plan, transaction)

        with mock.patch.object(PoliticalSystem, "commit_war_resolution", counting_commit):
            result = senate_api.auto_submit_proposals(state, land_proposal_deciders=[])
        self.assertTrue(result["success"], result.get("message"))
        self.assertEqual(calls["commit"], 0, "AI 路径零直接 mutation")
        self.assertIsNone(war1.commander_id)
        self.assertIsNone(war2.commander_id)
        self.assertIsNone(state.get_takeover_pending())
        self.assertFalse(consul.is_absent)


class TestT03RefreshReentryRepeatExactlyOnceDeploy(unittest.TestCase):
    """T-R4-03 + Oracle-B → R5：边界部署 F1~F5 注入全回滚 + 可重试 exactly-once。

    注入点改为 R5 真实生产点：`_strict_recruit_and_bind` / `MilitarySystem.recruit_legion` /
    `GameState.record_war_execution_receipt` / `GameState.mark_phase_executed`（commit-finalization）。
    """

    def _ready_for_advance(self, ctx, n=2):
        state = ctx["state"]
        s = _submit(state, [_command(ctx["war_a"], ctx["consul"].id, n)])
        assert s["success"], s.get("errors")
        resolved = _resolve(state)
        assert resolved["success"], resolved.get("message")
        return state

    def _assert_full_rollback(self, state, ctx, n):
        war_a, consul = ctx["war_a"], ctx["consul"]
        self.assertIsNone(war_a.commander_id, "Commander 回滚")
        self.assertFalse(consul.is_absent, "absent 回滚")
        self.assertEqual(war_a.status, WarStatus.ACTIVE)
        self.assertEqual(war_a.legion_numbers, [], "recruit 回滚")
        ms = state.get_military_system()
        self.assertGreaterEqual(len(ms.get_available_legions()), n, "增援池回滚")
        self.assertFalse(state.is_phase_executed("senate"), "Senate not executed")
        self.assertIsNone(state.get_war_execution_receipt_for_session(state.get_senate_session()),
                          "receipt 回滚（零部分提交）")
        self.assertEqual([a for a in state.get_senate_direct_actions()
                          if a.get("kind") == "war_resolution"], [], "no 边界记录")

    def test_t03_refresh_reentry_repeat_no_duplicate(self):
        ctx = F.build_fix01()
        state = self._ready_for_advance(ctx)
        adv = senate_api.advance_senate_phase(state, P1)
        self.assertTrue(adv["success"], adv.get("message"))
        # repeat advance → receipt 重放（不重复部署）
        for _ in range(2):
            again = senate_api.advance_senate_phase(state, P1)
            self.assertTrue(again["success"])
            self.assertIs(again["data"]["replayed"], True)
        deploy_das = [a for a in state.get_senate_direct_actions()
                      if a.get("kind") == "war_resolution"]
        self.assertEqual(len(deploy_das), 1, "exactly-once 边界记录")

    def test_t03_f1_failure_before_force_rebind_full_rollback(self):
        ctx = F.build_fix01()
        state = self._ready_for_advance(ctx)
        with mock.patch.object(PoliticalSystem, "_strict_recruit_and_bind",
                               side_effect=RuntimeError("F1 injected before force rebind")):
            adv = senate_api.advance_senate_phase(state, P1)
        self.assertFalse(adv["success"])
        self._assert_full_rollback(state, ctx, 2)
        adv2 = senate_api.advance_senate_phase(state, P1)
        self.assertTrue(adv2["success"], adv2.get("message"))
        self.assertTrue(state.is_phase_executed("senate"))

    def test_t03_f2_partial_recruit_failure_full_rollback(self):
        ctx = F.build_fix01()
        state = self._ready_for_advance(ctx)
        ms = state.get_military_system()
        pool_before = len(ms.get_available_legions())
        treasury_before = state.treasury
        orig_recruit = MilitarySystem.recruit_legion
        calls = {"n": 0}

        def flaky_recruit(self_, number):
            calls["n"] += 1
            if calls["n"] == 2:
                raise RuntimeError("F2 injected partial reinforcement recruit failure")
            return orig_recruit(self_, number)

        with mock.patch.object(MilitarySystem, "recruit_legion", flaky_recruit):
            adv = senate_api.advance_senate_phase(state, P1)
        self.assertFalse(adv["success"])
        self._assert_full_rollback(state, ctx, 2)
        self.assertEqual(len(ms.get_available_legions()), pool_before, "增援池完全回滚")
        self.assertEqual(state.treasury, treasury_before, "treasury 恢复")
        adv2 = senate_api.advance_senate_phase(state, P1)
        self.assertTrue(adv2["success"], adv2.get("message"))

    def test_t03_f3_failure_immediately_before_commit_point(self):
        ctx = F.build_fix01()
        state = self._ready_for_advance(ctx)
        with mock.patch.object(GameState, "record_war_execution_receipt",
                               side_effect=RuntimeError("F3 injected at commit point")):
            adv = senate_api.advance_senate_phase(state, P1)
        self.assertFalse(adv["success"])
        self._assert_full_rollback(state, ctx, 2)
        adv2 = senate_api.advance_senate_phase(state, P1)
        self.assertTrue(adv2["success"], adv2.get("message"))
        deploy_das = [a for a in state.get_senate_direct_actions()
                      if a.get("kind") == "war_resolution"]
        self.assertEqual(len(deploy_das), 1)

    def test_t03_f3b_commit_finalization_partial_failure_rollback(self):
        """F3b：receipt 写入后、mark_phase_executed 前/中注入 → 全回滚 + retry exactly once。"""
        ctx = F.build_fix01()
        state = self._ready_for_advance(ctx)
        ms = state.get_military_system()
        pool_before = len(ms.get_available_legions())
        treasury_before = state.treasury
        orig_mark = GameState.mark_phase_executed

        def flaky_mark(self_, phase_name):
            if phase_name == "senate" and not flaky_mark.fired:
                flaky_mark.fired = True
                raise RuntimeError("F3b injected inside commit-finalization")
            return orig_mark(self_, phase_name)
        flaky_mark.fired = False

        with mock.patch.object(GameState, "mark_phase_executed", flaky_mark):
            adv = senate_api.advance_senate_phase(state, P1)
        self.assertFalse(adv["success"])
        self.assertTrue(flaky_mark.fired)
        self._assert_full_rollback(state, ctx, 2)
        self.assertEqual(len(ms.get_available_legions()), pool_before)
        self.assertEqual(state.treasury, treasury_before)
        adv2 = senate_api.advance_senate_phase(state, P1)
        self.assertTrue(adv2["success"], adv2.get("message"))
        self.assertTrue(state.is_phase_executed("senate"))
        self.assertEqual(ctx["war_a"].commander_id, ctx["consul"].id)
        deploy_das = [a for a in state.get_senate_direct_actions()
                      if a.get("kind") == "war_resolution"]
        self.assertEqual(len(deploy_das), 1)

    def test_t03_f4_audit_failure_business_stays_committed(self):
        """F4：audit/event 失败 → 业务保持 committed、不重跑军事部署、无重复 recruit。"""
        ctx = F.build_fix01()
        state = self._ready_for_advance(ctx)
        war_a, consul = ctx["war_a"], ctx["consul"]
        orig_record = GameState.record_senate_direct_action
        calls = {"audit": 0}

        def flaky_record(self_, action):
            calls["audit"] += 1
            if calls["audit"] == 1:
                raise RuntimeError("F4 injected audit emission failure")
            return orig_record(self_, action)

        with mock.patch.object(GameState, "record_senate_direct_action", flaky_record):
            adv = senate_api.advance_senate_phase(state, P1)
        self.assertTrue(adv["success"], "audit 失败不回滚业务（独立上报）")
        self.assertTrue(state.is_phase_executed("senate"))
        self.assertEqual(war_a.commander_id, consul.id)
        # receipt 已在（业务 committed）→ 重试 advance 为重放，不重复征召
        again = senate_api.advance_senate_phase(state, P1)
        self.assertTrue(again["success"])
        self.assertIs(again["data"]["replayed"], True)
        self.assertEqual(len(war_a.legion_numbers), 2, "恰一次完整 N")


if __name__ == "__main__":
    unittest.main()
