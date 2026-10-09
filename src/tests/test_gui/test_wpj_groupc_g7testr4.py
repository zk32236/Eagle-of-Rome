# src/tests/test_gui/test_wpj_groupc_g7testr4.py
"""WP-J Group C G7 Test R4 Delta（delta v1.9 / FC-C31 + FC-C32）— 源码级绑定断言。

Owner 2026-10-09 G7-Test-R4：Q2 = **放弃方案甲**（统一自绘 USS 勾选框）⇒ ①②③ + 战争卡
勾选框**全部回归平台默认样式**（系统勾选框；③ 勾选 = 系统 ☑）；Q1 = ② 结果字形**仅反映
「元老院表决」**（依据 `veto_candidate_ids = passed && !vetoed` ⇒ `vetoed ⟹ 元老院已通过`）。

冻结契约（`02-sa-design/GroupC/WP-J-GroupC-G7TestR4Delta-v1.9-2026-10-09.md`，权威）：

- **FC-C31（Q2 回退）：** `SenateStage.qml` ① `CheckBox`（proposalSelectCheck）/ ②
  （proposalVoteCheck）/ ③（vetoCheck）+ `components/WarProposalCard.qml` `CheckBox`（checkBox）
  ——**全部移除自定义 `indicator`**（及随其附着的自绘勾/自绘叉子图元）⇒ 回落**平台默认样式
  指示器**（系统勾选框；③ 勾选 = 系统 ☑，**不再要求 ⮽**）。状态机（`checked`/`onToggled`/
  `enabled`/`visible` 门/选择与表决语义）**字节级不变**；保留 `FC-C18` 行卡 /
  `FC-C15–C17` wrap / 单一 `ScrollView`；**② 非输入态结果字形保留**（K2=A），但**移出**被撤的
  `indicator`、改由**行内独立无框 `Text`** 承载（谓词见 FC-C32）。
- **FC-C32（Q1 口径）：** ② 结果字形 **②-local** 谓词 `senateResultMark()`：
  `rejected → ✗`；`passed`/`vetoed → ✓`；无表决数据行（`.result` 缺失/未知）→ **空白（禁 ✗）**。
  **禁**改共享 `resultMark()`/`resultMarkColor()`（③ 否决面板仍需 `vetoed → ✗`）。

本文件 = 源码级绑定断言（RED→GREEN 判别）。渲染层几何/可比判据/有头复验见
`test_wpj_groupc_render_evidence.py`（Main.qml 离屏窗口 route=DIRECT_PRODUCTION）。
"""
import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(__file__))))
SENATE_QML = os.path.join(PROJECT_ROOT, "src", "ui", "gui", "qml", "stages", "SenateStage.qml")
WAR_QML = os.path.join(PROJECT_ROOT, "src", "ui", "gui", "qml", "components", "WarProposalCard.qml")

# 已撤（FC-C28/C29）自绘 USS 框规格六元组 + 自绘勾/叉笔画（R4 后须全部归零）
USS_TOKENS = (
    "implicitWidth: 20",
    "implicitHeight: 20",
    "radius: 3",
    'border.color: "#C8A870"',
    "border.width: 1",
)
# 禁 emoji 转义（\uXXXX；含 VS16）
EMOJI_ESCAPES = (r"\u274C", r"\u274c", r"\u2705", r"\uFE0F", r"\ufe0f")

# 四行勾选框面锚点（start_anchor, end_anchor）
_FACE_ANCHORS = {
    "①": ("id: proposalSelectCheck", "text: root.proposalTitle(modelData)"),
    "②": ('visible: sessionStore.senateCurrentStep !== "senate_vote"', "root.supportRateText("),
    "③": ("id: vetoCheck", "ColumnLayout {"),
    "战争卡": ("id: checkBox", "\n\n"),
}


def _senate():
    return open(SENATE_QML, encoding="utf-8").read()


def _war():
    return open(WAR_QML, encoding="utf-8").read()


def _seg(src, start_anchor, end_anchor):
    idx = src.find(start_anchor)
    assert idx >= 0, f"须定位锚点：{start_anchor}"
    end = src.find(end_anchor, idx + len(start_anchor))
    assert end > idx, f"须定位结束锚点：{end_anchor}"
    return src[idx:end]


def _face_seg(name):
    src = _war() if name == "战争卡" else _senate()
    return _seg(src, *_FACE_ANCHORS[name])


# ---------------------------------------------------------------------------
# FC-C31 —— 四行勾选框全部移除自定义 `indicator`（回落平台默认）
# ---------------------------------------------------------------------------

def test_c31_senate_has_no_custom_indicator_declaration():
    """FC-C31(1)：`SenateStage.qml` 内**任一** `CheckBox` 均不声明 `indicator`
    （穷举 ①②③ 归零）；仍恰有 3 处 CheckBox。"""
    src = _senate()
    assert src.count("CheckBox {") == 3, "SenateStage 仅应有 ①②③ 三处 CheckBox（FC-C31）"
    assert "indicator:" not in src, "①②③ 均不得残留自定义 indicator（FC-C31）"


def test_c31_warcard_has_no_custom_indicator_declaration():
    """FC-C31(1)：`WarProposalCard.qml` 战争卡 `CheckBox` 亦不声明 `indicator`。"""
    war = _war()
    assert "CheckBox {" in war, "战争卡须保有 CheckBox"
    assert "indicator:" not in war, "战争卡不得残留自定义 indicator（FC-C31）"


def test_c31_no_uss_spec_or_selfdrawn_glyph_remaining():
    """FC-C31(1)：四面勾选框均不得残留 USS 自绘框规格（20×20 / #C8A870 / radius 3 等）
    及自绘勾/叉子图元（rotation 45 / -45）。"""
    for name in _FACE_ANCHORS:
        seg = _face_seg(name)
        for tok in USS_TOKENS:
            assert tok not in seg, f"{name} 勾选框面不得残留 USS 规格 {tok}（FC-C31）"
        assert "rotation: 45" not in seg and "rotation: -45" not in seg, \
            f"{name} 勾选框面不得残留自绘勾/叉子图元（FC-C31）"
    assert 'border.color: "#C8A870"' not in _senate(), "SenateStage 不得残留 USS 边框色（FC-C31）"
    assert 'border.color: "#C8A870"' not in _war(), "WarProposalCard 不得残留 USS 边框色（FC-C31）"


def test_c31_panel1_state_machine_byte_identical():
    """FC-C31(3)：① 状态机（visible/enabled/checked/onToggled）逐字不变。"""
    seg = _face_seg("①")
    assert "visible: isProposal" in seg
    assert "enabled: sessionStore.canCreateSenateProposal" in seg
    assert "checked: root.hasSelectedProposal(modelData.key)" in seg
    assert "onToggled: root.setProposalSelected(modelData.key, checked)" in seg


def test_c31_panel1_result_mark_unchanged():
    """FC-C31(5) 守恒：① 结果标记（硬编码绿 ✓ `Text`，非本勾选框）不动。"""
    seg = _face_seg("①")
    assert 'text: "\\u2713"' in seg, "① 结果标记 ✓ 仍须存在（不动）"
    assert "color: theme.statusSuccess" in seg, "① 结果标记色仍为 theme.statusSuccess（不动）"
    assert "visible: !isProposal" in seg, "① 结果标记可见门不变（不动）"


def test_c31_panel2_state_machine_and_wrap_unchanged():
    """FC-C31(3)(4) + R5（FC-C36）：② 状态机（enabled/checked 语义）逐字不变；身份文本
    由 `CheckBox.contentItem` 移出为行内**同级 `Text`**，wrap 语义（`FC-C15–C17`）保留；数据源不变。"""
    seg = _face_seg("②")
    assert 'enabled: sessionStore.senateCurrentStep === "senate_vote"' in seg
    assert "checked: root.hasSelectedSenateVote(Number(modelData.id))" in seg
    assert "onToggled: root.setSenateVoteSelected(Number(modelData.id), checked)" in seg
    assert "contentItem:" not in seg
    assert "wrapMode: Text.Wrap" in seg
    assert "elide: Text.ElideNone" in seg
    assert "elide: Text.ElideRight" not in seg


def test_c31_panel2_result_glyph_is_inline_frameless_text_outside_indicator():
    """FC-C31(5)：② 非输入态结果字形**保留**但**移出** indicator ⇒ 行内独立无框 `Text` 承载
    （②-local `senateResultMark(modelData)`，可见门 = 非输入态）。"""
    seg = _face_seg("②")
    assert "text: root.senateResultMark(modelData)" in seg, \
        "② 结果字形须由行内独立 Text 承载（FC-C31(5)）"
    assert 'visible: sessionStore.senateCurrentStep !== "senate_vote"' in seg, \
        "② 结果字形须在非输入态可见（FC-C31(5)）"
    assert "indicator" not in seg or "indicator:" not in seg, \
        "② 结果字形不得再嵌于 indicator（FC-C31(5)）"


def test_c31_panel3_state_machine_byte_identical():
    """FC-C31(3)：③ 多选/提交/否决状态机逐字不变。"""
    seg = _face_seg("③")
    assert 'visible: sessionStore.senateCurrentStep !== "results"' in seg
    assert ('enabled: sessionStore.senateCurrentStep === "tribune_veto" '
            "&& sessionStore.canManuallySelectSenateVeto") in seg
    assert "checked: root.hasSelectedVeto(Number(modelData.id))" in seg
    assert "onToggled: root.setVetoSelected(Number(modelData.id), checked)" in seg


def test_c31_panel3_result_mark_unchanged():
    """FC-C31(5) 守恒：③ results 态红 ✗ 仍由既有**独立** `resultMark()` `Text` 承载（不动）。"""
    src = _senate()
    idx = src.find("id: vetoCheck")
    assert idx >= 0
    pre = src[max(0, idx - 400):idx]
    assert "root.resultMark(modelData)" in pre, "③ 结果标记仍用 resultMark(modelData)（不动）"
    assert "root.resultMarkColor(modelData)" in pre, "③ 结果标记色仍用 resultMarkColor(modelData)（不动）"


def test_c31_warcard_state_machine_byte_identical():
    """FC-C31(3)：战争卡状态机（enabled/checked/onToggled/emitDraft）逐字不变。"""
    seg = _face_seg("战争卡")
    assert "enabled: cardRoot.editable && cardRoot.routeReady" in seg
    assert "checked: cardRoot.checkedNow" in seg
    assert 'onToggled: cardRoot.emitDraft({"checked": checked})' in seg


def test_c31_no_emoji_in_changed_surfaces():
    """硬约束：四面勾选框不得引入 emoji 转义（\\u274C / \\u2705 / VS16）。"""
    for name in _FACE_ANCHORS:
        seg = _face_seg(name)
        for tok in EMOJI_ESCAPES:
            assert tok not in seg, f"{name} 变更面不得含 emoji 转义 {tok}"


# ---------------------------------------------------------------------------
# FC-C32 —— ② 元老院表决 结果字形 仅反映「元老院表决」（②-local 谓词）
# ---------------------------------------------------------------------------

def test_c32_senate_result_mark_local_predicate():
    """FC-C32：须有 ②-local `senateResultMark()`：`rejected → ✗`；`passed`/`vetoed → ✓`；
    缺失/未知 → 空白（禁 ✗）。"""
    src = _senate()
    assert "function senateResultMark(item)" in src, "须定义 senateResultMark()（FC-C32）"
    fn = _seg(src, "function senateResultMark(item)", "function senateResultMarkColor(item)")
    assert 'item.result === "rejected"' in fn and "\\u2717" in fn, \
        "senateResultMark 须把 rejected → ✗（FC-C32）"
    assert 'item.result === "passed"' in fn and 'item.result === "vetoed"' in fn, \
        "senateResultMark 须把 passed/vetoed → ✓（FC-C32）"
    assert "return \"\"" in fn, "无表决数据行须返回空白（禁 ✗，FC-C32）"
    # ② 结果字形须由 ②-local 谓词承载（非共享 resultMark）
    seg2 = _face_seg("②")
    assert "root.senateResultMark(modelData)" in seg2
    assert "root.resultMark(modelData)" not in seg2, "② 不得用共享 resultMark()（FC-C32）"


def test_c32_senate_result_mark_color_local():
    """FC-C32：`senateResultMarkColor()` 仅 `rejected` 为红 `#B3261E`，其余绿（②-local）。"""
    src = _senate()
    assert "function senateResultMarkColor(item)" in src
    fn = _seg(src, "function senateResultMarkColor(item)", "\n    }\n")
    assert 'item.result === "rejected"' in fn and "#B3261E" in fn, \
        "senateResultMarkColor 须把 rejected → 红（FC-C32）"
    assert "theme.statusSuccess" in fn, "其余须绿 theme.statusSuccess（FC-C32）"


def test_c32_shared_result_mark_unchanged():
    """FC-C32 守恒：共享 `resultMark()`/`resultMarkColor()` **未改**（③ 否决面板仍需
    `vetoed → ✗`；无第二表决红叉源）。"""
    src = _senate()
    assert '(item.result === "rejected" || item.result === "vetoed") ? "\\u2717" : "\\u2713"' in src, \
        "共享 resultMark() 须保持（③ results 态 vetoed → ✗，FC-C32 不改）"
    assert '? "#B3261E" : theme.statusSuccess' in src, \
        "共享 resultMarkColor() 须保持（FC-C32 不改）"


def test_c32_panel2_result_mark_not_driven_by_voteresultfor():
    """FC-C32 / OBS-G7T2-4：② 结果字形**禁**由 `voteResultFor()` 驱动（其项无 `.result` ⇒ 恒绿）。"""
    seg = _face_seg("②")
    assert "senateResultMark(modelData)" in seg
    assert "senateResultMark(root.voteResultFor" not in seg, "结果字形禁用 voteResultFor()（FC-C32）"


if __name__ == "__main__":
    import pytest
    raise SystemExit(pytest.main([__file__, "-v"]))
