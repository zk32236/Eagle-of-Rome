# src/tests/test_api/test_wpgr5_vote_veto_lifecycle.py
"""WP-G-R5 DA-2 (§3.7/§3.8/§2.3) — 冻结 proposal 的普通 Vote/Veto 生命周期。

覆盖 Owner §20 #20 / #21 / #22 / #23 / #24；B-AC18（浅层）。
"""
import copy
import unittest

from src.api import senate_api
from src.core.systems.political_system import PoliticalSystem

from src.tests.fixtures.wpgr5_fixtures import (
    build_r5_base, FIXED, add_figure, submit_request, command_draft,
)


class TestVoteVetoLifecycle(unittest.TestCase):
    def setUp(self):
        self.ctx = build_r5_base()
        self.state = self.ctx["state"]
        self.ps = PoliticalSystem(self.state)

    def _submit_one(self, target=None):
        req = submit_request(war_drafts=[
            command_draft(FIXED["war_ongoing"], target or self.ctx["cmd_a"].id, reinforcement_n=0)])
        result = self.ps.submit_proposal_package("player1", req)
        self.assertTrue(result["success"], result.get("errors"))
        return result["data"]["created"][0]["proposal_id"]

    def test_one_card_one_proposal(self):
        """§20 #20：一 checked card = 恰好一个提案。"""
        pid = self._submit_one()
        props = self.state.get_senate_proposals()
        self.assertEqual(len(props), 1)
        self.assertEqual(props[0]["id"], pid)
        self.assertEqual(props[0]["type"], "war_proposal")

    def test_immutable_after_submit(self):
        """§20 #21：Submit 后 Commander/N 不可改（改意图 → REUSED，快照不变）。"""
        pid = self._submit_one()
        snap_before = copy.deepcopy(self.state.get_senate_proposals()[0]["payload"])
        r2 = self.ps.submit_proposal_package(
            "player1",
            submit_request(war_drafts=[
                command_draft(FIXED["war_ongoing"], self.ctx["cmd_b"].id, reinforcement_n=3)]))
        self.assertFalse(r2["success"])
        snap_after = self.state.get_senate_proposals()[0]["payload"]
        self.assertEqual(snap_before, snap_after)

    def test_normal_vote(self):
        """§20 #22：War Proposal 参与普通 Vote。"""
        pid = self._submit_one()
        v = senate_api.vote(self.state, "player1", [pid], [True])
        self.assertTrue(v["success"], v.get("message"))
        self.assertTrue(self.state.has_senate_vote("player1", pid))

    def test_passed_can_be_vetoed(self):
        """§20 #23：passed War Proposal 可被保民官否决。"""
        add_figure(self.state, self.ctx["faction"], 5, "Tribune T", office="tribune")
        pid = self._submit_one()
        v = senate_api.vote(self.state, "player1", [pid], [True])
        self.assertTrue(v["success"], v.get("message"))
        projection = self.ps.build_vote_results_and_candidates()
        self.assertIn(pid, projection["veto_candidate_ids"])
        ve = senate_api.veto(self.state, "player1", [pid])
        self.assertTrue(ve["success"], ve.get("message"))
        self.assertIn(pid, self.state.get_senate_vetoes_copy())

    def test_vote_veto_no_content_mutation(self):
        """§20 #24：Vote/Veto 不改 proposal 内容（快照深值前后相等）。"""
        add_figure(self.state, self.ctx["faction"], 6, "Tribune U", office="tribune")
        pid = self._submit_one()
        snap = copy.deepcopy(self.state.get_senate_proposals()[0])
        senate_api.vote(self.state, "player1", [pid], [True])
        senate_api.veto(self.state, "player1", [pid])
        after = self.state.get_senate_proposals()[0]
        self.assertEqual(snap["payload"], after["payload"])
        self.assertEqual(snap["war_id"], after["war_id"])
        self.assertEqual(snap["mode"], after["mode"])


if __name__ == "__main__":
    unittest.main()
