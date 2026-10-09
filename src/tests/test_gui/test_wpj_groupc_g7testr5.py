# src/tests/test_gui/test_wpj_groupc_g7testr5.py
"""WP-J Group C G7 Test R5 Delta（delta v2.0 / FC-C35 + FC-C36 + FC-C37）— 源码/结构 + 步骤相 RENDER 断言。

Owner 2026-10-09 G7-Test-R5 Q1（一层诉求、两点）：
- Q1(1) 结果标记**时点**：② 元老院表决**一完成（`tribune_veto` 步）即显**绿 ✓ / 红 ✗，**不再**等到
  `results`（保民官否决后）。
- Q1(2) 勾选框**投后隐藏**：② 行非输入态**不再显示勾选框**（含平台默认指示器）。

冻结契约（`02-sa-design/GroupC/WP-J-GroupC-G7TestR5Diag-Delta-v2.0-2026-10-09.md`，权威）：
- **FC-C35**：② 结果字形数据源**扩展** = `modelData.result`（`results` 步权威）∪
  `root.voteResultFor(item.id).passed`（`tribune_veto` 步、`.result` 缺失时的元老院表决投影回退）；
  `total_influence>0 ⇒ passed ? ✓ : ✗`，否则空白。`vetoed` **不改写** ②；**禁**改共享
  `resultMark()`/`resultMarkColor()`；**禁第二红叉源**。
- **FC-C36**：② `CheckBox` 新增 `visible: senateCurrentStep === "senate_vote"`；② 身份文本移出
  `contentItem` 为行内**同级 `Text`**（保 `FC-C15–C17` wrap：`wrapMode: Text.Wrap` + `elide: ElideNone`）；
  `FC-C22`（`senateVoteIdentityGap`）**退役**；**禁**覆写 `indicator`；状态机（`checked`/`enabled`/
  `onToggled`/选择与表决语义）**字节级不变**；**仅 ②**。
- **FC-C37**：`tribune_veto`/`results` **步骤相对照** + 源码/结构 + **有头 live**（本环境无头，如实登记）+ 几何。

本文件 = 源码级绑定断言 + RENDER_AUTOMATED 步骤相对照（复用 `test_wpj_groupc_render_evidence` 的
离屏生产链 helper；route = DIRECT_PRODUCTION）。
"""
import json
import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(__file__))))
SENATE_QML = os.path.join(PROJECT_ROOT, "src", "ui", "gui", "qml", "stages", "SenateStage.qml")
WAR_QML = os.path.join(PROJECT_ROOT, "src", "ui", "gui", "qml", "components", "WarProposalCard.qml")

EVIDENCE_BASE = (
    "/mnt/e/OpenClaw/Projects/EOR/workspace/EOR20260821-01 GUI-BETA-R1"
    "/WP-J_Player-Visible-Feedback-and-Actionability/03-da-evidence/GroupC"
)
_EVID_DIR = "Group-C-G7TestR5Delta"

# ② 行身份文本唯一识别子串（沿 Group C 定位器）
IDENTITY_ANCHOR = (
    "text: (modelData.label || modelData.type) + root.voteParamDescription(modelData)"
)
# 已撤（FC-C28/C29）自绘 USS 框规格六元组 + 自绘勾/叉笔画（R4/R5 后须全部归零）
USS_TOKENS = (
    "implicitWidth: 20",
    "implicitHeight: 20",
    "radius: 3",
    'border.color: "#C8A870"',
    "border.width: 1",
)
EMOJI_ESCAPES = (r"\u274C", r"\u274c", r"\u2705", r"\uFE0F", r"\ufe0f")

# 复用 render_evidence 的离屏生产链 helper（route=DIRECT_PRODUCTION）
from src.tests.test_gui import test_wpj_groupc_render_evidence as R  # noqa: E402


def _senate():
    return open(SENATE_QML, encoding="utf-8").read()


def _war():
    return open(WAR_QML, encoding="utf-8").read()


# ---------------------------------------------------------------------------
# FC-C36 —— 源码/结构断言（② 勾选框 visible 门 + 身份文本承载重构 + FC-C22 退役）
# ---------------------------------------------------------------------------

def test_r5_source_panel2_checkbox_has_visible_gate():
    """FC-C36(1)：② `CheckBox{id: proposalVoteCheck}` 须声明
    `visible: sessionStore.senateCurrentStep === "senate_vote"`（非输入态不渲染勾选框）。"""
    src = _senate()
    idx = src.find("id: proposalVoteCheck")
    assert idx >= 0, "须定位 ② CheckBox（FC-C36）"
    seg = src[idx:idx + 700]
    assert 'visible: sessionStore.senateCurrentStep === "senate_vote"' in seg, \
        "② CheckBox 须有输入态 visible 门（FC-C36）"


def test_r5_source_panel2_identity_is_sibling_text_not_contentitem():
    """FC-C36(2)：② 身份文本为行内**同级 `Text`**（**不在**任何 `CheckBox.contentItem` 内）。"""
    src = _senate()
    idx = src.find(IDENTITY_ANCHOR)
    assert idx >= 0, "须定位 ② 身份文本（FC-C36）"
    block = src[idx:src.find("root.supportRateText(", idx)]
    assert "contentItem:" not in block, "② 身份文本须移出 contentItem 为同级 Text（FC-C36）"
    assert "wrapMode: Text.Wrap" in block, "② 身份文本须 wrapMode: Text.Wrap（FC-C15–C17）"
    assert "elide: Text.ElideNone" in block, "② 身份文本须 elide: Text.ElideNone（FC-C15–C17）"
    assert "elide: Text.ElideRight" not in block, "② 身份文本不得 elide ElideRight"


def test_r5_source_senate_vote_identity_gap_retired():
    """FC-C36(6)：`senateVoteIdentityGap`（FC-C22）与 contentItem 净缩进公式**退役**。"""
    src = _senate()
    assert "readonly property int senateVoteIdentityGap" not in src, \
        "`senateVoteIdentityGap` 须退役（FC-C22 SUPERSEDED，FC-C36）"
    assert "indicator.width + root.senateVoteIdentityGap" not in src, \
        "contentItem 净缩进公式须退役（FC-C22 SUPERSEDED，FC-C36）"


def test_r5_source_panel2_input_state_semantics_byte_identical():
    """FC-C36(5) + G7 Test R7 Delta（v2.3 / FC-C41 修订）：② 输入态 `enabled` 语义不变；
    `checked` 由常量 `true` **修订**为绑定 ② 专属选择集
    （`root.hasSelectedSenateVote(Number(modelData.id))`）+ `onToggled` 写回选择集。"""
    src = _senate()
    idx = src.find("id: proposalVoteCheck")
    assert idx >= 0
    seg = src[idx:idx + 700]
    assert 'enabled: sessionStore.senateCurrentStep === "senate_vote"' in seg
    assert "checked: root.hasSelectedSenateVote(Number(modelData.id))" in seg
    assert "onToggled: root.setSenateVoteSelected(Number(modelData.id), checked)" in seg
    # ② 专属选择集存在 + 默认空（未勾选 = 否决）
    assert "property var selectedSenateVoteIds: []" in src


def test_r5_source_no_custom_indicator_four_faces():
    """FC-C36(4)/FC-C31：四面勾选框（①②③ + 战争卡）均**不**声明自定义 `indicator`。"""
    senate = _senate()
    war = _war()
    assert senate.count("CheckBox {") == 3, "SenateStage 仅应有 ①②③ 三处 CheckBox"
    assert "indicator:" not in senate, "①②③ 均不得残留自定义 indicator"
    assert "CheckBox {" in war and "indicator:" not in war, "战争卡不得残留自定义 indicator"


# ---------------------------------------------------------------------------
# FC-C35 —— 源码/结构断言（结果字形谓词含 voteResultFor() 回退；共享 resultMark 未动）
# ---------------------------------------------------------------------------

def test_r5_source_senate_result_mark_has_voteresultfor_fallback():
    """FC-C35：②-local `senateResultMark()` 须含 `voteResultFor()` 回退分支
    （`.result` 缺失 / `total_influence>0` ⇒ `passed ? ✓ : ✗`）。"""
    src = _senate()
    assert "function senateResultMark(item)" in src
    fn = src[src.find("function senateResultMark(item)"):
             src.find("function senateResultMarkColor(item)")]
    assert "root.voteResultFor(item.id)" in fn, "senateResultMark 须含 voteResultFor() 回退（FC-C35）"
    assert "total_influence > 0" in fn, "回退须以 total_influence>0 为门（FC-C35）"
    assert 'item.result === "rejected"' in fn and "\\u2717" in fn, "rejected → ✗ 守恒"
    assert 'item.result === "passed"' in fn and 'item.result === "vetoed"' in fn, "passed/vetoed → ✓ 守恒"
    assert "return \"\"" in fn, "无表决数据 → 空白（禁 ✗）守恒"


def test_r5_source_senate_result_mark_color_fallback():
    """FC-C35：`senateResultMarkColor()` 回退分支——`.result` 缺失且表决未通过 ⇒ 红 `#B3261E`。"""
    src = _senate()
    fn = src[src.find("function senateResultMarkColor(item)"):
             src.find("function senateResultMarkColor(item)") + 400]
    assert "root.voteResultFor(item.id)" in fn, "senateResultMarkColor 须含 voteResultFor() 回退（FC-C35）"
    assert "#B3261E" in fn and "theme.statusSuccess" in fn


def test_r5_source_shared_result_mark_unchanged():
    """FC-C35 守恒：共享 `resultMark()`/`resultMarkColor()` **未改**
    （③ 否决面板仍需 `vetoed → ✗`；无第二表决红叉源）。"""
    src = _senate()
    assert '(item.result === "rejected" || item.result === "vetoed") ? "\\u2717" : "\\u2713"' in src
    assert '? "#B3261E" : theme.statusSuccess' in src


def test_r5_source_no_emoji_in_changed_surfaces():
    """硬约束：② 变更面不得引入 emoji 转义（\\u274C / \\u2705 / VS16）。"""
    src = _senate()
    idx = src.find(IDENTITY_ANCHOR)
    block = src[idx:src.find("root.supportRateText(", idx)]
    for tok in EMOJI_ESCAPES:
        assert tok not in block, f"② 变更面不得含 emoji 转义 {tok}"


# ---------------------------------------------------------------------------
# FC-C37 —— RENDER_AUTOMATED 步骤相对照（离屏生产链；真实 Main.qml；DIRECT_PRODUCTION）
# ---------------------------------------------------------------------------

def _panel2_rows(stage_root, labels):
    """② 表决行 → [(label, identity_text, 同行 CheckBox(可 None), 行卡)]（复用 R 定位器）。"""
    out = []
    for lbl in labels:
        if not lbl:
            continue
        it, cb, card = R._panel2_identity_and_checkbox(stage_root, lbl)
        if it is not None:
            out.append((lbl, it, cb, card))
    return out


def test_r5_render_tribune_veto_panel2_glyph_shown_and_no_checkbox():
    """FC-C37(1)（★关键）：`tribune_veto` 帧 ② 每行**显示结果字形**（`vote_results` 口径：
    passed→✓，非通过→✗，无数据→空白）**且 ② 行无勾选框**（FC-C36）。1280×720 及更大视口。"""
    rows = []
    for (w, h, tag) in ((1440, 900, "1440x900"), (1280, 720, "1280x720")):
        store, _s, _v, _ids = R._senate_veto_store_with_selection()
        assert store.senateCurrentStep == "tribune_veto", store.senateCurrentStep
        by_label = {r.get("label"): r for r in (store.senateSubmittedProposals or [])}
        labels = [l for l in by_label if l]
        engine, _ = R._create_engine(store)
        name = f"group-c-g7testr5-tribune-veto-panel2-{tag}.png"
        png = os.path.join(EVIDENCE_BASE, _EVID_DIR, name)
        cap = R._capture(engine, png, w, h)
        rows.append(R._emit(_EVID_DIR, name, cap,
                            "create_gui_prototype_session(senate)+doSubmitSenateProposals+doSubmitSenateVotes",
                            "tribune_veto", (w, h)))
        window = engine.rootObjects()[0]
        _root, stage_root = R._find_stage_root(window)
        assert stage_root is not None, f"须定位 SenateStage 根（{tag}）"
        p2 = _panel2_rows(stage_root, labels)
        assert p2, f"须定位 ② 表决行（{tag}）"
        shown = 0
        for label, identity, cb, _card in p2:
            row = by_label[label]
            # FC-C36：非输入态 ② 行不得显示勾选框
            assert cb is None or not cb.property("visible"), \
                f"tribune_veto 步 ② 行不得显示勾选框（FC-C36，{tag}）: {label!r}"
            # FC-C35：字形 = vote_results 口径（results 步前即显）
            exp = R._panel2_expected_glyph(store, row)
            t, glyph = R._row_result_glyph(identity)
            if exp == "":
                assert glyph in (None, ""), \
                    f"无表决数据行须无字形（{tag}）: {glyph!r} label={label!r}"
                continue
            assert t is not None and glyph == exp, \
                f"tribune_veto 步 ② 须显结果字形 == 元老院表决口径（FC-C35，{tag}）: " \
                f"got={glyph!r} exp={exp!r} label={label!r}"
            shown += 1
        assert shown >= 1, f"tribune_veto 步 须至少 1 行 ② 显结果字形（FC-C35，{tag}）"
        R._teardown(engine)
    with open(os.path.join(EVIDENCE_BASE, _EVID_DIR, "g7testr5-tribune-veto-manifest.json"),
              "w", encoding="utf-8") as fh:
        json.dump({"schema": "wpj-groupc-render-manifest/v1", "rows": rows}, fh,
                  ensure_ascii=False, indent=2)
        fh.write("\n")
    assert all(r["capture_ok"] for r in rows), rows


def test_r5_render_results_panel2_vetoed_green_and_panel3_red():
    """FC-C37(2)：`results` 帧 ② 同规则显字形；**`vetoed` 行 ② 显绿 ✓（≠ ✗）**（`veto` 不改写 ②）；
    **③ 显红 ✗**（`resultMark`，共享谓词未动）。1280×720 及更大视口。"""
    rows = []
    for (w, h, tag) in ((1440, 900, "1440x900"), (1280, 720, "1280x720")):
        store, _s, _v, _ids = R._senate_results_store(veto_first=True)
        assert store.senateCurrentStep == "results", store.senateCurrentStep
        by_label = {r.get("label"): r for r in (store.senateSubmittedProposals or [])}
        labels = [l for l in by_label if l]
        assert any(r.get("result") == "vetoed" for r in by_label.values()), \
            f"须有 vetoed 行（{tag}）"
        engine, _ = R._create_engine(store)
        name = f"group-c-g7testr5-results-panel2-{tag}.png"
        png = os.path.join(EVIDENCE_BASE, _EVID_DIR, name)
        cap = R._capture(engine, png, w, h)
        rows.append(R._emit(_EVID_DIR, name, cap,
                            "create_gui_prototype_session(senate)+doSubmitSenateProposals"
                            "+doSubmitSenateVotes+doSubmitSenateVetoes(veto_first)",
                            "results", (w, h)))
        window = engine.rootObjects()[0]
        _root, stage_root = R._find_stage_root(window)
        assert stage_root is not None, f"须定位 SenateStage 根（{tag}）"
        p2 = _panel2_rows(stage_root, labels)
        assert p2, f"须定位 ② 表决行（{tag}）"
        vetoed_seen = False
        for label, identity, cb, _card in p2:
            row = by_label[label]
            assert cb is None or not cb.property("visible"), \
                f"results 步 ② 行不得显示勾选框（FC-C36，{tag}）: {label!r}"
            exp = R._panel2_expected_glyph(store, row)
            t, glyph = R._row_result_glyph(identity)
            if exp == "":
                assert glyph in (None, ""), f"无数据行须无字形（{tag}）: {glyph!r}"
                continue
            assert t is not None and glyph == exp, \
                f"results 步 ② 字形须 == senateResultMark(.result)（{tag}）: " \
                f"got={glyph!r} exp={exp!r} result={row.get('result')!r}"
            if row.get("result") == "vetoed":
                vetoed_seen = True
                assert glyph == "\u2713", f"被否决提案在 ② 须显绿 ✓（非 ✗）（FC-C32，{tag}）: {glyph!r}"
                px = R._count_color_near(png, t, (0x22, 0x8B, 0x22), window=window, tol=60)
                assert px and px > 0, f"② 绿 ✓ 须见绿系像素（{tag}）: {px}"
        assert vetoed_seen, f"须在 ② 定位到 vetoed 行且显绿 ✓（{tag}）"
        # ③ results 态：显红 ✗（共享 resultMark；无勾选框）
        red_texts = []
        for it in R._all_items(stage_root):
            try:
                if "Text" not in it.metaObject().className() or not it.property("visible"):
                    continue
                if (it.property("text") or "") == "\u2717" and \
                        R._rgb(it.property("color")) == (0xB3, 0x26, 0x1E):
                    red_texts.append(it)
            except Exception:
                continue
        assert red_texts, f"③ results 态须显红 ✗（共享 resultMark，{tag}）"
        R._teardown(engine)
    with open(os.path.join(EVIDENCE_BASE, _EVID_DIR, "g7testr5-results-manifest.json"),
              "w", encoding="utf-8") as fh:
        json.dump({"schema": "wpj-groupc-render-manifest/v1", "rows": rows}, fh,
                  ensure_ascii=False, indent=2)
        fh.write("\n")
    assert all(r["capture_ok"] for r in rows), rows


def test_r5_render_panel3_tribune_veto_keeps_checkbox():
    """FC-C37(2)：③ `tribune_veto` 帧**保留勾选框**（提交否决前；`FC-C36` 仅 ②）。"""
    for (w, h, tag) in ((1440, 900, "1440x900"), (1280, 720, "1280x720")):
        store = R._senate_veto_store_with_selection()[0]
        engine, _ = R._create_engine(store)
        name = f"group-c-g7testr5-panel3-tribune-veto-{tag}.png"
        cap = R._capture(engine, os.path.join(EVIDENCE_BASE, _EVID_DIR, name), w, h)
        assert cap and cap not in ("timeout",), f"截图须成功（{tag}）: {cap}"
        window = engine.rootObjects()[0]
        _root, stage_root = R._find_stage_root(window)
        assert stage_root is not None
        vs = R._veto_checkbox_items(stage_root)
        assert vs, f"③ tribune_veto 帧须保留可见勾选框（FC-C37，{tag}）"
        R._teardown(engine)
    assert True


def test_r5_render_geometry_1280x720_and_larger():
    """FC-C37(5)：senate_vote 步于 1280×720 与更大视口渲染成功、窗口/阶段根几何非零（非回归）。"""
    for (w, h, tag) in ((1440, 900, "1440x900"), (1280, 720, "1280x720")):
        store = R._senate_vote_store_with_long_proposal()[0]
        assert store.senateCurrentStep == "senate_vote"
        engine, _ = R._create_engine(store)
        name = f"group-c-g7testr5-geometry-{tag}.png"
        cap = R._capture(engine, os.path.join(EVIDENCE_BASE, _EVID_DIR, name), w, h)
        assert cap and cap not in ("timeout",), f"截图须成功（{tag}）: {cap}"
        window = engine.rootObjects()[0]
        assert (window.width() or 0) > 0 and (window.height() or 0) > 0, f"窗口几何须非零（{tag}）"
        _root, stage_root = R._find_stage_root(window)
        assert stage_root is not None and (stage_root.width() or 0) > 0, f"阶段根几何须非零（{tag}）"
        R._teardown(engine)
    assert True


def test_r5_render_live_headed_recheck_recorded():
    """FC-C37(4) 有头/窗口化 live 复验如实登记：本 DA 运行环境为**无头 WSL**（无 DISPLAY；
    测试进程强制 offscreen）⇒ **NOT_APPLICABLE（不伪造）**；以离屏 RENDER_AUTOMATED 替代。
    注意：离屏 RENDER 的 ② 行样本为 land 提案；「含战争行」的有头复验待有头环境补做。"""
    display = os.environ.get("DISPLAY")
    plat = os.environ.get("QT_QPA_PLATFORM")
    out = os.path.join(EVIDENCE_BASE, _EVID_DIR, "g7testr5-live-headed.runtime.json")
    os.makedirs(os.path.dirname(out), exist_ok=True)
    record = {
        "schema": "wpj-groupc-live-headed/v1",
        "requested": "有头/窗口化 live 复验（真实 app.py；非 offscreen；含战争行 ② 勾选框隐藏）",
        "display": display,
        "QT_QPA_PLATFORM_env": plat,
        "status": "NOT_APPLICABLE_HEADLESS",
        "reason": ("本 DA 运行环境为无头 WSL（无可用 DISPLAY；测试进程强制 QT_QPA_PLATFORM=offscreen）；"
                   "无法进行有头实机 live 复验。已以离屏 RENDER_AUTOMATED（真实 Main.qml + 真实生产链"
                   " create_gui_prototype_session）替代并如实登记；② war 行样本另见 Group C 既有 slice。"),
    }
    with open(out, "w", encoding="utf-8") as fh:
        json.dump(record, fh, ensure_ascii=False, indent=2)
        fh.write("\n")
    assert not display, f"若有 DISPLAY 则应做有头复验（不得伪报）: {display}"


if __name__ == "__main__":
    import pytest
    raise SystemExit(pytest.main([__file__, "-v", "-s"]))
