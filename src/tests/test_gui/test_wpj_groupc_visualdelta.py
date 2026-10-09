# src/tests/test_gui/test_wpj_groupc_visualdelta.py
"""WP-J Group C Pre-G6 VisualDelta (delta v1.3 / FC-C18–C21) — 源码级绑定断言。

三项 player-visible GUI 修复（契约级）：

- Q1 / FC-C18 / J-AC-11：「2 元老院表决」面板 body Repeater **delegate** 由裸 `ColumnLayout`
  → **带边框卡 `Rectangle`**（`#FFF6E6` / `#E0B56C` / `width:1` / `radius:4`，逐字同
  ③ 保民官否决行 L1829–1836 / ① 执政官提案卡 L1484–1498）；行高**内容驱动**；
  **保留** FC-C15–C17 的 wrap `contentItem`；不新增 nested scroll。
- Q2 / FC-C19 / J-AC-05a：`PopulationStage.candidateTable` 表头第 2 列 L270
  `"候选人"` → `"最佳候选人"`；L441 庆典赞助表头保持 `"候选人"`（负向，防误改）。
- Q3 / FC-C23（**取代 FC-C20**）/ J-AC-12：「3 保民官否决」行 `CheckBox` 自定义 `indicator`——
  `checked`→**中性 ✗**（U+2717，非 emoji）、`!checked`→空白；字形色 = 同行身份文本色 `#2C1E12`
  （禁红/禁红边红填充）；框式同 ①②；`checked`/`onToggled`/`enabled`/多选状态机**字节级不变**；
  指示器尺寸稳定（20×20，不破行几何）；`results` 态红 ✗ 仍由既有 `resultMark()` 承载。

本文件 = 源码级绑定断言（RED→GREEN 判别）。渲染层几何/双态断言见
`test_wpj_groupc_render_evidence.py`（Main.qml 离屏窗口 route=DIRECT_PRODUCTION）。

RED 支持：可用环境变量 `WPJ_GROUP_C_SENATE_QML` / `WPJ_GROUP_C_POP_QML`
把断言语料指向 pre-delta 冻结夹具（`attempts/ATTEMPT-3/red-fixtures/`），
在同一断言集上复现 RED。默认读取产品源。
"""
import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(__file__))))
SENATE_QML = os.environ.get("WPJ_GROUP_C_SENATE_QML") or os.path.join(
    PROJECT_ROOT, "src", "ui", "gui", "qml", "stages", "SenateStage.qml")
POP_QML = os.environ.get("WPJ_GROUP_C_POP_QML") or os.path.join(
    PROJECT_ROOT, "src", "ui", "gui", "qml", "stages", "PopulationStage.qml")

# 表决面板身份文本唯一识别子串（沿用 ATTEMPT-2 定位器）
IDENTITY_ANCHOR = (
    "text: (modelData.label || modelData.type) + root.voteParamDescription(modelData)"
)
# 表决面板 Repeater 数据源唯一识别子串
PANEL2_MODEL_ANCHOR = "model: sessionStore.senateSubmittedProposals || []"


def _senate():
    return open(SENATE_QML, encoding="utf-8").read()


def _pop():
    return open(POP_QML, encoding="utf-8").read()


# ---------------------------------------------------------------------------
# Q1 / FC-C18 —— 表决面板行带边框卡
# ---------------------------------------------------------------------------

def test_q1_senate_vote_row_delegate_is_bordered_card():
    """FC-C18：行 delegate 由裸 ColumnLayout → 带边框卡 Rectangle。"""
    src = _senate()
    idx = src.find(PANEL2_MODEL_ANCHOR)
    assert idx >= 0, "须定位「2 元老院表决」Repeater"
    seg = src[idx:idx + 300]
    assert "delegate: Rectangle {" in seg, "表决面板行 delegate 须为带边框卡 Rectangle（FC-C18）"
    assert "delegate: ColumnLayout {" not in seg, "行 delegate 不得仍为裸 ColumnLayout（FC-C18）"


def test_q1_card_border_matches_tribune_veto_card():
    """FC-C18：卡边框样式逐字一致（#FFF6E6 / #E0B56C / width:1 / radius:4）。"""
    src = _senate()
    idx = src.find(PANEL2_MODEL_ANCHOR)
    assert idx >= 0, "须定位「2 元老院表决」Repeater"
    card = src[idx:idx + 1500]
    for token in ('color: "#FFF6E6"', 'border.color: "#E0B56C"', "border.width: 1", "radius: 4"):
        assert token in card, f"表决行卡须含 {token}（FC-C18）"
    assert "voteRowColumn.implicitHeight" in card, "行高须内容驱动（FC-C18）"


def test_q1_keeps_wrap_content_item():
    """FC-C18 / OBS-V-2（R5 / FC-C36 承载重构）：② 身份文本由 `CheckBox.contentItem` 移出为行内
    **同级 `Text`**，但 `FC-C15–C17` wrap 语义保留（wrap + ElideNone）。"""
    src = _senate()
    idx = src.find(IDENTITY_ANCHOR)
    assert idx >= 0, "须定位表决面板身份文本（FC-C15）"
    block = src[idx:src.find("root.supportRateText(", idx)]
    assert "contentItem:" not in block, "身份文本须移出 contentItem（同级 Text，FC-C36）"
    assert "wrapMode: Text.Wrap" in block
    assert "elide: Text.ElideNone" in block
    assert "elide: Text.ElideRight" not in block


def test_q1_no_nested_scroll_in_card():
    """FC-C18：卡内不得出现第二个滚动 owner（不新增 nested scroll）。"""
    src = _senate()
    idx = src.find(PANEL2_MODEL_ANCHOR)
    card = src[idx:idx + 1500]
    assert "ScrollView" not in card and "Flickable" not in card, \
        "表决行卡内不得有 nested scroll（FC-C18）"


# ---------------------------------------------------------------------------
# Q2 / FC-C19 —— 信息表表头文案
# ---------------------------------------------------------------------------

_INFO_HEADER = (
    'Text { text: "最佳候选人"; color: "#766652"; font.pixelSize: 11; '
    "Layout.preferredWidth: 220 }"
)
_CAMPAIGN_HEADER = (
    'Text { text: "候选人"; color: "#766652"; font.pixelSize: 11; '
    "Layout.fillWidth: true }"
)


def test_q2_information_table_header_is_best_candidate():
    """FC-C19：信息表表头第 2 列 == 「最佳候选人」。"""
    assert _INFO_HEADER in _pop(), "信息表表头须为「最佳候选人」（FC-C19）"


def test_q2_campaign_header_unchanged_negative():
    """FC-C19 负向：L441 庆典赞助表头保持「候选人」（防误改）。"""
    assert _CAMPAIGN_HEADER in _pop(), "庆典赞助表头须保持「候选人」（FC-C19 负向）"


# ---------------------------------------------------------------------------
# Q1 / FC-C22（G7-Delta）—— ② 表决行 指示器↔身份文本 间距 = 与 ①③ 一致
# ---------------------------------------------------------------------------

def test_q1_vote_row_indicator_text_gap_uses_shared_constant():
    """R5（FC-C36，**FC-C22 SUPERSEDED**）：`senateVoteIdentityGap` 特例退役 —— ② 现与 ①③
    完全同构（text-less CheckBox + 同级 `Text` 于 `RowLayout{ spacing:6 }`），不再有「指示器宽 + 基准」
    的净左缩进特例。"""
    src = _senate()
    assert "readonly property int senateVoteIdentityGap" not in src, \
        "`senateVoteIdentityGap` 须退役（FC-C22 SUPERSEDED，FC-C36）"
    idx = src.find(IDENTITY_ANCHOR)
    assert idx >= 0, "须定位表决面板身份文本（FC-C36）"
    block = src[idx:src.find("root.supportRateText(", idx)]
    assert "indicator.width + root.senateVoteIdentityGap" not in block, \
        "② 不得再用 FC-C22 净缩进特例（FC-C36）"
    assert "Layout.fillWidth: true" in block, \
        "② 身份文本须为填充宽度的同级 Text（FC-C36）"


def test_q1_vote_row_no_longer_uses_control_internal_spacing():
    """FC-C22：② 行间距不得再仅由控件内部 `spacing` 决定（与 ①③ 不一致的根因）。"""
    src = _senate()
    idx = src.find(IDENTITY_ANCHOR)
    assert idx >= 0, "须定位表决面板身份文本（FC-C22）"
    block = src[idx:src.find("root.supportRateText(", idx)]
    assert "proposalVoteCheck.indicator.width + proposalVoteCheck.spacing" not in block, \
        "② 间距不得再由控件内部 spacing 决定（FC-C22）"


def test_q1_vote_row_keeps_wrap_content_item():
    """R5（FC-C36 承载重构）：② 身份文本保留 `FC-C15–C17` wrap（wrap + ElideNone）但
    **移出 contentItem**（行内同级 `Text`）。"""
    src = _senate()
    idx = src.find(IDENTITY_ANCHOR)
    assert idx >= 0, "须定位表决面板身份文本（FC-C22）"
    block = src[idx:src.find("root.supportRateText(", idx)]
    assert "contentItem:" not in block, "身份文本须移出 contentItem（同级 Text，FC-C36）"
    assert "wrapMode: Text.Wrap" in block
    assert "elide: Text.ElideNone" in block


# ---------------------------------------------------------------------------
# Q3 / FC-C31（R4 Delta，**取代 FC-C23/FC-C26/FC-C28/FC-C29**）
# ③ 否决行勾选框回归**平台默认**指示器（撤自绘框/自绘叉）；③ 结果态红 ✗ 保留。
# ---------------------------------------------------------------------------

_VETO_ID_ANCHOR = "id: vetoCheck"


def _veto_checkbox_segment():
    src = _senate()
    idx = src.find(_VETO_ID_ANCHOR)
    assert idx >= 0, "否决行 CheckBox 须有 id（FC-C31）"
    end = src.find("ColumnLayout {", idx)
    assert end > idx, "须定位否决行 CheckBox 块边界（FC-C31）"
    return src, src[idx:end]


def test_q3_veto_checkbox_has_no_custom_indicator():
    """FC-C31（R4 回退）：③ 否决行 CheckBox **不得**再声明自定义 `indicator`
    （撤 FC-C23/FC-C26/FC-C28/FC-C29 自绘框/自绘叉）⇒ 回落平台默认指示器。"""
    _src, seg = _veto_checkbox_segment()
    assert "indicator:" not in seg, "③ 不得残留自定义 indicator（FC-C31）"
    assert "rotation: 45" not in seg and "rotation: -45" not in seg, \
        "③ 不得残留自绘叉子图元（FC-C31）"
    assert 'border.color: "#C8A870"' not in seg and "implicitWidth: 20" not in seg, \
        "③ 不得残留 USS 自绘框规格（FC-C31）"


def test_q3_state_machine_byte_identical():
    """FC-C31(3)：③ checked/onToggled/enabled 语义字节级不变。"""
    _src, seg = _veto_checkbox_segment()
    assert "checked: root.hasSelectedVeto(Number(modelData.id))" in seg
    assert "onToggled: root.setVetoSelected(Number(modelData.id), checked)" in seg
    assert ('enabled: sessionStore.senateCurrentStep === "tribune_veto" '
            "&& sessionStore.canManuallySelectSenateVeto") in seg


def test_q3_result_state_red_mark_unchanged():
    """FC-C31(5)：③ results 态红 ✗ 仍由既有独立 resultMark()/resultMarkColor() 承载（不改）。"""
    src = _senate()
    assert '(item.result === "rejected" || item.result === "vetoed") ? "\\u2717" : "\\u2713"' in src, \
        "resultMark() 须保持（③ results 态 ✗，FC-C31 不改）"
    assert '? "#B3261E" : theme.statusSuccess' in src, \
        "resultMarkColor() 须保持（③ results 态红，FC-C31 不改）"


# ---------------------------------------------------------------------------
# Q1 / FC-C32（R4 Delta，**取代 FC-C25**）—— ② 非输入态结果字形 = 行内独立无框 Text
# Q2 / FC-C31（R4 Delta，**取代 FC-C25/FC-C26**）—— senate 三面板行回归默认勾选框
# ---------------------------------------------------------------------------

_PANEL2_GLYPH_ANCHOR = 'visible: sessionStore.senateCurrentStep !== "senate_vote"'


def _panel2_segment():
    src = _senate()
    idx = src.find(_PANEL2_GLYPH_ANCHOR)
    assert idx >= 0, "须定位 ② 结果字形（FC-C32）"
    end = src.find("root.supportRateText(", idx)
    assert end > idx, "须定位 ② 表决行块边界（FC-C32）"
    return src, src[idx:end]


def test_q1_panel2_result_mark_is_inline_frameless_text():
    """FC-C32：② 非输入态结果字形**移出** indicator，改由**行内独立无框 `Text`** 承载；
    谓词 = ②-local `senateResultMark(modelData)`；② 不得再声明自定义 `indicator`。"""
    _src, seg = _panel2_segment()
    assert "text: root.senateResultMark(modelData)" in seg, \
        "② 结果字形须由 senateResultMark(modelData) 承载（FC-C32）"
    assert "color: root.senateResultMarkColor(modelData)" in seg, \
        "② 结果字形色须由 senateResultMarkColor(modelData) 决定（FC-C32）"
    assert 'visible: sessionStore.senateCurrentStep !== "senate_vote"' in seg, \
        "结果字形须在非输入态可见（FC-C32）"
    assert "indicator:" not in seg, "② 不得再声明自定义 indicator（FC-C31/FC-C32）"


def test_q1_panel2_result_mark_uses_model_result_not_voteresultfor():
    """FC-C32 / OBS-G7T2-4：② 结果字形**禁**由 voteResultFor()（无 .result）驱动。"""
    _src, seg = _panel2_segment()
    assert "senateResultMark(modelData)" in seg
    assert "senateResultMark(root.voteResultFor" not in seg, \
        "结果字形禁用 voteResultFor()（FC-C32）"


def test_q1_panel2_keeps_wrap_content_item_and_input_semantics():
    """FC-C31(3)(4) + R5（FC-C36）：② 身份文本为行内**同级 `Text`**（wrap + ElideNone；
    **不在** `contentItem`）+ 输入态勾选语义保留；不再有自绘框、不再用 FC-C22 净缩进；
    ② 勾选框新增非输入态隐藏 `visible` 门。"""
    _src, seg = _panel2_segment()
    assert "contentItem:" not in seg
    assert "wrapMode: Text.Wrap" in seg
    assert "elide: Text.ElideNone" in seg
    assert 'enabled: sessionStore.senateCurrentStep === "senate_vote"' in seg
    assert "checked: root.hasSelectedSenateVote(Number(modelData.id))" in seg
    assert "onToggled: root.setSenateVoteSelected(Number(modelData.id), checked)" in seg
    assert "readonly property int senateVoteIdentityGap" not in seg
    assert "indicator.width + root.senateVoteIdentityGap" not in seg
    assert 'visible: sessionStore.senateCurrentStep === "senate_vote"' in seg


def test_q2_senate_rows_use_platform_default_checkboxes():
    """FC-C31：senate 三面板行内选择控件一律**平台默认**（无自定义 `indicator`）；
    ①③非输入态由 `visible` 门隐藏（② 结果字形另有行内独立 Text）。"""
    src = _senate()
    assert src.count("CheckBox {") == 3, "SenateStage 仅应有 ①②③ 三处 CheckBox（FC-C31）"
    assert "indicator:" not in src, "三面板行不得残留自绘 indicator（FC-C31）"
    assert "visible: isProposal" in src, "① 须非输入态隐藏（FC-C31）"
    assert 'visible: sessionStore.senateCurrentStep !== "results"' in src, "③ 须非输入态隐藏（FC-C31）"


if __name__ == "__main__":
    import pytest
    raise SystemExit(pytest.main([__file__, "-v"]))
