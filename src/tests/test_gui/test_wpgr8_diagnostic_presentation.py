# src/tests/test_gui/test_wpgr8_diagnostic_presentation.py
"""WP-G-R8 DA SLICE-R8-02（SA-Design §5.3 / §4.3 / §4.4 I-1..I-4；FC-UI-04/05；D-R8-04/05）

诊断呈现去 machine + 人话化 + 卡级人话（R8-AC-04 / 05 / 08）。

本片锁定（源码锚点 + Store 只读绑定；真实 RENDER 归 SO 帧族 F-N/F-D/F-M）：
- `SenateStage` Dialog：移除「machine 详情」+ raw JSON 渲染；`senateErrorDetailLine` → 人话
  （code→人话查表，禁 machine code / field token）；`senateErrorDetailExtra` → 人类可读涉事对象
  （用 label，不用 opaque `war=<id>` / `commander=<id>` / `N=` 形态）；
- frozen direct 行：移除 `item_ref: JSON.stringify(...)`（FC-UI-04）；
- `WarProposalCard`：`cardErrorText` 人话；移除 `errorDetailsText()` JSON + 「展开详情」toggle +
  `errorDetailsExpanded`；label fallback 人话（不露 raw ID / raw enum）；
- 数据面**不变**（Store 五字段结构化 payload 保留；诊断留 Store/日志）；
- bounded Dialog + close/ESC 恢复路径保留（L-D 几何 envelope 归 SLICE-R8-03）。
"""
import os
import sys
import unittest

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(__file__))))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

_SENATE = "src/ui/gui/qml/stages/SenateStage.qml"
_CARD = "src/ui/gui/qml/components/WarProposalCard.qml"


def _read(rel_path: str) -> str:
    with open(os.path.join(PROJECT_ROOT, rel_path), encoding="utf-8") as f:
        return f.read()


def _func(source: str, name: str, span: int = 4000) -> str:
    """抽取 `function <name>` 体（到下一个缩进函数定义或 span 上限）。"""
    idx = source.find("function " + name)
    if idx < 0:
        return ""
    nxt = source.find("\n    function ", idx)
    end = nxt if nxt > idx else idx + span
    return source[idx:end]


class TestR8SenateDialogDeMachine(unittest.TestCase):
    """R8-AC-04：Senate Dialog 玩家面零 raw diagnostic。"""

    @classmethod
    def setUpClass(cls):
        cls.qml = _read(_SENATE)

    def test_no_machine_detail_label_or_json_render(self):
        self.assertNotIn("机器详情", self.qml)
        self.assertNotIn("root.senateErrorMachineJson()", self.qml)

    def test_no_raw_json_in_senate_stage(self):
        self.assertNotIn("JSON.stringify", self.qml)

    def test_no_item_ref_render(self):
        """FC-UI-04：frozen direct 行不再渲染 `item_ref`。"""
        self.assertNotIn("item_ref", self.qml)

    def test_detail_line_is_humanised(self):
        block = _func(self.qml, "senateErrorDetailLine")
        self.assertIn("senateErrorHumanMessage", block)
        self.assertNotIn("_errField", block)
        self.assertNotIn('" · "', block)

    def test_detail_extra_uses_labels_not_opaque_ids(self):
        block = _func(self.qml, "senateErrorDetailExtra")
        self.assertNotIn("war=", block)
        self.assertNotIn("commander=", block)
        self.assertNotIn("N=", block)
        self.assertIn("senateWarLanguageName", block)
        self.assertIn("senateCommanderDisplayName", block)

    def test_human_message_lookup_covers_codes(self):
        block = _func(self.qml, "senateErrorHumanMessage")
        for code in ("REINFORCEMENT_INVALID", "LEGION_POOL_EXCEEDED",
                     "COMMANDER_CLAIM_DUPLICATE", "PACKAGE_ALREADY_SUBMITTED"):
            self.assertIn(code, block)
        self.assertIn("增援军团数量不符合要求", block)
        self.assertIn("同一指挥官不能同时指挥这些战争", block)
        self.assertIn("配置未能提交", block)

    def test_label_fallback_no_raw_id(self):
        """§5.3：label 缺失 → 人话 fallback（不回退 raw ID、不猜名字）。"""
        self.assertIn("战争名称暂不可用", self.qml)
        self.assertIn("指挥官身份暂不可用", self.qml)

    def test_dialog_recovery_path_present(self):
        """R8-AC-05/08：close/ESC 恢复路径保留（bounded Dialog 不变）。"""
        self.assertIn('objectName: "senateValidationDialog"', self.qml)
        self.assertIn("closePolicy: Popup.CloseOnEscape", self.qml)
        self.assertIn("senateValidationDialog.close()", self.qml)
        self.assertIn("senateValidationDialog.open()", self.qml)

    def test_err_scope_accessor_retired_with_machine_json(self):
        """`_errScope` 仅服务于已退役 machine JSON → 一并退役。"""
        self.assertNotIn("function _errScope", self.qml)


class TestR8CardErrorHumanised(unittest.TestCase):
    """R8-AC-04：WarProposalCard 卡级错误去 machine。"""

    @classmethod
    def setUpClass(cls):
        cls.card = _read(_CARD)

    def test_no_json_in_card(self):
        self.assertNotIn("JSON.stringify", self.card)

    def test_no_expand_details_toggle(self):
        self.assertNotIn("errorDetailsText", self.card)
        self.assertNotIn("errorDetailsExpanded", self.card)
        self.assertNotIn("展开详情", self.card)
        self.assertNotIn("收起详情", self.card)

    def test_card_error_text_humanised(self):
        block = _func(self.card, "cardErrorText")
        self.assertNotIn('out += " · " + field', block)
        self.assertIn("增援军团数量不符合要求", block)
        self.assertIn("同一指挥官不能同时指挥这些战争", block)

    def test_pool_line_preserved(self):
        """pool 人话三值保留（R7 契约；读 Core 权威 details 键）。"""
        self.assertIn("function poolLine", self.card)
        self.assertIn("requested_total", self.card)
        self.assertIn("available_total", self.card)
        self.assertIn("reduce_by", self.card)

    def test_identity_text_no_raw_id_but_keeps_unselectable_hint(self):
        self.assertIn("不在候选，不可选", self.card)
        self.assertNotIn("当前 ID", self.card)

    def test_classification_fallback_humanised(self):
        self.assertIn("战争信息待更新", self.card)

    def test_field_highlight_routing_preserved(self):
        """精确字段高亮保留（涉事卡/字段）。"""
        self.assertIn('cardRoot.fieldError("reinforcement_n")', self.card)
        self.assertIn('cardRoot.codeError("COMMANDER_CLAIM_DUPLICATE")', self.card)
        self.assertIn("cardRoot.hasError ? theme.statusError", self.card)


if __name__ == "__main__":
    unittest.main()
