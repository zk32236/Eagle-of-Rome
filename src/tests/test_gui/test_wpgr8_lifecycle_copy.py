# src/tests/test_gui/test_wpgr8_lifecycle_copy.py
"""WP-G-R8 DA SLICE-R8-01（SA-Design §5.2 Copy Contract / §4.2 S-1/S-3/S-5；FC-UI-01/02/03/08/09）

Direct Action 呈现时间线（**copy only；零 Core**）——R8-AC-01 / 02 / 03 / 09。

本片锁定（源码锚点 + Store 只读绑定；真实 RENDER 归 SO 帧族）：
- `WarProposalCard.authorityLabel()` proposal 期路由文案 = 「元老院表决」/「执政官直接行动」
  （**禁**含「决定」；C-01/C-02）；
- frozen direct 区标题加 `proposalStepDone` 的 **copy 门**（提案期 = 「战争法案配置（只读）」/
  step 退出 = 「执政官决定…」）；**不改** `visible: root.frozenDirectRows().length > 0`（FC-UI-02 / PM P2-2）；
- frozen 行标题 = 人话决策摘要（C-04，`consulDecisionSummary`）；**不**透传 producer `display_label`；
- frozen 行状态 = 人话（C-05/C-06，`consulExecutionStatus`）；「已执行」仅 `execution=="executed"`；
  **不**透传 producer `execution_label` 技术 receipt 文案（FC-UI-03）；
- 结果面板 direct 行 = 「执政官决定：<War>，由 <Commander> 指挥，增援 <N> 个军团」+ 执行状态；
- 数据面**不变**（`display_label` 仍在 DTO 行内 —— UI 只不再渲染）；direct 行无 `proposal_id`、
  不进 Vote/Veto 候选（FC-UI-08 / AC-09）。
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

_SENATE = "src/ui/gui/qml/stages/SenateStage.qml"
_CARD = "src/ui/gui/qml/components/WarProposalCard.qml"

# PM P2-2 / FC-UI-02：frozen 区可见性谓词 —— 逐字冻结，**copy 门不得改它**。
_FROZEN_VISIBLE = "visible: root.frozenDirectRows().length > 0"

# C-04 / C-05 / C-06 冻结文本（§5.2）。
_C04_PREFIX = "执政官决定："
_C05 = "待战斗阶段执行（尚未执行）"
_C06 = "已执行"
_OLD_RECEIPT = "已执行（边界 receipt）"


def _read(rel_path: str) -> str:
    with open(os.path.join(PROJECT_ROOT, rel_path), encoding="utf-8") as f:
        return f.read()


def _block(source: str, anchor: str, size: int = 640) -> str:
    idx = source.find(anchor)
    return "" if idx < 0 else source[idx:idx + size]


class TestR8ProposalRouteCopy(unittest.TestCase):
    """R8-AC-01：proposal 期路由文案（C-01/C-02；禁「决定」）。"""

    @classmethod
    def setUpClass(cls):
        cls.card = _read(_CARD)

    def _authority_block(self) -> str:
        idx = self.card.find("function authorityLabel()")
        self.assertGreaterEqual(idx, 0)
        return self.card[idx:self.card.find("}", idx) + 1]

    def test_direct_route_label_is_zhixingguan_zhijie_xingdong(self):
        block = self._authority_block()
        self.assertIn("执政官直接行动", block)

    def test_direct_route_label_has_no_decision_word(self):
        """C-02：consul_direct 分支文案**禁**含「决定」。"""
        block = self._authority_block()
        self.assertNotIn("执政官决定", block)
        self.assertNotIn("待推进执行", block)

    def test_senate_route_label_kept(self):
        """C-01：senate_vote 分支「元老院表决」保留。"""
        self.assertIn("元老院表决", self._authority_block())


class TestR8FrozenSectionCopyGate(unittest.TestCase):
    """R8-AC-02：frozen 区标题 copy 门（PM P2-2：门只作用标题，不改可见性）。"""

    @classmethod
    def setUpClass(cls):
        cls.qml = _read(_SENATE)

    def test_frozen_visibility_predicate_unchanged(self):
        """FC-UI-02 / PM P2-2：可见性谓词逐字不变（仅权威 direct 行非空决定）。"""
        self.assertIn(_FROZEN_VISIBLE, self.qml)

    def test_frozen_visibility_not_gated_by_step(self):
        """copy 门**只**在标题；visible 行不含 proposalStepDone。"""
        idx = self.qml.find(_FROZEN_VISIBLE)
        self.assertGreaterEqual(idx, 0)
        self.assertNotIn("proposalStepDone", self.qml[idx:idx + len(_FROZEN_VISIBLE)])

    def test_frozen_title_copy_gate_present(self):
        section = _block(self.qml, "id: frozenDirectSection", 900)
        self.assertIn("root.proposalStepDone", section)
        self.assertIn("战争法案配置（只读）", section)
        self.assertIn("执政官决定", section)

    def test_frozen_proposal_branch_has_no_decision_word(self):
        """提案期标题（copy 门 false 分支）= 配置信息，**不含**「执政官决定」。"""
        idx = self.qml.find("战争法案配置（只读）")
        self.assertGreaterEqual(idx, 0)
        # false 分支文本本身不含「决定」
        self.assertNotIn("决定", self.qml[idx:idx + len("战争法案配置（只读）")])


class TestR8FrozenRowHumanCopy(unittest.TestCase):
    """R8-AC-02/03：frozen 行标题/状态人话化（C-04/C-05/C-06）。"""

    @classmethod
    def setUpClass(cls):
        cls.qml = _read(_SENATE)

    def _row_block(self) -> str:
        idx = self.qml.find('objectName: "senateFrozenDirectRow"')
        end = self.qml.find("root.nonWarProposalOptions()", idx)
        self.assertGreaterEqual(idx, 0)
        self.assertGreater(end, idx)
        return self.qml[idx:end]

    def test_row_title_uses_human_decision_summary(self):
        self.assertIn("root.consulDecisionSummary(modelData)", self._row_block())

    def test_row_title_does_not_passthrough_producer_display_label(self):
        """禁透传 producer 技术串 `display_label`（含旧「… · 待推进到战斗阶段执行」）。"""
        self.assertNotIn("display_label", self._row_block())

    def test_row_status_uses_human_execution_status(self):
        self.assertIn("root.consulExecutionStatus(modelData)", self._row_block())

    def test_row_status_does_not_passthrough_receipt_label(self):
        """FC-UI-03 / C-06：禁透传 producer `execution_label` 技术 receipt 文案。"""
        block = self._row_block()
        self.assertNotIn(_OLD_RECEIPT, block)
        self.assertNotIn("execution_label", block)

    def test_decision_summary_helper_matches_c04(self):
        block = _block(self.qml, "function consulDecisionSummary", 700)
        self.assertIn(_C04_PREFIX, block)
        self.assertIn("由 ", block)
        self.assertIn(" 指挥", block)
        self.assertIn("增援 ", block)
        self.assertIn(" 个军团", block)
        self.assertIn("war_label", block)
        self.assertIn("target_commander_label", block)
        self.assertIn("reinforcement_n", block)

    def test_execution_status_helper_matches_c05_c06(self):
        block = _block(self.qml, "function consulExecutionStatus", 520)
        self.assertIn('execution === "executed"', block)
        self.assertIn(_C06, block)
        self.assertIn(_C05, block)


class TestR8ResultDirectLineCopy(unittest.TestCase):
    """R8-AC-02/03：结果面板 direct 行文案（C-04/C-05）。"""

    @classmethod
    def setUpClass(cls):
        cls.qml = _read(_SENATE)

    def test_result_label_is_decision_noun(self):
        block = _block(self.qml, "function _consulDirectLabel", 260)
        self.assertIn('return "执政官决定"', block)
        self.assertNotIn("display_label", block)

    def test_result_text_uses_human_summary(self):
        block = _block(self.qml, "function _consulDirectText", 520)
        self.assertIn("consulDecisionSummary", block)
        self.assertNotIn("display_label", block)
        self.assertNotIn("N=", block)

    def test_no_producer_display_label_left_in_senate_stage(self):
        """整文件不再引用 producer `display_label`（唯一两处渲染已人话化）。"""
        self.assertNotIn("display_label", self.qml)

    def test_result_line_carries_pending_status(self):
        """C-05：结果 direct 行保持「待战斗阶段执行（尚未执行）」语义。"""
        self.assertIn("_consulDirectStatus", self.qml)


class TestR8DirectLifecycleStoreBinding(unittest.TestCase):
    """R8-AC-01/02/03/09 数据面绑定（Store 只读；数据面**不变**）。"""

    def setUp(self):
        self.ctx = build_f6_base()
        self.store = GuiSessionStore(self.ctx["state"])
        self.store.initialize(FIXED["player"])

    def _submit_direct(self, n=2):
        draft = command_draft(FIXED["war_ongoing"], self.ctx["cmd_a"].id, reinforcement_n=n)
        feedback = self.store.doSubmitSenateProposals([draft])
        self.assertTrue(feedback["success"], feedback)
        return draft

    def test_proposal_step_before_submit(self):
        """S-1：提交前 step==proposal（⇒ copy 门走「战争法案配置（只读）」）。"""
        self.assertEqual(self.store.senateCurrentStep, "proposal")

    def test_direct_row_execution_awaiting_boundary(self):
        """S-3/FC-UI-03：边界前 execution == awaiting_boundary（UI 只读不推断）。"""
        self._submit_direct()
        rows = self.store.senateConsulDirectDecisions
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["execution"], "awaiting_boundary")

    def test_direct_row_execution_label_is_receipt_technical(self):
        """数据面**不变**：producer `display_label`/`execution_label` 仍在行内（仅 UI 不再渲染）。"""
        self._submit_direct()
        row = self.store.senateConsulDirectDecisions[0]
        self.assertIn("执政官决定", row["display_label"])
        self.assertTrue(row["execution_label"])

    def test_step_exit_after_submit(self):
        """S-3：提交后 step 退出 proposal（⇒ copy 门切「执政官决定…」）。"""
        self._submit_direct()
        self.assertNotEqual(self.store.senateCurrentStep, "proposal")

    def test_direct_row_has_no_proposal_id(self):
        """FC-UI-08：direct 行无 `proposal_id`。"""
        self._submit_direct()
        self.assertNotIn("proposal_id", self.store.senateConsulDirectDecisions[0])

    def test_direct_not_in_vote_veto_candidates(self):
        """R8-AC-09：direct 行永不进 Vote/Veto 候选集。"""
        self._submit_direct()
        self.assertEqual(list(self.store.senateVetoCandidateIds), [])
        for result in self.store.senateVoteResults:
            self.assertNotEqual(result.get("war_id"), FIXED["war_ongoing"])


if __name__ == "__main__":
    unittest.main()
