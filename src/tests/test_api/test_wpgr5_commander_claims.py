# src/tests/test_api/test_wpgr5_commander_claims.py
"""WP-G-R5 DA-1/DA-2 (§2.5/§3.3) — Commander Claim 模型与 Submit 唯一性。

覆盖 Owner §20 #10 / #11 / #12 / #13 / #14；B-AC05 / B-AC06 / B-AC07。
"""
import unittest

from src.core.systems.political_system import PoliticalSystem

from src.tests.fixtures.wpgr5_fixtures import (
    build_r5_base, FIXED, submit_request, command_draft, peace_draft, error_codes,
)


class TestCommanderClaims(unittest.TestCase):
    def setUp(self):
        self.ctx = build_r5_base()
        self.state = self.ctx["state"]
        self.ps = PoliticalSystem(self.state)

    def _claims(self, drafts, declarations=None):
        real_wars = [self.ctx["war_ongoing"], self.ctx["war_peace"], self.ctx["war_passive"]]
        canonical = self.ps.normalize_war_drafts(drafts)
        return self.ps.build_commander_claims(
            real_wars, canonical, declarations or [])

    def test_unchecked_claims(self):
        """§20 #10：unchecked real War 仍保留现任 Commander claim（retained_unchecked）。"""
        claims = self._claims([command_draft(FIXED["war_ongoing"], self.ctx["cmd_a"].id, checked=False)])
        by_war = {c["war_id"]: c for c in claims if c["commander_id"] is not None}
        self.assertEqual(by_war[FIXED["war_ongoing"]]["commander_id"], self.ctx["cmd_a"].id)
        self.assertEqual(by_war[FIXED["war_ongoing"]]["basis"], "retained_unchecked")
        self.assertEqual(by_war[FIXED["war_peace"]]["basis"], "retained_unchecked")

    def test_candidate_unchecked_no_claim(self):
        """§20 #11：unchecked active-declaration candidate 不产生 claim（默认 Consul 不占用）。"""
        declarations = [{"war_id": FIXED["war_threat"], "name": "Threat War"}]
        claims = self._claims([], declarations)
        war_ids = {c["war_id"] for c in claims}
        self.assertNotIn(FIXED["war_threat"], war_ids)

    def test_peace_retains_claim(self):
        """§20 #14：Peace War 保留现任 Commander claim（不看缓存 target）。"""
        claims = self._claims([peace_draft(FIXED["war_peace"])])
        by_war = {c["war_id"]: c for c in claims if c["commander_id"] is not None}
        self.assertEqual(by_war[FIXED["war_peace"]]["basis"], "retained_peace")
        self.assertEqual(by_war[FIXED["war_peace"]]["commander_id"], self.ctx["cmd_b"].id)

    def test_selected_command_claim(self):
        """checked command → selected target claim，替换旧 claim。"""
        claims = self._claims([command_draft(FIXED["war_ongoing"], self.ctx["cmd_b"].id)])
        by_war = {c["war_id"]: c for c in claims if c["commander_id"] is not None}
        self.assertEqual(by_war[FIXED["war_ongoing"]]["basis"], "selected_command")
        self.assertEqual(by_war[FIXED["war_ongoing"]]["commander_id"], self.ctx["cmd_b"].id)


class TestClaimSubmit(unittest.TestCase):
    def setUp(self):
        self.ctx = build_r5_base()
        self.state = self.ctx["state"]
        self.ps = PoliticalSystem(self.state)

    def test_duplicate_claim(self):
        """§20 #12：同 target Commander 被不同 War claim → 整包失败（COMMANDER_CLAIM_DUPLICATE）。"""
        req = submit_request(war_drafts=[
            command_draft(FIXED["war_ongoing"], self.ctx["cmd_b"].id),
            command_draft(FIXED["war_passive"], self.ctx["cmd_b"].id),
        ])
        result = self.ps.submit_proposal_package("player1", req)
        self.assertFalse(result["success"])
        self.assertIn("COMMANDER_CLAIM_DUPLICATE", error_codes(result))
        self.assertEqual(self.state.get_senate_proposals(), [])

    def test_unique_swap(self):
        """§20 #13：A↔B swap（unique target claims）→ 接受，零绑定变化。"""
        req = submit_request(war_drafts=[
            command_draft(FIXED["war_ongoing"], self.ctx["cmd_b"].id),
            command_draft(FIXED["war_peace"], self.ctx["cmd_a"].id),
        ])
        result = self.ps.submit_proposal_package("player1", req)
        self.assertTrue(result["success"], result.get("errors"))
        # 零绑定变化（Submit 不部署）
        self.assertEqual(self.ctx["war_ongoing"].commander_id, self.ctx["cmd_a"].id)
        self.assertEqual(self.ctx["war_peace"].commander_id, self.ctx["cmd_b"].id)

    def test_retained_vs_candidate(self):
        """B-AC05：A unchecked 保留甲 + B checked→甲 → duplicate；unchecked candidate 默认甲不冲突。"""
        # A(unchecked, retains cmd_a) + passive checked→cmd_a → duplicate
        req = submit_request(war_drafts=[
            command_draft(FIXED["war_ongoing"], self.ctx["consul_id"], checked=False),
            command_draft(FIXED["war_passive"], self.ctx["cmd_a"].id),
        ])
        result = self.ps.submit_proposal_package("player1", req)
        self.assertFalse(result["success"])
        self.assertIn("COMMANDER_CLAIM_DUPLICATE", error_codes(result))

        # 另一 unchecked candidate（默认甲，无 claim）→ 不冲突
        declarations = [{"war_id": FIXED["war_threat"], "name": "Threat War"}]
        claims = self.ps.build_commander_claims(
            [self.ctx["war_ongoing"]], self.ps.normalize_war_drafts([]), declarations)
        war_ids = {c["war_id"] for c in claims}
        self.assertNotIn(FIXED["war_threat"], war_ids)

    def test_peace_claim_conflict(self):
        """B-AC07：A Peace 保留甲 + B checked→甲 → duplicate；不预释放。"""
        req = submit_request(war_drafts=[
            peace_draft(FIXED["war_peace"]),                       # retains cmd_b
            command_draft(FIXED["war_ongoing"], self.ctx["cmd_b"].id),
        ])
        result = self.ps.submit_proposal_package("player1", req)
        self.assertFalse(result["success"])
        self.assertIn("COMMANDER_CLAIM_DUPLICATE", error_codes(result))


if __name__ == "__main__":
    unittest.main()
