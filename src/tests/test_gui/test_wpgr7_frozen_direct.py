# src/tests/test_gui/test_wpgr7_frozen_direct.py
"""WP-G-R7 DA B4（SA-Design §A.5 / R7-AC-02/03/04/06；DA-Plan §2 B1/B4）— R7-A frozen direct 渲染面。

本片锁定 B1 落地面（**源码 + Store 绑定**；真实渲染 RENDER 归 SO 帧族 `senateFrozenDirectRow`）：
- 新增 step 无关只读区 `frozenDirectSection`（bounded ≤168）；
- 数据源 = Store 顶层 `senateConsulDirectDecisions`（**非** PA），身份文本 War·Commander·N；
- 只读 delegate（`senateFrozenDirectRow`）**无任何输入控件** ⇒ 永不可再 Submit（INV-A5）；
- **不改** War Card Repeater 的 step 门控（R6 可编辑路径零回归）；
- frozen 区插在 War Card Repeater 之后、非 War ScrollView 之前。
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

_QML = "src/ui/gui/qml/stages/SenateStage.qml"
_STEP_GATE = ('model: sessionStore.senateCurrentStep === "proposal" '
              '? (sessionStore.senateWarCards || []) : []')


def _read_qml(rel_path: str) -> str:
    with open(os.path.join(PROJECT_ROOT, rel_path), encoding="utf-8") as f:
        return f.read()


class TestR7FrozenDirectQmlWiring(unittest.TestCase):
    """B1 QML 接线（源码锚点）。"""

    @classmethod
    def setUpClass(cls):
        cls.qml = _read_qml(_QML)

    def test_frozen_row_anchor_and_section_present(self):
        self.assertIn('objectName: "senateFrozenDirectRow"', self.qml)
        self.assertIn("id: frozenDirectSection", self.qml)

    def test_frozen_section_is_bounded(self):
        idx = self.qml.find("id: frozenDirectSection")
        self.assertGreaterEqual(idx, 0)
        block = self.qml[idx:idx + 420]
        self.assertIn("Layout.maximumHeight: 168", block)

    def test_frozen_rows_read_top_level_dto_not_pa(self):
        idx = self.qml.find("function frozenDirectRows()")
        self.assertGreaterEqual(idx, 0)
        block = self.qml[idx:idx + 200]
        self.assertIn("sessionStore.senateConsulDirectDecisions", block)
        self.assertNotIn("senatePublicAnnouncement", block)

    def test_war_card_step_gate_unchanged(self):
        """R7-A 不注入可编辑 Repeater：step 门保持逐字不变。"""
        self.assertIn(_STEP_GATE, self.qml)

    def test_frozen_section_between_card_repeater_and_nonwar_list(self):
        gate = self.qml.find("sessionStore.senateWarCards || []) : []")
        frozen = self.qml.find("id: frozenDirectSection")
        self.assertGreaterEqual(frozen, 0)
        self.assertGreater(gate, -1)
        self.assertGreater(frozen, gate)
        # 从 frozen 区之后找非 War 列表的**使用**（函数定义在文件更早处）
        nonwar = self.qml.find("root.nonWarProposalOptions()", frozen)
        self.assertGreater(nonwar, frozen)

    def test_frozen_delegate_has_no_input_controls(self):
        """INV-A5：只读行无输入控件 ⇒ 永不可再 Submit。"""
        idx = self.qml.find('objectName: "senateFrozenDirectRow"')
        end = self.qml.find("root.nonWarProposalOptions()", idx)
        self.assertGreaterEqual(idx, 0)
        self.assertGreater(end, idx)
        block = self.qml[idx:end]
        for ctrl in ("SpinBox", "ComboBox", "CheckBox", "TextField",
                     "RadioButton", "TextInput", "Button {"):
            self.assertNotIn(ctrl, block, f"frozen delegate 不应含输入控件: {ctrl}")

    def test_identity_text_covers_war_commander_n_without_elide(self):
        idx = self.qml.find("function frozenDirectIdentityText")
        self.assertGreaterEqual(idx, 0)
        block = self.qml[idx:idx + 520]
        self.assertIn("war_label", block)
        self.assertIn("target_commander_label", block)
        self.assertIn("reinforcement_n", block)

    def test_frozen_identity_text_elide_none(self):
        idx = self.qml.find('objectName: "senateFrozenDirectRow"')
        end = self.qml.find("root.nonWarProposalOptions()", idx)
        block = self.qml[idx:end]
        self.assertIn("elide: Text.ElideNone", block)


class TestR7FrozenDirectStoreContinuity(unittest.TestCase):
    """R7-A 身份连续性（Store 绑定面 / D-11 局部 trace）。"""

    def setUp(self):
        self.ctx = build_f6_base()
        self.store = GuiSessionStore(self.ctx["state"])
        self.store.initialize(FIXED["player"])

    def _submit_direct(self):
        draft = command_draft(FIXED["war_ongoing"], self.ctx["cmd_a"].id, reinforcement_n=2)
        feedback = self.store.doSubmitSenateProposals([draft])
        self.assertTrue(feedback["success"], feedback)
        return draft

    def test_draft_to_row_identity_trace(self):
        draft = self._submit_direct()
        rows = self.store.senateConsulDirectDecisions
        self.assertEqual(len(rows), 1)
        row = rows[0]
        # draft.war_id → 冻结行 war_id（同一逻辑 War item）
        self.assertEqual(row["war_id"], draft["war_id"])
        # draft Commander / N → 冻结行身份（不重建自 live defaults）
        self.assertEqual(row["target_commander_id"], draft["target_commander_id"])
        self.assertEqual(row["reinforcement_n"], draft["reinforcement_n"])
        # 稳定身份 ref
        self.assertEqual(row["item_ref"]["direct_decision_id"], row["direct_decision_id"])

    def test_frozen_row_survives_component_redraw_read(self):
        """§6.3 / N-11：多次读取 / refresh 不清空（model 非空即渲染，无 step 门）。"""
        self._submit_direct()
        for _ in range(3):
            self.store._refresh_senate_view()
            self.assertEqual(len(self.store.senateConsulDirectDecisions), 1)


if __name__ == "__main__":
    unittest.main()
