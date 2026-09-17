# src/tests/test_api/test_wpgr5_legion_pool.py
"""WP-G-R5 DA-2 (§3.6) — 全局 Legion Pool 聚合。

覆盖 Owner §20 #17 / #18 / #19；B-AC10 / B-AC11。
"""
import unittest

from src.core.systems.political_system import PoliticalSystem

from src.tests.fixtures.wpgr5_fixtures import (
    build_r5_base, FIXED, submit_request, command_draft, recruit_legions_for_war,
    error_codes,
)


def _pool_size(state):
    ms = state.get_military_system()
    return len(ms.get_available_legions())


class TestLegionPool(unittest.TestCase):
    def setUp(self):
        self.ctx = build_r5_base()
        self.state = self.ctx["state"]
        self.ps = PoliticalSystem(self.state)

    def test_within_pool(self):
        """§20 #17：Σ N ≤ pool → 接受（N=5）。"""
        pool = _pool_size(self.state)
        self.assertGreaterEqual(pool, 5)
        req = submit_request(war_drafts=[
            command_draft(FIXED["war_ongoing"], self.ctx["cmd_a"].id, reinforcement_n=5)])
        result = self.ps.submit_proposal_package("player1", req)
        self.assertTrue(result["success"], result.get("errors"))

    def test_exceed(self):
        """§20 #18：Σ N > pool → LEGION_POOL_EXCEEDED，整包失败，含 requested/available/reduce_by。"""
        pool = _pool_size(self.state)
        req = submit_request(war_drafts=[
            command_draft(FIXED["war_ongoing"], self.ctx["cmd_a"].id, reinforcement_n=pool + 1)])
        result = self.ps.submit_proposal_package("player1", req)
        self.assertFalse(result["success"])
        self.assertIn("LEGION_POOL_EXCEEDED", error_codes(result))
        err = next(e for e in result["errors"] if e["code"] == "LEGION_POOL_EXCEEDED")
        self.assertEqual(err["details"]["requested_total"], pool + 1)
        self.assertEqual(err["details"]["available_total"], pool)
        self.assertEqual(err["details"]["reduce_by"], 1)

    def test_pool_boundary_equal(self):
        """B-AC10：Σ N == pool 接受。"""
        pool = _pool_size(self.state)
        req = submit_request(war_drafts=[
            command_draft(FIXED["war_ongoing"], self.ctx["cmd_a"].id, reinforcement_n=pool)])
        result = self.ps.submit_proposal_package("player1", req)
        self.assertTrue(result["success"], result.get("errors"))

    def test_all_zero_accepted(self):
        """B-AC10：全零请求接受（treasury 零/负不影响）。"""
        self.state._treasury = -100
        req = submit_request(war_drafts=[
            command_draft(FIXED["war_ongoing"], self.ctx["cmd_a"].id, reinforcement_n=0)])
        result = self.ps.submit_proposal_package("player1", req)
        self.assertTrue(result["success"], result.get("errors"))

    def test_no_prespend(self):
        """§20 #19 / B-AC11：Peace 可能召回兵不预支——不能算入当前可用池。"""
        pool = _pool_size(self.state)
        # 把 20 个军团指派到 pending-peace War（Peace 可能召回）
        recruit_legions_for_war(self.state, self.ctx["war_peace"], self.ctx["cmd_b"].id, count=20)
        remaining = _pool_size(self.state)
        self.assertEqual(remaining, pool - 20)
        # 请求 remaining+1 → 失败（不得预支 war_peace 幸存兵）
        req = submit_request(war_drafts=[
            command_draft(FIXED["war_ongoing"], self.ctx["cmd_a"].id, reinforcement_n=remaining + 1)])
        result = self.ps.submit_proposal_package("player1", req)
        self.assertFalse(result["success"])
        self.assertIn("LEGION_POOL_EXCEEDED", error_codes(result))


if __name__ == "__main__":
    unittest.main()
