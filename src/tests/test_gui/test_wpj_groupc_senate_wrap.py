# src/tests/test_gui/test_wpj_groupc_senate_wrap.py
"""WP-J Group C-2 (J-AC-05b / BL-R4G7-03) — nonWar 法案卡标题/详情 wrap + 卡高内容驱动。

冻结契约（`02-sa-design/GroupC/` v1.1 §4）：
- FC-C09 mandatory：`proposalTitle` / `proposalDetail`（proposal 卡 + 提交态卡 + Stage-3 行）。
- FC-C10 mandatory 文本 `wrapMode: Text.Wrap` + `elide: Text.ElideNone`；卡/行高**内容驱动**（隐式高）。
- FC-C13 覆盖 nonWar 卡 + 提交态卡 + Stage-3 否决/结果行；**不改** War Card / 汇总行。

本文件 = 源码级绑定断言（RED→GREEN 判别）；渲染层几何断言见
`test_wpj_groupc_render_evidence.py`（Main.qml 离屏窗口 route=DIRECT_PRODUCTION）。
"""
import os
import sys

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(__file__))))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

SENATE_QML = os.path.join(PROJECT_ROOT, "src", "ui", "gui", "qml", "stages", "SenateStage.qml")


def _source():
    return open(SENATE_QML, encoding="utf-8").read()


def test_source_mandatory_faces_use_wrap_not_elide():
    """mandatory 标题/详情面须 wrap + ElideNone（FC-C10），不再单行 elide 截断。"""
    src = _source()
    assert src.count("wrapMode: Text.Wrap") >= 3, "mandatory 文本面须 wrap（FC-C10）"
    assert src.count("elide: Text.ElideNone") >= 3, "mandatory 文本须 ElideNone（FC-C10）"


def test_source_no_elide_right_on_mandatory_faces():
    """非 War 法案卡标题/提交态详情 + Stage-3 行标题/详情 不得再 elide ElideRight（本缺陷根因）。"""
    src = _source()
    blocks = []
    # 每处 mandatory Text 以 proposalTitle/proposalDetail 定位，检查其后 8 行无 ElideRight
    for marker in ("text: root.proposalTitle(modelData)", "text: root.proposalDetail(modelData)"):
        idx = 0
        while True:
            pos = src.find(marker, idx)
            if pos < 0:
                break
            blocks.append(src[pos:pos + 320])
            idx = pos + 1
    assert blocks, "须定位到 mandatory 文本面"
    for block in blocks:
        assert "elide: Text.ElideRight" not in block, \
            "mandatory 文本面不得再 elide ElideRight（FC-C10）"


def test_source_card_and_row_height_content_driven():
    """FC-C10：非 War 提交态卡与 Stage-3 行高不再固定 48/66（内容驱动）。"""
    src = _source()
    assert "cardColumn.implicitHeight + 12" in src, "卡高须内容驱动（FC-C10）"
    assert "stageThreeRow.implicitHeight + 16" in src, "Stage-3 行高须内容驱动（FC-C10）"
    assert 'sessionStore.senateCurrentStep === "results" ? 66 : 48' not in src, \
        "Stage-3 行高不得保留固定 66/48"


def test_source_summary_rows_protected():
    """FC-C13/§5.2 受保护面：公示区结果汇总行维持现状（不得误改）。"""
    src = _source()
    assert "maximumLineCount" in src  # 汇总行策略仍在
    # vetoed/rejected/passed 汇总行文案函数仍在（未被误删）
    for fn in ("function vetoedResultText()", "function rejectedResultText()",
               "function passedResultText()"):
        assert fn in src, f"汇总行文案函数须保留：{fn}"


# ---------------------------------------------------------------------------
# WP-J Group C Pre-G6 回归（delta v1.2 / FC-C15–C17）——「2 元老院表决」面板
# 提案身份文本（原 L1757 CheckBox.text）：既有上游定位器（proposalTitle/Detail）
# 不命中此面，故此处补 L1757 定位器。
# ---------------------------------------------------------------------------

# 该面身份文本的唯一识别子串（`CheckBox.text` 表达式，delta §1.2 pin）
_L1757_IDENTITY_ANCHOR = (
    "text: (modelData.label || modelData.type) + root.voteParamDescription(modelData)"
)


def test_source_senate_vote_panel_identity_text_located():
    """FC-C15：须能定位「2 元老院表决」面板提案身份文本（原 L1757）。"""
    src = _source()
    assert _L1757_IDENTITY_ANCHOR in src, \
        "须定位元老院表决面板提案身份文本（FC-C15）"
    # 该面板 body 唯一 scroll owner（FC-C16 单一 scroll owner）仍在
    assert "senateSubmittedProposals" in src, "Panel2 数据源须保留"


def test_source_senate_vote_panel_identity_text_wraps():
    """FC-C16/C17（R5 / FC-C36 承载重构）：Panel2 提案身份文本承载于行内**同级 `Text`**
    （wrap + ElideNone；**不在** `CheckBox.contentItem` 内），非输入态勾选框隐藏后身份文本仍保留。"""
    src = _source()
    idx = src.find(_L1757_IDENTITY_ANCHOR)
    assert idx >= 0, "须定位元老院表决面板提案身份文本（FC-C15）"
    # 承载块边界 = anchor → 紧随其后的支持率辅助行（root.supportRateText(...)）
    end = src.find("root.supportRateText(", idx)
    assert end > idx, "须定位承载块边界（支持率辅助行）"
    block = src[idx:end]
    assert "contentItem:" not in block, \
        "身份文本须移出 `CheckBox.contentItem` 为同级 Text（FC-C36）"
    assert "wrapMode: Text.Wrap" in block, \
        "表决面板身份文本须 wrapMode: Text.Wrap（FC-C16）"
    assert "elide: Text.ElideNone" in block, \
        "表决面板身份文本须 elide: Text.ElideNone（FC-C16）"
    assert "elide: Text.ElideRight" not in block, \
        "表决面板身份文本不得 elide ElideRight（FC-C16）"


def test_source_senate_vote_panel_keeps_checked_semantics():
    """FC-C16（G7 Test R7 Delta v2.3 / FC-C41 **修订**）：承载仍为 CheckBox（整行可点选/
    勾选）；`checked` 由常量 `true` 修订为绑定 ② 专属选择集 `hasSelectedSenateVote`（默认未勾选）；
    数据源 `senateSubmittedProposals` 不变。"""
    src = _source()
    idx = src.find(_L1757_IDENTITY_ANCHOR)
    assert idx >= 0, "须定位元老院表决面板提案身份文本（FC-C15）"
    end = src.find("root.supportRateText(", idx)
    assert end > idx, "须定位承载块边界（支持率辅助行）"
    # 定位器窗口修正（VisualDelta）：承载外层新增带边框卡容器 + 缩进 4 空格后，
    # 原 400 字节回看窗不再覆盖 `CheckBox {`（纯粹定位器窗口脆弱性，非契约变化）。
    # 改为向后搜索最近的承载 `CheckBox {`；断言语义随 FC-C41 修订（checked 由常量→绑定选择集）。
    cb_start = src.rfind("CheckBox {", 0, idx)
    assert cb_start >= 0, "须定位承载 CheckBox（勾选语义保持，FC-C16）"
    block = src[cb_start:end]
    assert "CheckBox {" in block, "承载仍须为 CheckBox（勾选语义保持，FC-C16）"
    assert "checked: root.hasSelectedSenateVote(Number(modelData.id))" in block, \
        "checked 须绑定 ② 专属选择集（FC-C41）"
    assert "onToggled: root.setSenateVoteSelected(Number(modelData.id), checked)" in block, \
        "② 须新增 onToggled 写回选择集（FC-C41）"
    # 支持率辅助行（L1759–1766 语义）不被误改
    assert "supportRateText" in src, "支持率辅助行须保留"


if __name__ == "__main__":
    import pytest
    raise SystemExit(pytest.main([__file__, "-v"]))
