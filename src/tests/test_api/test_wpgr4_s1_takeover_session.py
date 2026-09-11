# src/tests/test_api/test_wpgr4_s1_takeover_session.py
"""WP-G-R4 S1（R4-G-01，SA v1.7 §8.1 A）— Human Takeover Deferred Decision/Deployment
Lifecycle（O5/OD-R4-06）。T01/T02/T03 + Oracle-A（P1-01 pending-target 免配舰）+
Oracle-B（P1-02 部署事务 failure injection F1~F5 + F3b）。Evidence Class=DATA（SC-R4-A）。

权威：SA-Design-WP-G-R4-2026-09-07.md v1.7（FROZEN）§2.2/§2.3/§2.4b/§2.5/§8.4；
R4 任务包 v1.1 §5/§11（G01 接受准则）；DA-Plan-WP-G-R4 §1 S1。
R3 §1（Takeover 自动 finish/空结算）由 OD-R4-05/06 supersede（ledger 逐条依据见注释）。

TDD 必红主因（baseline 775dbfc）：takeover_war 立即部署+置 decision_complete+空结算；
advance 无部署 owner/无回滚；assign_fleets 对 pending 目标战提前绑舰；无 T/V 持有者。
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


def _view(state, player=P1):
    view = senate_api.get_senate_view(state, player)
    assert view["success"], view.get("message")
    return view["data"]


class TestT01DeferredDeploymentPreservesSelection(unittest.TestCase):
    """T-R4-01：reserve→Submit 锁 T 零部署→另一合法非空提案→vote/veto/resolve
    （pending-aware M 放行）→显式 advance 原子部署 exactly-once；T/V 跨 settlement 存续。"""

    def _lock_takeover(self, ctx, n=2):
        state = ctx["state"]
        r = senate_api.takeover_war(state, P1, ctx["war_a"].id, n, action="reserve")
        self.assertTrue(r["success"], r.get("message"))
        s = senate_api.takeover_war(state, P1, ctx["war_a"].id, n, action="submit")
        self.assertTrue(s["success"], s.get("message"))
        return s

    def test_t01_reserve_submit_zero_deploy_then_second_proposal_then_advance(self):
        ctx = F.build_fix01()
        state, consul, war_a = ctx["state"], ctx["consul"], ctx["war_a"]
        dto = _view(state)
        self.assertTrue(dto["takeover_required"]["required"])   # M_open：commanderless C 战
        self.assertTrue(dto["takeover_required"]["m_open"])

        # reserve（V=RESERVED）+ Submit（T=LOCKED）零部署
        self._lock_takeover(ctx, n=2)
        pending = state.get_takeover_pending()
        self.assertIsNotNone(pending)
        self.assertEqual(pending["status"], "LOCKED")
        self.assertEqual(pending["war_id"], war_a.id)
        self.assertEqual(pending["reinforcement_n"], 2)
        # 零部署副作用（R4-18）：无 treaty/status/Commander/force/absent
        self.assertIsNone(war_a.commander_id)
        self.assertEqual(war_a.status, WarStatus.ACTIVE)
        self.assertEqual(war_a.legion_numbers, [])
        self.assertFalse(consul.is_absent, "R4-17：Submit 不置 absent（执政官留城）")
        self.assertFalse(state.senate_proposal_decision_complete, "Submit 不写 P（不关闭选择）")
        self.assertFalse(state.get_phase_result("senate"), "Submit 不收敛 R")
        self.assertEqual(state.get_senate_direct_actions(), [], "Submit 不写 D_Takeover")

        # pending-aware M：LOCKED T 覆盖 C 战 → M_open False（resolve/advance 放行，无死锁 R4-18）
        dto = _view(state)
        self.assertFalse(dto["takeover_required"]["m_open"])
        self.assertTrue(dto["takeover_required"]["m_deploy_ready"])
        self.assertFalse(dto["takeover_required"]["required"])

        # 显式空结束写 P（跨 settlement 前 T 存续）→ resolve（M 放行）→ 真实 R
        empty = senate_api.propose_many(state, P1, [])
        self.assertTrue(empty["success"])
        self.assertTrue(state.senate_proposal_decision_complete)
        resolved = senate_api.resolve_senate(state)
        self.assertTrue(resolved["success"], resolved.get("message"))
        self.assertTrue(state.get_phase_result("senate"))
        # T 跨 settlement 存续（P1-RF-02）：resolve 的 clear_senate_pending 不清 _takeover_pending
        self.assertEqual(state.get_takeover_pending()["status"], "LOCKED")
        state.clear_senate_pending()
        self.assertEqual(state.get_takeover_pending()["status"], "LOCKED",
                         "clear_senate_pending 永不触碰 _takeover_pending")
        self.assertFalse(state.is_phase_executed("senate"))

        # 显式 advance → 原子部署恰一次
        deploy = senate_api.advance_senate_phase(state, P1)
        self.assertTrue(deploy["success"], deploy.get("message"))
        self.assertEqual(war_a.commander_id, consul.id)
        self.assertTrue(consul.is_absent, "O5：部署边界才 absent")
        self.assertEqual(len(war_a.legion_numbers), 2, "完整 N 兑现")
        self.assertEqual(state.get_takeover_pending()["status"], "CONSUMED")
        self.assertTrue(state.is_phase_executed("senate"))
        # D_Takeover 恰一次（POST-COMMIT AUDIT，exactly-once 键）
        das = [a for a in state.get_senate_direct_actions() if a.get("kind") == "takeover_deploy"]
        self.assertEqual(len(das), 1)
        self.assertTrue(das[0]["exactly_once_key"].startswith(f"takeover_deploy:{war_a.id}:"))

        # refresh/重入不重复（F5）
        again = senate_api.advance_senate_phase(state, P1)
        self.assertFalse(again["success"])
        self.assertEqual(len([a for a in state.get_senate_direct_actions()
                              if a.get("kind") == "takeover_deploy"]), 1)

    def test_t01_oracle_a_assign_fleets_skips_locked_pending_target(self):
        """Oracle-A（SA v1.7 §8.4 P1-01）：naval-required commanderless ACTIVE + LOCKED T →
        resolve_senate 后 assigned_fleet_ids/Fleet owner 零变化、T 保持 LOCKED；仅 advance 后部署。"""
        state = F.make_base_state(turn_number=1, year=-282)
        faction = F.add_faction(state, treasury=500)
        F.add_player(state)
        consul = F.add_consul(state, faction)
        state._treasury = 500
        war = F.make_war("naval_cmdless", "Naval Commanderless", status=WarStatus.ACTIVE,
                         naval_required=True, enemy_naval=18, commander_id=None)
        F.attach_active(state, war)
        # available fleet（未指派——正常 Senate 自动配舰会吃掉它；R4 必须跳过 pending 目标战）
        ns = state.naval_system
        from src.core.entities.fleet import Fleet, FleetStatus
        fl = Fleet(number=1, fleet_type="trireme")
        fl._strength_base = 3
        fl._status = FleetStatus.AVAILABLE
        ns._fleets[1] = fl

        self.assertTrue(senate_api.takeover_war(state, P1, war.id, 1, action="reserve")["success"])
        self.assertTrue(senate_api.takeover_war(state, P1, war.id, 1, action="submit")["success"])
        self.assertTrue(senate_api.propose_many(state, P1, [])["success"])
        resolved = senate_api.resolve_senate(state)
        self.assertTrue(resolved["success"], resolved.get("message"))
        # 零变化（Oracle-A 硬断言）
        self.assertEqual(war.assigned_fleet_ids, [], "resolve 不得对 LOCKED pending 目标战绑舰")
        self.assertEqual(ns.get_fleets_by_war(war.id), [], "Fleet owner 零变化（未绑舰）")
        self.assertEqual(fl.status, FleetStatus.AVAILABLE)
        self.assertEqual(state.get_takeover_pending()["status"], "LOCKED")
        self.assertFalse(consul.is_absent)
        # 显式 advance → 部署恰一次（此战不 naval-required deploy 逻辑仍适用 commander 指派）
        adv = senate_api.advance_senate_phase(state, P1)
        self.assertTrue(adv["success"], adv.get("message"))
        self.assertEqual(war.commander_id, consul.id)


class TestT02SubmitNeverDeploysOrSettles(unittest.TestCase):
    """T-R4-02：Submit 零部署副作用（spy 部署 owner 0 次/resolve 0 次）；不置 P；
    Takeover 不进 Vote/Veto；Takeover-only 不隐式 resolve；whole-package 失败零写入；AI parity。"""

    def test_t02_submit_deploy_owner_zero_and_no_settlement(self):
        ctx = F.build_fix01()
        state, consul, war_a = ctx["state"], ctx["consul"], ctx["war_a"]
        calls = {"deploy": 0, "resolve": 0}
        orig_deploy = PoliticalSystem.execute_war_takeover_deploy

        def counting_deploy(self_, war_, consul_, reinforcement_n=None):
            calls["deploy"] += 1
            return orig_deploy(self_, war_, consul_, reinforcement_n=reinforcement_n)

        orig_resolve = senate_api.resolve_senate

        def counting_resolve(state_, vote_decider=None):
            calls["resolve"] += 1
            return orig_resolve(state_, vote_decider)

        with mock.patch.object(PoliticalSystem, "execute_war_takeover_deploy", counting_deploy), \
             mock.patch.object(senate_api, "resolve_senate", counting_resolve):
            r = senate_api.takeover_war(state, P1, war_a.id, 2, action="reserve")
            self.assertTrue(r["success"])
            s = senate_api.takeover_war(state, P1, war_a.id, 2, action="submit")
            self.assertTrue(s["success"], s.get("message"))
        self.assertEqual(calls["deploy"], 0, "Submit 不得触发部署 mutation")
        self.assertEqual(calls["resolve"], 0, "Submit 不得隐式 resolve_senate")
        self.assertIsNone(war_a.commander_id)
        self.assertFalse(consul.is_absent)
        self.assertEqual(state.get_senate_proposals(), [], "Takeover 不产生 Vote/Veto 提案")
        self.assertEqual(state.get_senate_votes_copy(), {})
        self.assertFalse(state.senate_proposal_decision_complete)
        self.assertFalse(state.get_phase_result("senate"))
        self.assertFalse(state.is_phase_executed("senate"))
        dto = _view(state)
        self.assertEqual(dto["current_step"], "proposal", "Takeover-only Submit 停留 selection")

    def test_t02_whole_package_failure_zero_write(self):
        """C 非空时对 P 战（TRUCE+pending）Submit → whole-package 拒绝（C 优先单 commitment）；
        T 留 RESERVED、不写 P、reservation 保持可重试（P1-RF-02）。"""
        ctx = F.build_fix01()
        state = ctx["state"]
        war_b = ctx["war_b"]
        r = senate_api.takeover_war(state, P1, war_b.id, 1, action="reserve")
        self.assertTrue(r["success"], r.get("message"))
        s = senate_api.takeover_war(state, P1, war_b.id, 1, action="submit")
        self.assertFalse(s["success"], "C 非空 → P 战不可锁（C 优先）")
        pending = state.get_takeover_pending()
        self.assertEqual(pending["status"], "RESERVED", "失败零写入：留 RESERVED")
        self.assertFalse(state.senate_proposal_decision_complete)
        self.assertEqual(state.get_senate_proposals(), [])
        # 可编辑重试：reserve 换目标 war_a（单 reservation 覆盖）→ submit 成功锁 C 战
        r2 = senate_api.takeover_war(state, P1, ctx["war_a"].id, 1, action="reserve")
        self.assertTrue(r2["success"], r2.get("message"))
        s2 = senate_api.takeover_war(state, P1, ctx["war_a"].id, 1, action="submit")
        self.assertTrue(s2["success"], s2.get("message"))
        self.assertEqual(state.get_takeover_pending()["status"], "LOCKED")

    def test_t02_ai_single_commitment_no_direct_mutation(self):
        """AI parity（R4-24）：多 eligible C 战 → plan 单 commitment（至多 1 LOCKED T）；
        execute_ai_takeover_direct_action 不直接 mutation（部署 owner spy 0 次）。"""
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
        plan = politics.plan_ai_takeovers()
        self.assertLessEqual(len(plan), 1, "单 commitment：至多 1 war")
        if not plan:
            self.skipTest("decider 拒绝全部候选（非断言面）")
        calls = {"deploy": 0}
        orig_deploy = PoliticalSystem.execute_war_takeover_deploy

        def counting(self_, war_, consul_, reinforcement_n=None):
            calls["deploy"] += 1
            return orig_deploy(self_, war_, consul_, reinforcement_n=reinforcement_n)

        with mock.patch.object(PoliticalSystem, "execute_war_takeover_deploy", counting):
            records = politics.execute_ai_takeover_direct_action(predecided=plan)
        self.assertEqual(calls["deploy"], 0, "AI 废弃直连：不得直接 mutation")
        self.assertLessEqual(len(records), 1)
        locked = [w for w in (war1, war2)
                  if state.get_takeover_pending() and state.get_takeover_pending()["war_id"] == w.id]
        self.assertEqual(len(locked), 1 if records else 0)
        if records:
            pending = state.get_takeover_pending()
            self.assertEqual(pending["status"], "LOCKED")
            self.assertIsNone(pending["war_id"] and None if False else locked[0].commander_id)
            self.assertIsNone(locked[0].commander_id, "锁 T 零部署")
            self.assertFalse(consul.is_absent)


class TestT03RefreshReentryRepeatExactlyOnceDeploy(unittest.TestCase):
    """T-R4-03 + Oracle-B（SA v1.7 §8.4）：部署事务 F1~F5 + F3b 六注入。"""

    def _ready_for_advance(self, ctx, n=2):
        state = ctx["state"]
        r = senate_api.takeover_war(state, P1, ctx["war_a"].id, n, action="reserve")
        assert r["success"], r.get("message")
        s = senate_api.takeover_war(state, P1, ctx["war_a"].id, n, action="submit")
        assert s["success"], s.get("message")
        assert senate_api.propose_many(state, P1, [])["success"]
        resolved = senate_api.resolve_senate(state)
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
        pending = state.get_takeover_pending()
        self.assertIsNotNone(pending)
        self.assertEqual(pending["status"], "LOCKED", "T 回 LOCKED")
        self.assertEqual([a for a in state.get_senate_direct_actions()
                          if a.get("kind") == "takeover_deploy"], [], "no D_Takeover")

    def _deploy_owner_patch(self, inject=None):
        orig = PoliticalSystem.execute_war_takeover_deploy

        def wrapped(self_, war_, consul_, reinforcement_n=None):
            if inject == "raise_early":
                raise RuntimeError("F1 injected before force rebind")
            result = orig(self_, war_, consul_, reinforcement_n=reinforcement_n)
            if inject == "raise_after_ops":
                raise RuntimeError("F3 injected immediately before commit point")
            return result
        return mock.patch.object(PoliticalSystem, "execute_war_takeover_deploy", wrapped)

    def test_t03_refresh_reentry_repeat_no_duplicate(self):
        ctx = F.build_fix01()
        state = self._ready_for_advance(ctx)
        # refresh/重入 view 稳定
        for _ in range(2):
            dto = _view(state)
            self.assertTrue(dto["can_advance"])
            self.assertTrue(dto["pending_takeover_locked"])
        adv = senate_api.advance_senate_phase(state, P1)
        self.assertTrue(adv["success"], adv.get("message"))
        # repeat advance → idempotent rejection（F5）
        for _ in range(2):
            again = senate_api.advance_senate_phase(state, P1)
            self.assertFalse(again["success"])
        deploy_das = [a for a in state.get_senate_direct_actions()
                      if a.get("kind") == "takeover_deploy"]
        self.assertEqual(len(deploy_das), 1, "exactly-once D")

    def test_t03_f1_failure_before_force_rebind_full_rollback(self):
        ctx = F.build_fix01()
        state = self._ready_for_advance(ctx)
        with self._deploy_owner_patch(inject="raise_early"):
            adv = senate_api.advance_senate_phase(state, P1)
        self.assertFalse(adv["success"])
        self._assert_full_rollback(state, ctx, 2)
        # retry deploys exactly once
        adv2 = senate_api.advance_senate_phase(state, P1)
        self.assertTrue(adv2["success"], adv2.get("message"))
        self.assertTrue(state.is_phase_executed("senate"))

    def test_t03_f2_partial_recruit_failure_full_rollback(self):
        ctx = F.build_fix01()
        state = self._ready_for_advance(ctx)
        ms = state.get_military_system()
        pool_before = len(ms.get_available_legions())
        treasury_before = state.treasury
        orig_recruit = MilitarySystem.recruit_multiple
        calls = {"n": 0}

        def flaky_recruit(self_, count):
            calls["n"] += 1
            if calls["n"] == 1 and count > 1:
                # 先真实征召 1 个（partial），随后注入失败
                first = orig_recruit(self_, 1)
                raise RuntimeError("F2 injected partial reinforcement recruit failure")
            return orig_recruit(self_, count)

        with mock.patch.object(MilitarySystem, "recruit_multiple", flaky_recruit):
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
        with self._deploy_owner_patch(inject="raise_after_ops"):
            adv = senate_api.advance_senate_phase(state, P1)
        self.assertFalse(adv["success"])
        self._assert_full_rollback(state, ctx, 2)
        adv2 = senate_api.advance_senate_phase(state, P1)
        self.assertTrue(adv2["success"], adv2.get("message"))
        deploy_das = [a for a in state.get_senate_direct_actions()
                      if a.get("kind") == "takeover_deploy"]
        self.assertEqual(len(deploy_das), 1)

    def test_t03_f3b_commit_finalization_partial_failure_rollback(self):
        """F3b（Oracle-B，SA v1.7 §8.4）：T/V→CONSUMED 后、mark_phase_executed 前/中注入 →
        全回滚 + T 回 LOCKED + retry exactly once（production-shape：真实 mark_phase_executed
        调用点 = advance_senate_phase 内两 authoritative publication 之间）。"""
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
        # retry 部署 exactly once（mark 再次调用成功）
        adv2 = senate_api.advance_senate_phase(state, P1)
        self.assertTrue(adv2["success"], adv2.get("message"))
        self.assertTrue(state.is_phase_executed("senate"))
        self.assertEqual(ctx["war_a"].commander_id, ctx["consul"].id)
        deploy_das = [a for a in state.get_senate_direct_actions()
                      if a.get("kind") == "takeover_deploy"]
        self.assertEqual(len(deploy_das), 1)

    def test_t03_f4_audit_failure_business_stays_committed(self):
        """F4：audit/event 失败 → 业务保持 committed、禁止重试军事部署、无重复 recruit。"""
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
        # audit 失败后 D 缺失，但业务 committed——重试 advance 被 is_phase_executed guard 拒
        again = senate_api.advance_senate_phase(state, P1)
        self.assertFalse(again["success"])
        deploy_calls = 0
        # 无重复 recruit：legions == 2（恰好一次完整 N）
        self.assertEqual(len(war_a.legion_numbers), 2)


if __name__ == "__main__":
    unittest.main()
