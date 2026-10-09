# src/tests/test_gui/test_wpj_groupc_g7testr6.py
"""WP-J Group C G7 Test R6 Delta（delta v2.3 / FC-C38 + FC-C39 + FC-C40）— 源码/结构 + DATA + RENDER。

Owner 2026-10-09 16:27 裁 **C1**（「两个问题一起修复」）。冻结契约（权威）：
`02-sa-design/GroupC/WP-J-GroupC-R6R7Delta-v2.3-2026-10-09.md`（`FC-C38..C43`）。

- **FC-C38**：③ 保民官否决面板**不渲染支持率**（删 `SenateStage.qml` ③ 支持率 `Text` 整块；
  **仅 ③**；② 支持率 `Text` 保留；`supportRateText()`/`voteResultFor()` 保留）。
- **FC-C39**：② 支持率反映**元老院表决**（与否决无关）；被否决提案**保留真 tally** ——
  `political_system.calculate_vote_result` 否决短路清零（L609–616）解除：vetoed 仍走派系循环，
  仅 `passed=False`/`vetoed=True`；返回 dict **键集** / `passed`·`vetoed` 布尔 / `veto_candidate_ids`
  语义**不变**；② 结果字形回退加 `!vr.vetoed` 门（保 `FC-C32`『禁第二红叉源』）。
- **FC-C40**：证据链（② 被否决 land 行显「未通过 · 支持率 X%」**非「—」** + 字形 **✓**；
  ③ 无「支持率」；有头 live；几何 1280×720+）。

证据：`DATA(PRODUCTION_CHAIN)` + `RENDER_AUTOMATED`；Route = `DIRECT_PRODUCTION`；SO = NO / 不建 fixture。
"""
import json
import os
import re
import sys

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
os.environ.setdefault("PYTHONUTF8", "1")
os.environ.setdefault("PYTHONUNBUFFERED", "1")

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(__file__))))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

SENATE_QML = os.path.join(PROJECT_ROOT, "src", "ui", "gui", "qml", "stages", "SenateStage.qml")
POLITICAL_PY = os.path.join(PROJECT_ROOT, "src", "core", "systems", "political_system.py")

EVIDENCE_BASE = (
    "/mnt/e/OpenClaw/Projects/EOR/workspace/EOR20260821-01 GUI-BETA-R1"
    "/WP-J_Player-Visible-Feedback-and-Actionability/03-da-evidence/GroupC"
)
_EVID_DIR = "Group-C-G7TestR6Delta"

from src.api import senate_api  # noqa: E402
from src.tests.test_gui import test_wpj_groupc_render_evidence as R  # noqa: E402
from src.tests.test_api import test_wpfr1_senate_vote_results as W  # noqa: E402

DOT = "\u00b7"          # ·
RATE_PAT = re.compile(r"\u672a\u901a\u8fc7 \u00b7 \u652f\u6301\u7387 (\d+)%")  # 未通过 · 支持率 X%


def _senate():
    return open(SENATE_QML, encoding="utf-8").read()


def _political():
    return open(POLITICAL_PY, encoding="utf-8").read()


def _texts_with(root, needle):
    out = []
    for it in R._all_items(root):
        try:
            if "Text" not in it.metaObject().className() or not it.property("visible"):
                continue
            if needle in (it.property("text") or ""):
                out.append(it)
        except Exception:
            continue
    return out


def _panel3_cards_via_visible_checkbox(stage_root):
    """③ 行卡（tribune_veto 帧：③ 勾选框可见）→ [(checkbox, 卡)]。"""
    out = []
    for cb, _ind in R._veto_checkbox_items(stage_root):
        card = R._nearest_rect_ancestor_by_rgb(cb, (255, 246, 230))
        if card is not None:
            out.append((cb, card))
    return out


# ---------------------------------------------------------------------------
# FC-C38 —— 源码/结构断言（③ 删支持率；② 保留；helpers 保留）
# ---------------------------------------------------------------------------

def test_r6_source_panel3_support_rate_removed_panel2_kept():
    """FC-C38(1)(3)：③ 支持率 `Text` 删除 ⇒ `supportRateText(` 全文件仅剩 **1** 处调用（②）。"""
    src = _senate()
    assert src.count("root.supportRateText(") == 1, \
        "③ 支持率 Text 须删除（仅 ② 保留一处 supportRateText 调用；FC-C38）"
    # ② 支持率 Text 仍在（门 = voteResultFor(...) !== null）
    assert "visible: root.voteResultFor(modelData.id) !== null" in src, \
        "② 支持率 Text（`voteResultFor !== null` 门）须保留（FC-C38(2)）"


def test_r6_source_support_rate_helpers_retained_and_panel3_core_intact():
    """FC-C38(2)(4)：`supportRateText()`/`voteResultFor()` 保留；③ 结果字形/身份/明细不动。"""
    src = _senate()
    assert "function supportRateText(vr)" in src, "supportRateText() 须保留（② 仍用；FC-C38(4)）"
    assert "function voteResultFor(proposalId)" in src, "voteResultFor() 须保留（② 仍用）"
    assert "text: root.resultMark(modelData)" in src, "③ 结果字形（共享 resultMark）须保留（FC-C38(2)）"


# ---------------------------------------------------------------------------
# FC-C39 —— 源码/结构断言（C1 core + ② 字形回退协同）
# ---------------------------------------------------------------------------

def test_r6_source_calculate_vote_result_veto_not_zeroed():
    """FC-C39(1)(2)：`calculate_vote_result` 否决**不再短路清零** —— 以 `is_vetoed` 标记，
    仍走派系循环算真 tally；仅强制 `passed=False`/`vetoed=True`。"""
    src = _political()
    fn = src[src.find("    def calculate_vote_result("):]
    fn = fn[:fn.find("    def execute_passed_proposal(")]
    assert "is_vetoed = proposal_id in vetoes" in fn, "C1：须以 is_vetoed 标记（不提前 return 零值）"
    assert "if proposal_id in vetoes:\n            return {" not in fn, "C1：否决短路清零须解除"
    assert '"vetoed": is_vetoed' in fn, "C1：vetoed 布尔由 is_vetoed 派生（值语义不变）"
    assert "if is_vetoed:" in fn and "passed = False" in fn, "C1：vetoed ⇒ passed=False（布尔不变）"
    # 返回 dict 键集守恒（6 键）
    for key in ('"proposal"', '"passed"', '"vetoed"', '"support_influence"',
                '"oppose_influence"', '"total_influence"'):
        assert key in fn, f"返回 dict 键 {key} 须守恒"


def test_r6_source_panel2_glyph_fallback_has_vetoed_gate():
    """FC-C39(4)：② 字形回退分支（`senateResultMark`/`senateResultMarkColor`）须含 `!vr.vetoed` 门
    （保 `FC-C32` 禁第二红叉源）。"""
    src = _senate()
    mark = src[src.find("function senateResultMark(item)"):src.find("function senateResultMarkColor(item)")]
    color = src[src.find("function senateResultMarkColor(item)"):
                src.find("function senateResultMarkColor(item)") + 700]
    assert "!vr.vetoed" in mark, "C1 协同：② 字形回退须加 `!vr.vetoed` 门（FC-C39(4)）"
    assert "!vr.vetoed" in color, "C1 协同：② 字形回退色分支须加 `!vr.vetoed` 门（FC-C39(4)）"
    # 主谓词（item.result 口径）守恒
    assert 'item.result === "vetoed"' in mark


# ---------------------------------------------------------------------------
# FC-C39 —— DATA（PRODUCTION_CHAIN）：被否决提案保留真 tally；键集/布尔不变
# ---------------------------------------------------------------------------

def test_r6_data_vetoed_row_keeps_true_tally_and_dto_keys():
    """FC-C39(1)(2)：`resolve_senate` 全链 —— 被否决提案 `vote_results` 行 tally = 真实值（>0），
    键集守恒，`passed`/`vetoed` 布尔不变。"""
    state = W._build_state()
    pid1, pid2, pid3 = W._propose_lands(state, "player1", [50, 30, 20])
    W._vote_all_humans(state, [pid1, pid2, pid3])
    state._current_player_id = "player2"
    assert senate_api.veto(state, "player2", [pid3])["success"]
    resolved = senate_api.resolve_senate(state)
    assert resolved["success"], resolved.get("message")
    by_id = {r["proposal_id"]: r for r in resolved["data"]["vote_results"]}
    row = by_id[pid3]
    assert set(row) == {"proposal_id", "support_influence", "oppose_influence",
                        "total_influence", "passed", "vetoed"}, sorted(row)
    assert row["vetoed"] is True and row["passed"] is False
    assert row["total_influence"] > 0, "C1：被否决提案须保留真 tally（非 0）"
    assert row["support_influence"] + row["oppose_influence"] == row["total_influence"]
    # 与非否决提案同键集（口径一致）
    for pid in (pid1, pid2):
        assert set(by_id[pid]) == set(row)
    # 被否决提案仍进 vetoed_proposals（布尔/成员判定守恒）
    assert pid3 in (resolved["data"].get("vetoed_proposals") or [])


def test_r6_data_vetoed_tally_matches_senate_vote_projection():
    """FC-C39(1)：被否决提案 tally 与「未否决同表决」口径一致（真值是同一派系循环产出）。
    直连 `PoliticalSystem.calculate_vote_result` 对比 vetoed/非 vetoed 两态。"""
    state = W._build_state()
    pid1, pid2, pid3 = W._propose_lands(state, "player1", [50, 30, 20])
    W._vote_all_humans(state, [pid1, pid2, pid3])
    from src.core.systems.political_system import PoliticalSystem
    ps = PoliticalSystem(state)
    state._current_player_id = "player2"
    senate_api.veto(state, "player2", [pid3])
    proposal3 = next(p for p in state.get_senate_proposals() if p["id"] == pid3)
    r = ps.calculate_vote_result(proposal3)
    assert r["vetoed"] is True and r["passed"] is False
    assert r["total_influence"] > 0 and r["support_influence"] + r["oppose_influence"] == r["total_influence"]


# ---------------------------------------------------------------------------
# FC-C40 —— RENDER_AUTOMATED（② 被否决 land 行 真率 + 字形 ✓；③ 无「支持率」）
# ---------------------------------------------------------------------------

def test_r6_render_results_panel2_vetoed_rate_and_glyph():
    """FC-C40(1)：`results` 帧 ② 被否决 land 行显「未通过 · 支持率 X%」（X>0，非「—」）
    **且字形 = ✓（非 ✗）**；③ **不**渲染「支持率」。1280×720 及更大视口。"""
    rows = []
    for (w, h, tag) in ((1440, 900, "1440x900"), (1280, 720, "1280x720")):
        store, _state, _viewer, _ids = R._senate_results_store(veto_first=True)
        assert store.senateCurrentStep == "results", store.senateCurrentStep
        by_label = {r.get("label"): r for r in (store.senateSubmittedProposals or [])}
        labels = [l for l in by_label if l]
        engine, _ = R._create_engine(store)
        name = f"group-c-g7testr6-results-{tag}.png"
        png = os.path.join(EVIDENCE_BASE, _EVID_DIR, name)
        cap = R._capture(engine, png, w, h)
        rows.append(R._emit(
            _EVID_DIR, name, cap,
            "create_gui_prototype_session(senate)+doSubmitSenateProposals"
            "+doSubmitSenateVotes+doSubmitSenateVetoes(veto_first)",
            "results", (w, h)))
        window = engine.rootObjects()[0]
        _root, stage_root = R._find_stage_root(window)
        assert stage_root is not None, f"须定位 SenateStage 根（{tag}）"
        p2 = R._panel2_rows(stage_root, labels)
        assert p2, f"须定位 ② 表决行（{tag}）"
        vetoed_seen = False
        for label, identity, _cb, card in p2:
            row = by_label.get(label)
            if row is None or row.get("result") != "vetoed":
                continue
            vetoed_seen = True
            t, glyph = R._row_result_glyph(identity)
            assert t is not None and glyph == "\u2713", \
                f"② 被否决行字形须 = ✓（非 ✗）（FC-C39/C32，{tag}）: {glyph!r}"
            rates = [x.property("text") for x in _texts_with(card, "\u652f\u6301\u7387")]
            assert rates, f"② 被否决 land 行须显支持率（{tag}）"
            m = next((RATE_PAT.search(rt or "") for rt in rates if RATE_PAT.search(rt or "")), None)
            assert m is not None, f"② 被否决行须显「未通过 · 支持率 X%」（{tag}）: {rates}"
            assert int(m.group(1)) > 0, f"X 须 > 0（FC-C39(3)，非「—」）（{tag}）: {m.group(0)}"
            for rt in rates:
                assert "\u2014" not in (rt or ""), f"② 被否决行不得显「—」（{tag}）: {rt!r}"
        assert vetoed_seen, f"须在 ② 定位到 vetoed land 行（{tag}）"
        # ③ 不渲染「支持率」：全部「支持率」文本须属 ② 卡（FC-C38）
        p2_cards = {id(c[3]) for c in p2}
        for x in _texts_with(stage_root, "\u652f\u6301\u7387"):
            cur, owner = x, None
            while cur is not None:
                if id(cur) in p2_cards:
                    owner = cur
                    break
                cur = R._parent_item(cur)
            assert owner is not None, f"③ 不得渲染「支持率」（FC-C38，{tag}）"
        R._teardown(engine)
    with open(os.path.join(EVIDENCE_BASE, _EVID_DIR, "g7testr6-results-manifest.json"),
              "w", encoding="utf-8") as fh:
        json.dump({"schema": "wpj-groupc-render-manifest/v1", "rows": rows}, fh,
                  ensure_ascii=False, indent=2)
        fh.write("\n")
    assert all(r["capture_ok"] for r in rows), rows


def test_r6_render_panel3_tribune_veto_no_support_rate():
    """FC-C40(2)：③ `tribune_veto` 帧任意行**不渲染**「支持率」（③ 行卡内无「支持率」文本）。"""
    for (w, h, tag) in ((1440, 900, "1440x900"), (1280, 720, "1280x720")):
        store = R._senate_veto_store_with_selection()[0]
        assert store.senateCurrentStep == "tribune_veto", store.senateCurrentStep
        engine, _ = R._create_engine(store)
        name = f"group-c-g7testr6-panel3-tribune-veto-{tag}.png"
        cap = R._capture(engine, os.path.join(EVIDENCE_BASE, _EVID_DIR, name), w, h)
        assert cap and cap not in ("timeout",), f"截图须成功（{tag}）: {cap}"
        window = engine.rootObjects()[0]
        _root, stage_root = R._find_stage_root(window)
        assert stage_root is not None
        cards = _panel3_cards_via_visible_checkbox(stage_root)
        assert cards, f"③ tribune_veto 帧须有可见行卡（FC-C38，{tag}）"
        for _cb, card in cards:
            assert not _texts_with(card, "\u652f\u6301\u7387"), \
                f"③ 行不得渲染「支持率」（FC-C38，{tag}）"
        R._teardown(engine)
    assert True


def test_r6_render_geometry_1280x720_and_larger():
    """FC-C40(5)：`results` 帧于 1280×720 与更大视口渲染成功、窗口/阶段根几何非零（非回归）。"""
    for (w, h, tag) in ((1440, 900, "1440x900"), (1280, 720, "1280x720")):
        store = R._senate_results_store(veto_first=True)[0]
        engine, _ = R._create_engine(store)
        name = f"group-c-g7testr6-geometry-{tag}.png"
        cap = R._capture(engine, os.path.join(EVIDENCE_BASE, _EVID_DIR, name), w, h)
        assert cap and cap not in ("timeout",), f"截图须成功（{tag}）: {cap}"
        window = engine.rootObjects()[0]
        assert (window.width() or 0) > 0 and (window.height() or 0) > 0, f"窗口几何须非零（{tag}）"
        _root, stage_root = R._find_stage_root(window)
        assert stage_root is not None and (stage_root.width() or 0) > 0, f"阶段根几何须非零（{tag}）"
        R._teardown(engine)
    assert True


def test_r6_render_live_headed_recheck_recorded():
    """FC-C40(4) 有头/窗口化 live 复验如实登记：本 DA 运行环境为**无头 WSL**（无 DISPLAY；
    测试进程强制 offscreen）⇒ **NOT_APPLICABLE（不伪造）**；以离屏 RENDER_AUTOMATED 替代。
    注：离屏样本为 land 提案；「含战争行」的有头复验待有头环境补做。"""
    display = os.environ.get("DISPLAY")
    plat = os.environ.get("QT_QPA_PLATFORM")
    out = os.path.join(EVIDENCE_BASE, _EVID_DIR, "g7testr6-live-headed.runtime.json")
    os.makedirs(os.path.dirname(out), exist_ok=True)
    record = {
        "schema": "wpj-groupc-live-headed/v1",
        "requested": "有头/窗口化 live 复验（真实 app.py；非 offscreen；含战争行 + 被否决 land 行）",
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
