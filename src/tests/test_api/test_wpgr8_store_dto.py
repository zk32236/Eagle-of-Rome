# src/tests/test_api/test_wpgr8_store_dto.py
"""WP-G-R8 DA SLICE-R8-02（SA-Design §5.3；FC-UI-04/05；D-R8-04/05）— Store 诊断数据面 + 人话展示副本。

本片（DATA；RENDER 归 SO）锁定：
- **数据面不变**：真实提交失败 → Store `senateSubmitErrors` 仍保留五字段原始结构化 payload
  （`code/scope/field/details/message`），`senateSubmitErrorsByWar` 精确卡定位；
- **旁路反馈人话化**：Senate 调用点经 Store 发出的 `feedbackRaised`（shell toast/status 消费者）
  显示**人话摘要**，**不含** machine code（SA §5.3）；原始 `feedback` 返回 / 错误对象不被改写；
- 草稿深值保留 + 成功重提清面（R8-AC-08 数据面）。
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

_DRAFT_KEYS = ("checked", "mode", "target_commander_id", "reinforcement_n")


class TestR8DiagnosticDataSurfaceUnchanged(unittest.TestCase):
    def setUp(self):
        self.ctx = build_f6_base()
        self.store = GuiSessionStore(self.ctx["state"])
        self.store.initialize(FIXED["player"])

    def test_failure_keeps_five_field_payload(self):
        wid = FIXED["war_ongoing"]
        fb = self.store.doSubmitSenateProposals(
            [command_draft(wid, self.ctx["cmd_a"].id, reinforcement_n=-1)])
        self.assertFalse(fb["success"])
        items = self.store.senateSubmitErrors
        self.assertTrue(items)
        for it in items:
            for key in ("code", "scope", "field", "details", "message"):
                self.assertIn(key, it)
        # 相关卡定位（结构面不变）
        self.assertIn(wid, self.store.senateSubmitErrorsByWar)

    def test_failed_toast_is_human_not_machine_code(self):
        msgs = []
        self.store.feedbackRaised.connect(lambda t, m: msgs.append((t, m)))
        self.store.doSubmitSenateProposals(
            [command_draft(FIXED["war_ongoing"], self.ctx["cmd_a"].id, reinforcement_n=-1)])
        self.assertTrue(msgs)
        ftype, message = msgs[-1]
        self.assertEqual(ftype, "error")
        self.assertNotIn("REINFORCEMENT_INVALID", message)
        self.assertNotIn("reinforcement_n", message)
        self.assertIn("增援军团数量不符合要求", message)

    def test_duplicate_commander_toast_is_human(self):
        w_on, w_th = FIXED["war_ongoing"], FIXED["war_threat"]
        msgs = []
        self.store.feedbackRaised.connect(lambda t, m: msgs.append((t, m)))
        self.store.doSubmitSenateProposals([
            command_draft(w_on, self.ctx["cmd_a"].id, reinforcement_n=1),
            command_draft(w_th, self.ctx["cmd_a"].id, reinforcement_n=2),
        ])
        self.assertTrue(msgs)
        self.assertNotIn("COMMANDER_CLAIM_DUPLICATE", msgs[-1][1])
        self.assertIn("同一指挥官不能同时指挥这些战争", msgs[-1][1])

    def test_returned_feedback_message_unchanged(self):
        """人话化只改**展示副本**；原反馈对象（含 code）不被改写。"""
        wid = FIXED["war_ongoing"]
        fb = self.store.doSubmitSenateProposals(
            [command_draft(wid, self.ctx["cmd_a"].id, reinforcement_n=-1)])
        self.assertIn("REINFORCEMENT_INVALID", fb["feedback_message"])

    def test_pool_exceeded_toast_carries_authority_numbers(self):
        wid = FIXED["war_ongoing"]
        available = len(self.ctx["pool_ids"])
        msgs = []
        self.store.feedbackRaised.connect(lambda t, m: msgs.append((t, m)))
        self.store.doSubmitSenateProposals(
            [command_draft(wid, self.ctx["cmd_a"].id, reinforcement_n=available + 1)])
        self.assertTrue(msgs)
        message = msgs[-1][1]
        self.assertNotIn("LEGION_POOL_EXCEEDED", message)
        self.assertIn("增援请求超过可用军团", message)
        self.assertIn(str(available), message)

    def test_draft_preserved_and_resubmit_succeeds_same_phase(self):
        wid = FIXED["war_ongoing"]
        draft = command_draft(wid, self.ctx["cmd_a"].id, reinforcement_n=-1)
        self.store.doSubmitSenateProposals([draft])
        kept = self.store.senateDraftFor(wid)
        for key in _DRAFT_KEYS:
            self.assertEqual(kept.get(key), draft[key], f"{wid}.{key} 未保留")
        self.assertEqual(self.store.senateCurrentStep, "proposal")
        ok = self.store.doSubmitSenateProposals(
            [command_draft(wid, self.ctx["cmd_a"].id, reinforcement_n=1)])
        self.assertTrue(ok["success"], ok)
        self.assertFalse(self.store.hasSenateSubmitErrors)

    def test_error_surface_properties_still_present(self):
        for prop in ("senateSubmitErrors", "senateSubmitErrorsByWar",
                     "senateSubmitErrorsByScope", "hasSenateSubmitErrors",
                     "senateSubmitErrorBanner", "senateWarCards"):
            self.assertTrue(hasattr(self.store, prop), prop)


if __name__ == "__main__":
    unittest.main()
