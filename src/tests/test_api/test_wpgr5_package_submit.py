# src/tests/test_api/test_wpgr5_package_submit.py
"""WP-G-R5 DA-2 (§3.1–§3.9) — 整包 Submit（all-or-nothing / 21 code / 原子发布）。

覆盖 Owner §20 #2 / #6 / #16；B-AC01 / B-AC03 / B-AC14 / B-AC15 / B-AC16 / B-AC17。
"""
import copy
import unittest

from src.api import senate_api
from src.core.systems.political_system import PoliticalSystem

from src.tests.fixtures.wpgr5_fixtures import (
    build_r5_base, FIXED, add_province, submit_request, command_draft, peace_draft,
    error_codes,
)


class TestPackageSubmitBasics(unittest.TestCase):
    def setUp(self):
        self.ctx = build_r5_base()
        self.state = self.ctx["state"]
        self.ps = PoliticalSystem(self.state)

    def test_commander_required(self):
        """§20 #2 / §3.3：checked non-Peace command 缺 Commander → COMMANDER_REQUIRED，created=[]。"""
        req = submit_request(war_drafts=[command_draft(FIXED["war_ongoing"], None)])
        result = self.ps.submit_proposal_package("player1", req)
        self.assertFalse(result["success"])
        self.assertIn("COMMANDER_REQUIRED", error_codes(result))
        self.assertEqual(result["data"]["created"], [])
        self.assertEqual(self.state.get_senate_proposals(), [])

    def test_commander_target_invalid(self):
        """§3.3：target 存在但死亡/非候选 → COMMANDER_INELIGIBLE（此处用不存在 ID → TARGET_INVALID）。"""
        req = submit_request(war_drafts=[command_draft(FIXED["war_ongoing"], 9999)])
        result = self.ps.submit_proposal_package("player1", req)
        self.assertFalse(result["success"])
        self.assertTrue(
            {"COMMANDER_TARGET_INVALID", "COMMANDER_INELIGIBLE"} & set(error_codes(result))
        )

    def test_n_zero_ok(self):
        """§20 #6 / §3.6：N=0 合法（同现任 Commander no-op）。

        R6 迁移（B-1 类 route→direct）：`war_ongoing`（ongoing 真实 War）的 command 模式
        ⇒ `consul_direct`（不再产 Senate 提案）。断言面迁到 R6 双账本 + 唯一边界：
        `created=[]` / `consul_war_decisions` 恰 1（FROZEN、N=0）；边界落地 = 原将保留（no-op）、零增兵。
        """
        req = submit_request(war_drafts=[
            command_draft(FIXED["war_ongoing"], self.ctx["cmd_a"].id, reinforcement_n=0)])
        result = self.ps.submit_proposal_package("player1", req)
        self.assertTrue(result["success"], result.get("errors"))
        # ① 双账本：Senate 提案集不得混入 direct；direct 决策恰 1（FROZEN、N=0）
        props = self.state.get_senate_proposals()
        self.assertEqual(len(props), 0)
        self.assertEqual(result["data"]["created"], [])
        decisions = self.state.get_consul_war_decisions("S1")
        self.assertEqual(len(decisions), 1)
        rec = list(decisions.values())[0]
        self.assertEqual(rec["authority"], "consul_direct")
        self.assertEqual(rec["decision_state"], "FROZEN")
        self.assertEqual(rec["war_id"], FIXED["war_ongoing"])
        self.assertEqual(rec["payload"]["target_commander_id"], self.ctx["cmd_a"].id)
        self.assertEqual(rec["payload"]["reinforcement_n"], 0)
        # ② 唯一边界落地：N=0 同现任 = no-op（原将保留、零增兵）
        res = senate_api.resolve_senate(self.state)
        self.assertTrue(res["success"], res.get("message"))
        pool_before = len(self.state.get_military_system().get_available_legions())
        adv = senate_api.advance_senate_phase(self.state, "player1")
        self.assertTrue(adv["success"], adv.get("message"))
        self.assertEqual(self.ctx["war_ongoing"].commander_id, self.ctx["cmd_a"].id)
        self.assertEqual(len(self.state.get_military_system().get_available_legions()),
                         pool_before)

    def test_reinforcement_invalid(self):
        """§3.6：负/浮点/bool N → REINFORCEMENT_INVALID。"""
        for bad in (-1, 1.5, True):
            self.state.clear_senate_pending()
            req = submit_request(war_drafts=[
                command_draft(FIXED["war_ongoing"], self.ctx["cmd_a"].id, reinforcement_n=bad)])
            result = self.ps.submit_proposal_package("player1", req, {"session": "S-%s" % bad})
            self.assertFalse(result["success"], bad)
            self.assertIn("REINFORCEMENT_INVALID", error_codes(result), bad)

    def test_war_mode_invalid(self):
        """§3.2/§3.9：非法 mode → WAR_MODE_INVALID。"""
        draft = command_draft(FIXED["war_ongoing"], self.ctx["cmd_a"].id)
        draft["mode"] = "banana"
        result = self.ps.submit_proposal_package("player1", submit_request(war_drafts=[draft]))
        self.assertFalse(result["success"])
        self.assertIn("WAR_MODE_INVALID", error_codes(result))

    def test_peace_requires_pending_draft(self):
        """§3.4：对无 pending 草案的真实 War 提 Peace → PEACE_DRAFT_INVALID。"""
        result = self.ps.submit_proposal_package(
            "player1", submit_request(war_drafts=[peace_draft(FIXED["war_ongoing"])]))
        self.assertFalse(result["success"])
        self.assertIn("PEACE_DRAFT_INVALID", error_codes(result))

    def test_not_authorized(self):
        """§3.2 V0 / §3.9：非执政官派系 actor → SUBMIT_NOT_AUTHORIZED。"""
        result = self.ps.submit_proposal_package("no_such_player", submit_request())
        self.assertFalse(result["success"])
        self.assertIn("SUBMIT_NOT_AUTHORIZED", error_codes(result))


class TestAtomicityAndNormalization(unittest.TestCase):
    def setUp(self):
        self.ctx = build_r5_base()
        self.state = self.ctx["state"]
        self.state.add_national_public_land(1000)
        self.ps = PoliticalSystem(self.state)

    def test_atomic_fail_zero_publish(self):
        """B-AC01：含有效普通提案 + 无效 checked command → 整包失败，零发布，保 draft。"""
        req = submit_request(
            war_drafts=[command_draft(FIXED["war_ongoing"], None)],
            proposals=[{"type": "land", "params": {"act_type": "sale", "amount_C": 100}}],
        )
        result = self.ps.submit_proposal_package("player1", req)
        self.assertFalse(result["success"])
        self.assertEqual(result["data"]["created"], [])
        self.assertIs(result["data"]["draft_preserved"], True)
        self.assertEqual(self.state.get_senate_proposals(), [])

    def test_null_current_unchecked_not_rejected(self):
        """B-AC03：null-current 真实 War unchecked → 不因 null 拒绝。"""
        self.ctx["war_ongoing"].commander_id = None
        result = self.ps.submit_proposal_package(
            "player1", submit_request(war_drafts=[command_draft(FIXED["war_ongoing"], None, checked=False)]))
        self.assertTrue(result["success"], result.get("errors"))

    def test_peace_ignores_cached_commander_n(self):
        """B-AC03/§3.4：Peace 忽略缓存 Commander/N，payload 仅含 treaty_snapshot。"""
        draft = peace_draft(FIXED["war_peace"])
        draft["target_commander_id"] = 9999
        draft["reinforcement_n"] = -5
        result = self.ps.submit_proposal_package("player1", submit_request(war_drafts=[draft]))
        self.assertTrue(result["success"], result.get("errors"))
        props = self.state.get_senate_proposals()
        self.assertEqual(len(props), 1)
        payload = props[0]["payload"]
        self.assertIn("treaty_snapshot", payload)
        self.assertNotIn("target_commander_id", payload)
        self.assertNotIn("reinforcement_n", payload)

    def test_peace_snapshot_frozen(self):
        """B-AC14：成功 Peace 后 War treaty 仍 pending；快照深冻结（无 live alias）。"""
        result = self.ps.submit_proposal_package(
            "player1", submit_request(war_drafts=[peace_draft(FIXED["war_peace"])]))
        self.assertTrue(result["success"], result.get("errors"))
        # War treaty 状态未被 Submit 改写（DD-01：禁 peace submit 早写）
        self.assertEqual(self.ctx["war_peace"].peace_treaty["status"], "pending")
        props = self.state.get_senate_proposals()
        snap = props[0]["payload"]["treaty_snapshot"]
        # 篡改客户端原 dict 不影响快照
        self.ctx["war_peace"].peace_treaty["indemnity"] = 99999
        self.assertEqual(snap["indemnity"], 80)

    def test_empty_package(self):
        """B-AC15：空包（unchecked pending-peace / commanderless 真实 War）→ 合法成功。"""
        result = self.ps.submit_proposal_package("player1", submit_request())
        self.assertTrue(result["success"], result.get("errors"))
        self.assertEqual(result["data"]["created"], [])
        self.assertTrue(self.state.senate_proposal_decision_complete)


class TestGovernorConflict(unittest.TestCase):
    def setUp(self):
        self.ctx = build_r5_base()
        self.state = self.ctx["state"]
        add_province(self.state, 11, "Gallia", governor_id=None)
        self.ps = PoliticalSystem(self.state)

    def test_gov_cmd_conflict(self):
        """§20 #16 / §3.5：同人 Governor × War Commander → GOVERNOR_COMMANDER_CONFLICT。"""
        req = submit_request(
            war_drafts=[command_draft(FIXED["war_ongoing"], self.ctx["cmd_gov"].id)],
            proposals=[{"type": "governor", "params": {"province_id": 11,
                                                       "candidate_id": self.ctx["cmd_gov"].id}}],
        )
        result = self.ps.submit_proposal_package("player1", req)
        self.assertFalse(result["success"])
        self.assertIn("GOVERNOR_COMMANDER_CONFLICT", error_codes(result))
        self.assertEqual(self.state.get_senate_proposals(), [])


class TestReplayAndReuse(unittest.TestCase):
    def setUp(self):
        self.ctx = build_r5_base()
        self.state = self.ctx["state"]
        self.ps = PoliticalSystem(self.state)

    def _ok_request(self, target=None, request_id="req-1"):
        return submit_request(
            war_drafts=[command_draft(FIXED["war_ongoing"], target or self.ctx["cmd_a"].id)],
            request_id=request_id)

    def test_replay_same_request(self):
        """B-AC16/§3.8：同 request id 同意图重放 → replayed=true，无新增提案。"""
        r1 = self.ps.submit_proposal_package("player1", self._ok_request())
        self.assertTrue(r1["success"], r1.get("errors"))
        n = len(self.state.get_senate_proposals())
        r2 = self.ps.submit_proposal_package("player1", self._ok_request())
        self.assertTrue(r2["success"])
        self.assertIs(r2["data"].get("replayed"), True)
        self.assertEqual(len(self.state.get_senate_proposals()), n)

    def test_reuse_same_id_diff_intent(self):
        """B-AC16/§3.8：同 id 改意图 → SUBMIT_REQUEST_REUSED。"""
        self.ps.submit_proposal_package("player1", self._ok_request())
        r2 = self.ps.submit_proposal_package(
            "player1", self._ok_request(target=self.ctx["cmd_b"].id))
        self.assertFalse(r2["success"])
        self.assertIn("SUBMIT_REQUEST_REUSED", error_codes(r2))

    def test_different_id_already_submitted(self):
        """B-AC16/§3.8：异 id 再提交 → PACKAGE_ALREADY_SUBMITTED。"""
        self.ps.submit_proposal_package("player1", self._ok_request())
        r2 = self.ps.submit_proposal_package("player1", self._ok_request(request_id="req-2"))
        self.assertFalse(r2["success"])
        self.assertIn("PACKAGE_ALREADY_SUBMITTED", error_codes(r2))


class TestZeroMilitaryMutation(unittest.TestCase):
    def test_zero_military_mutation(self):
        """B-AC17：checked command 同现任 + N=0 → 军事/职位深值不变（零军事写）。"""
        from src.tests.fixtures.wpgr5_fixtures import build_r5_base
        ctx = build_r5_base()
        state = ctx["state"]
        ps = PoliticalSystem(state)
        war = ctx["war_ongoing"]

        before = {
            "commander_id": war.commander_id,
            "status": war.status,
            "activation_turn": war.activation_turn,
            "legion_numbers": list(war.legion_numbers),
            "treaty_status": ctx["war_peace"].peace_treaty["status"],
            "treasury": state.treasury,
            "consul_absent": ctx["consul"].is_absent,
        }
        req = submit_request(war_drafts=[command_draft(war.id, ctx["cmd_a"].id, reinforcement_n=0)])
        result = ps.submit_proposal_package("player1", req)
        self.assertTrue(result["success"], result.get("errors"))
        after = {
            "commander_id": war.commander_id,
            "status": war.status,
            "activation_turn": war.activation_turn,
            "legion_numbers": list(war.legion_numbers),
            "treaty_status": ctx["war_peace"].peace_treaty["status"],
            "treasury": state.treasury,
            "consul_absent": ctx["consul"].is_absent,
        }
        self.assertEqual(before, after)


if __name__ == "__main__":
    unittest.main()
