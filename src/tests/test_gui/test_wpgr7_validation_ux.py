# src/tests/test_gui/test_wpgr7_validation_ux.py
"""WP-G-R7 DA B4（SA-Design §B.2–B.7 / R7-AC-08…15；DA-Plan §2 B2/B3/B4）— R7-B 校验 UX。

本片锁定 B2/B3 落地面（**Store/数据 + QML 源码**；真实渲染 RENDER 归 SO 帧族）：
- invalid-N / duplicate-Commander / pool 超限 → 失败面精确（code·scope·field）+ 相关卡定位
  （`senateSubmitErrorsByWar`，权威 Core details），零发布，草稿深值保留，就地重提成功；
- 负向 N-01（N=0 合法不误高亮）/ N-02 / N-03 / N-04 / N-05 / N-12；
- bounded 呈现（bounded Dialog + 固定 28px 状态条 + 卡级块 ≤120）与 canonical error 色
  （`theme.statusError`，无第二套红）；helper 体齐备（G3 P2-2）；逐卡 ack（G3 P2-1/P2-3）。
"""
import os
import sys
import unittest

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(__file__))))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

from src.ui.gui.session_store import GuiSessionStore
from src.tests.fixtures.wpgr5_fixtures import FIXED, command_draft
from src.tests.fixtures.wpgr6_fixtures import build_f6_base, pool_legion_ids

_SENATE_QML = "src/ui/gui/qml/stages/SenateStage.qml"
_CARD_QML = "src/ui/gui/qml/components/WarProposalCard.qml"

_DRAFT_KEYS = ("checked", "mode", "target_commander_id", "reinforcement_n")


def _read_qml(rel_path: str) -> str:
    with open(os.path.join(PROJECT_ROOT, rel_path), encoding="utf-8") as f:
        return f.read()


class _StoreCase(unittest.TestCase):
    def setUp(self):
        self.ctx = build_f6_base()
        self.state = self.ctx["state"]
        self.store = GuiSessionStore(self.state)
        self.store.initialize(FIXED["player"])

    def _session(self):
        return (self.store._senate_draft_session_id
                or self.state.get_senate_session() or "turn-1")

    def _error(self, code):
        return next((i for i in self.store.senateSubmitErrors if i["code"] == code), None)

    def _assert_zero_publication(self):
        """R7-AC-13：零 Senate 提案 + 零 direct 决策 + 无递交包。"""
        self.assertEqual(self.state.get_senate_proposals(), [])
        self.assertEqual(self.store.senateConsulDirectDecisions, [])
        self.assertEqual(self.state.get_consul_war_decisions(self._session()), {})
        self.assertIsNone(self.state.get_senate_package_id_for_session(self._session()))

    def _assert_draft_preserved(self, war_id, draft):
        """R7-AC-12：失败不取消 checkbox / 不改 mode / 不换将 / 不 clamp N（逐字段深值相等）。"""
        kept = self.store.senateDraftFor(war_id)
        for key in _DRAFT_KEYS:
            self.assertEqual(kept.get(key), draft[key], f"{war_id}.{key} 未保留")


class TestR7InvalidN(_StoreCase):
    """R7-AC-08/09/12/13/14 + N-01/N-02/N-03。"""

    def test_negative_n_fails_located_field_preserved_then_corrected(self):
        wid = FIXED["war_ongoing"]
        draft = command_draft(wid, self.ctx["cmd_a"].id, reinforcement_n=-1)
        feedback = self.store.doSubmitSenateProposals([draft])
        self.assertFalse(feedback["success"])
        item = self._error("REINFORCEMENT_INVALID")
        self.assertIsNotNone(item)
        # 精确字段定位（scope=war_id，field=reinforcement_n）
        self.assertEqual(item["scope"], wid)
        self.assertEqual(item["field"], "reinforcement_n")
        # 相关卡定位（仅该卡）
        self.assertIn(wid, self.store.senateSubmitErrorsByWar)
        # 零发布
        self._assert_zero_publication()
        # 草稿深值保留
        self._assert_draft_preserved(wid, draft)
        # 就地改值重提成功
        feedback2 = self.store.doSubmitSenateProposals(
            [command_draft(wid, self.ctx["cmd_a"].id, reinforcement_n=1)])
        self.assertTrue(feedback2["success"], feedback2)
        self.assertFalse(self.store.hasSenateSubmitErrors)

    def test_n_zero_is_legal_and_not_flagged(self):
        """N-01：N=0 合法（零池例外）→ 成功且不误报 REINFORCEMENT_INVALID。"""
        wid = FIXED["war_ongoing"]
        feedback = self.store.doSubmitSenateProposals(
            [command_draft(wid, self.ctx["cmd_a"].id, reinforcement_n=0)])
        self.assertTrue(feedback["success"], feedback)
        self.assertFalse(self.store.hasSenateSubmitErrors)
        self.assertEqual(self.store.senateSubmitErrors, [])

    def test_n_over_pool_pool_error_and_located(self):
        """R7-AC-09 / N-03：N > 可用池 → LEGION_POOL_EXCEEDED，相关卡定位，零发布，草稿保留。"""
        wid = FIXED["war_ongoing"]
        available = len(pool_legion_ids(self.state))
        self.assertGreater(available, 0)
        draft = command_draft(wid, self.ctx["cmd_a"].id, reinforcement_n=available + 1)
        feedback = self.store.doSubmitSenateProposals([draft])
        self.assertFalse(feedback["success"])
        item = self._error("LEGION_POOL_EXCEEDED")
        self.assertIsNotNone(item)
        self.assertEqual(item["scope"], "package")
        self.assertIn(wid, self.store.senateSubmitErrorsByWar)
        self._assert_zero_publication()
        self._assert_draft_preserved(wid, draft)

    def test_multi_war_over_pool_requests_lists_all_cards(self):
        """N-05：多战总和超池 → requests 多行；各涉事卡定位。"""
        w_on, w_th = FIXED["war_ongoing"], FIXED["war_threat"]
        available = len(pool_legion_ids(self.state))
        d_big = command_draft(w_on, self.ctx["cmd_a"].id, reinforcement_n=available + 1)
        d_th = command_draft(w_th, self.ctx["consul_id"], reinforcement_n=1)
        feedback = self.store.doSubmitSenateProposals([d_big, d_th])
        self.assertFalse(feedback["success"])
        item = self._error("LEGION_POOL_EXCEEDED")
        self.assertIsNotNone(item)
        requests = item["details"].get("requests") or []
        self.assertGreaterEqual(len(requests), 1)
        for wid in (w_on, w_th):
            self.assertIn(wid, self.store.senateSubmitErrorsByWar)
        self._assert_zero_publication()


class TestR7DuplicateCommander(_StoreCase):
    """R7-AC-10/11/12/13/14 + N-04。"""

    def test_duplicate_commander_two_cards_located_then_corrected(self):
        w_on, w_th = FIXED["war_ongoing"], FIXED["war_threat"]
        d_on = command_draft(w_on, self.ctx["cmd_a"].id, reinforcement_n=1)
        d_th = command_draft(w_th, self.ctx["cmd_a"].id, reinforcement_n=2)
        feedback = self.store.doSubmitSenateProposals([d_on, d_th])
        self.assertFalse(feedback["success"])
        item = self._error("COMMANDER_CLAIM_DUPLICATE")
        self.assertIsNotNone(item)
        self.assertEqual(item["scope"], "package")
        claimed = sorted(str(c["war_id"]) for c in item["details"].get("claims", []))
        self.assertEqual(claimed, sorted([w_on, w_th]))
        # 全部涉事卡定位
        for wid in (w_on, w_th):
            self.assertIn(wid, self.store.senateSubmitErrorsByWar)
            codes = [i["code"] for i in self.store.senateSubmitErrorsByWar[wid]]
            self.assertIn("COMMANDER_CLAIM_DUPLICATE", codes)
        self._assert_zero_publication()
        self._assert_draft_preserved(w_on, d_on)
        self._assert_draft_preserved(w_th, d_th)
        # 改一个 Commander → 重提成功
        d_th_ok = command_draft(w_th, self.ctx["consul_id"], reinforcement_n=2)
        feedback2 = self.store.doSubmitSenateProposals([d_on, d_th_ok])
        self.assertTrue(feedback2["success"], feedback2)
        self.assertFalse(self.store.hasSenateSubmitErrors)

    def test_duplicate_commander_three_cards_located(self):
        """N-04：×3 卡同 Commander → 三卡全入 by_war，claims 三条，零发布。"""
        drafts = [
            command_draft(FIXED["war_ongoing"], self.ctx["cmd_a"].id, reinforcement_n=1),
            command_draft(FIXED["war_peace"], self.ctx["cmd_a"].id, reinforcement_n=1),
            command_draft(FIXED["war_threat"], self.ctx["cmd_a"].id, reinforcement_n=1),
        ]
        feedback = self.store.doSubmitSenateProposals(drafts)
        self.assertFalse(feedback["success"])
        item = self._error("COMMANDER_CLAIM_DUPLICATE")
        self.assertIsNotNone(item)
        claimed = sorted(str(c["war_id"]) for c in item["details"].get("claims", []))
        self.assertEqual(len(claimed), 3)
        for wid in (FIXED["war_ongoing"], FIXED["war_peace"], FIXED["war_threat"]):
            self.assertIn(wid, self.store.senateSubmitErrorsByWar)
        self._assert_zero_publication()


class TestR7RecoveryAndStale(_StoreCase):
    """R7-AC-14 + N-12：无重启恢复 + 重复失败不叠错 + 成功清面。"""

    def test_repeated_invalid_submit_errors_stable_and_drafts_kept(self):
        wid = FIXED["war_ongoing"]
        draft = command_draft(wid, self.ctx["cmd_a"].id, reinforcement_n=-1)
        first = self.store.doSubmitSenateProposals([draft])
        self.assertFalse(first["success"])
        n_first = len(self.store.senateSubmitErrors)
        # 再次提交同一无效包：错误面刷新（不叠增），草稿仍保留
        second = self.store.doSubmitSenateProposals([draft])
        self.assertFalse(second["success"])
        self.assertEqual(len(self.store.senateSubmitErrors), n_first)
        self._assert_draft_preserved(wid, draft)
        # 成功 revalidate 清空错误面
        ok = self.store.doSubmitSenateProposals(
            [command_draft(wid, self.ctx["cmd_a"].id, reinforcement_n=1)])
        self.assertTrue(ok["success"], ok)
        self.assertFalse(self.store.hasSenateSubmitErrors)
        self.assertEqual(self.store.senateSubmitErrorsByWar, {})

    def test_failure_does_not_trigger_destructive_refresh(self):
        """R7-AC-12 保证：失败路径不重建 defaults（仍在提案步、仍可编辑）。"""
        wid = FIXED["war_ongoing"]
        self.store.doSubmitSenateProposals(
            [command_draft(wid, self.ctx["cmd_a"].id, reinforcement_n=-1)])
        self.assertEqual(self.store.senateCurrentStep, "proposal")
        self.assertTrue(self.store.canCreateSenateProposal)


class TestR7ValidationQmlWiring(unittest.TestCase):
    """B2/B3 QML 接线（源码锚点；RENDER 归 SO）。"""

    @classmethod
    def setUpClass(cls):
        cls.senate = _read_qml(_SENATE_QML)
        cls.card = _read_qml(_CARD_QML)

    # ---- bounded 呈现 ----
    def test_bounded_dialog_present_and_modal(self):
        for marker in ('objectName: "senateValidationDialog"', "modal: true",
                       "closePolicy: Popup.CloseOnEscape"):
            self.assertIn(marker, self.senate, marker)

    def test_dialog_dimensions_bounded(self):
        self.assertIn("Math.min(root.width - 80, 640)", self.senate)
        self.assertIn("Math.min(root.height - 120, 440)", self.senate)

    def test_package_strip_fixed_28(self):
        idx = self.senate.find('objectName: "senateValidationStrip"')
        self.assertGreaterEqual(idx, 0)
        end = self.senate.find('objectName: "senateFinalizationWarningStrip"', idx)
        self.assertGreater(end, idx)
        block = self.senate[idx:end]
        self.assertIn("Layout.maximumHeight: 28", block)
        self.assertIn("elide: Text.ElideRight", block)

    def test_finalization_warning_strip_bounded(self):
        idx = self.senate.find('objectName: "senateFinalizationWarningStrip"')
        self.assertGreaterEqual(idx, 0)
        block = self.senate[idx:idx + 500]
        self.assertIn("Layout.maximumHeight: 28", block)

    def test_card_error_block_bounded_120(self):
        idx = self.card.find('objectName: "warCardErrorBlock"')
        self.assertGreaterEqual(idx, 0)
        block = self.card[idx:idx + 400]
        self.assertIn("Layout.maximumHeight: 120", block)
        self.assertIn("clip: true", block)

    # ---- 字段/控件高亮锚点 + code→widget 展示路由 ----
    def test_field_highlight_anchors_present(self):
        self.assertIn('objectName: "warCardNField"', self.card)
        self.assertIn('objectName: "warCardCommanderField"', self.card)

    def test_field_error_routing(self):
        self.assertIn('cardRoot.fieldError("reinforcement_n")', self.card)
        self.assertIn('cardRoot.codeError("LEGION_POOL_EXCEEDED")', self.card)
        self.assertIn('cardRoot.codeError("COMMANDER_CLAIM_DUPLICATE")', self.card)

    def test_card_border_uses_error_state(self):
        self.assertIn("cardRoot.hasError ? theme.statusError", self.card)

    # ---- canonical error 色（无第二套红） ----
    def test_canonical_error_color_and_no_second_palette(self):
        for src in (self.senate, self.card):
            self.assertIn("theme.statusError", src)
            self.assertNotIn("#B00020", src)
            self.assertNotIn("#FCE8E6", src)

    # ---- helper 体齐备（G3 P2-2） ----
    def test_error_helpers_implemented(self):
        for fn in ("function senateErrorSummaryText()",
                   "function senateErrorDetailLine(",
                   "function senateErrorDetailExtra(",
                   "function senateErrorMachineJson()"):
            self.assertIn(fn, self.senate, fn)

    # ---- 逐卡 ack 装配（G3 P2-1/P2-3） ----
    def test_card_errors_injected_via_ack_aware_helper(self):
        self.assertIn("cardErrors: root.cardErrorsFor(modelData.war_id)", self.senate)
        self.assertIn("property var errorAckWars", self.senate)
        self.assertIn("function cardErrorsFor(", self.senate)
        self.assertIn("function onWarDraftEdited(", self.senate)

    def test_dialog_open_close_wired_to_error_surface(self):
        self.assertIn("function onSenateSubmitErrorsChanged()", self.senate)
        self.assertIn("senateValidationDialog.open()", self.senate)
        self.assertIn("senateValidationDialog.close()", self.senate)


if __name__ == "__main__":
    unittest.main()
