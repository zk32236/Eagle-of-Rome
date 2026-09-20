# src/tests/test_api/test_wpgr7_store_dto.py
"""WP-G-R7 DA B4（SA-Design §A.4 / R7-AC-02/03/04/06；DA-Plan §2 B1/B4）— Store DTO 透传 + R7-A 连续性。

本片（B4）证据分类 = DATA（RENDER 归 SO）。锁定：
- `GuiSessionStore.senateConsulDirectDecisions` = 顶层 `consul_direct_decisions` 只读透传
  （无 setter / 零生命周期推导 / 行内无 `proposal_id`）；
- direct-only Submit 成功 → 该 Property 呈现 FROZEN 行（身份 item_ref / War / Commander / N），
  且 step 无关（results 步仍可读）；
- direct 行不进 Vote / Veto（无递交提案 / 无否决候选 / 零 Senate 提案发布）；
- 刷新（重复 GET / `_refresh_senate_view`）身份稳定（item_ref 逐字不变）。

**不弱化任何既有断言**：R6 已覆盖 `senate_api`/PA 面（见 `test_wpgr6_senate_flow.py`）；
本片只补 B1 新增的 **Store Property** 消费面。
"""
import os
import sys
import unittest

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(__file__))))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

from src.ui.gui.session_store import GuiSessionStore
from src.tests.fixtures.wpgr5_fixtures import FIXED, command_draft
from src.tests.fixtures.wpgr6_fixtures import build_f6_base


def _war_row(rows, war_id):
    for row in rows:
        if row.get("war_id") == war_id:
            return row
    return None


class TestR7StoreConsulDirectDTO(unittest.TestCase):
    """B1：Store 顶层 direct DTO 只读投影（SA §A.4）。"""

    def setUp(self):
        self.ctx = build_f6_base()
        self.state = self.ctx["state"]
        self.store = GuiSessionStore(self.state)
        self.store.initialize(FIXED["player"])

    def test_property_is_list_and_empty_before_submit(self):
        self.assertIsInstance(self.store.senateConsulDirectDecisions, list)
        self.assertEqual(self.store.senateConsulDirectDecisions, [])

    def test_property_is_readonly_passthrough(self):
        """只读透传：把哨兵行放进顶层 DTO → 属性原样返回（零推导 / 零过滤）。"""
        sentinel = {"war_id": "sentinel_war", "decision_state": "FROZEN"}
        self.store._senate_view["consul_direct_decisions"] = [sentinel]
        surfaced = self.store.senateConsulDirectDecisions
        self.assertEqual(len(surfaced), 1)
        self.assertIs(surfaced[0], sentinel)

    def test_direct_submit_populates_frozen_row_with_full_identity(self):
        feedback = self.store.doSubmitSenateProposals(
            [command_draft(FIXED["war_ongoing"], self.ctx["cmd_a"].id, reinforcement_n=1)])
        self.assertTrue(feedback["success"], feedback)
        rows = self.store.senateConsulDirectDecisions
        self.assertEqual(len(rows), 1)
        row = rows[0]
        # R7-AC-03：全 War / Commander / N 身份
        self.assertEqual(row["war_id"], FIXED["war_ongoing"])
        self.assertEqual(row["target_commander_id"], self.ctx["cmd_a"].id)
        self.assertEqual(row["reinforcement_n"], 1)
        # R7-AC-04：明确 Consul Direct / awaiting boundary
        self.assertEqual(row["identity"], "consul_direct_decision")
        self.assertEqual(row["authority"], "consul_direct")
        self.assertEqual(row["decision_state"], "FROZEN")
        self.assertEqual(row["execution"], "awaiting_boundary")
        # R7-AC-06：稳定身份（item_ref）；行内无 proposal_id（不进 Vote/Veto）
        self.assertTrue(row["item_ref"])
        self.assertEqual(row["item_ref"]["kind"], "consul_direct")
        self.assertNotIn("proposal_id", row)

    def test_frozen_row_readable_after_step_moves_to_results(self):
        """R7-AC-02：direct-only Submit → step 转 results；Property 仍非空（step 无关）。"""
        self.store.doSubmitSenateProposals(
            [command_draft(FIXED["war_ongoing"], self.ctx["cmd_a"].id, 1)])
        self.assertEqual(self.store.senateCurrentStep, "results")
        self.assertEqual(len(self.store.senateConsulDirectDecisions), 1)

    def test_direct_row_absent_from_vote_and_veto(self):
        """R7-AC-01：direct 行不进 Vote / Veto；零真 Senate 提案发布。"""
        self.store.doSubmitSenateProposals(
            [command_draft(FIXED["war_ongoing"], self.ctx["cmd_a"].id, 1)])
        self.assertEqual(self.store.senateSubmittedProposals, [])
        self.assertEqual(self.store.senateVetoCandidateIds, [])
        self.assertEqual(self.state.get_senate_proposals(), [])

    def test_identity_stable_across_store_refresh(self):
        """R7-AC-06 / §6.3（N-11）：重复拉取 → item_ref 与行内容逐字稳定。"""
        self.store.doSubmitSenateProposals(
            [command_draft(FIXED["war_ongoing"], self.ctx["cmd_a"].id, 1)])
        before = self.store.senateConsulDirectDecisions
        self.assertEqual(len(before), 1)
        self.store._refresh_senate_view()
        after = self.store.senateConsulDirectDecisions
        self.assertEqual([r["item_ref"] for r in after],
                         [r["item_ref"] for r in before])
        self.assertEqual(after, before)

    def test_pre_boundary_zero_military_mutation(self):
        """R7-AC-05：Submit→边界之间原将/军事零变更（Property 只读，不触发执行）。"""
        self.store.doSubmitSenateProposals(
            [command_draft(FIXED["war_ongoing"], self.ctx["cmd_a"].id, 1)])
        self.assertEqual(self.ctx["war_ongoing"].commander_id, self.ctx["cmd_a"].id)
        self.assertIsNone(
            self.state.get_war_execution_receipt_for_session(self.state.get_senate_session()))
        self.assertTrue(all(r["execution"] == "awaiting_boundary"
                            for r in self.store.senateConsulDirectDecisions))

    def test_existing_error_surface_properties_still_present(self):
        """无回退：B1 新增属性不替换 / 不遮蔽 R6 既有错误面属性。"""
        for prop in ("senateSubmitErrors", "senateSubmitErrorsByWar",
                     "senateSubmitErrorsByScope", "hasSenateSubmitErrors",
                     "senateSubmitErrorBanner", "senateWarCards"):
            self.assertTrue(hasattr(self.store, prop), prop)
        self.assertEqual(self.store.senateSubmitErrors, [])
        self.assertFalse(self.store.hasSenateSubmitErrors)


if __name__ == "__main__":
    unittest.main()
