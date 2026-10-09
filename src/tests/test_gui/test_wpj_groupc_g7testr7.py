# src/tests/test_gui/test_wpj_groupc_g7testr7.py
"""WP-J Group C G7 Test R7 Delta（delta v2.3 / FC-C41 + FC-C42 + FC-C43）— 源码/结构 + DATA + RENDER。

Owner「两个问题一起修复」；R7 = ② 元老院表决选择控件接线。冻结契约（权威）：
`02-sa-design/GroupC/WP-J-GroupC-R6R7Delta-v2.3-2026-10-09.md`（`FC-C41..C43`）。

- **FC-C41**：② `CheckBox{id:proposalVoteCheck}.checked` 由常量 `true` → **绑定 ② 专属选择集**
  （`root.hasSelectedSenateVote(Number(modelData.id))`）+ 新增 `onToggled` 写回；新增根属性
  `selectedSenateVoteIds: []` + `hasSelectedSenateVote` + `setSenateVoteSelected`；**随会期重置**；
  **默认未勾选**；平台默认指示器守恒（禁覆写 `indicator`）。
- **FC-C42**：`session_store.doSubmitSenateVotes` 删硬编码全赞成 → `votes = [pid in agree_ids ...]`；
  ② 提交按钮传 ② 选择；**向后兼容签名** `agree_ids=None`，None ⇒ **非「静默全赞成」**（全反对）。
- **FC-C43**：证据链（取消勾选 ⇒ 人类票 = 反对；日志**双证** + 结果正确；默认/全选对照；有头 live；几何）。

证据：`DATA(PRODUCTION_CHAIN)` + `RENDER_AUTOMATED`；Route = `DIRECT_PRODUCTION`；SO = NO / 不建 fixture。
"""
import json
import os
import sys

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
os.environ.setdefault("PYTHONUTF8", "1")
os.environ.setdefault("PYTHONUNBUFFERED", "1")

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(__file__))))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

SENATE_QML = os.path.join(PROJECT_ROOT, "src", "ui", "gui", "qml", "stages", "SenateStage.qml")
STORE_PY = os.path.join(PROJECT_ROOT, "src", "ui", "gui", "session_store.py")

EVIDENCE_BASE = (
    "/mnt/e/OpenClaw/Projects/EOR/workspace/EOR20260821-01 GUI-BETA-R1"
    "/WP-J_Player-Visible-Feedback-and-Actionability/03-da-evidence/GroupC"
)
_EVID_DIR = "Group-C-G7TestR7Delta"

from src.api import session_api  # noqa: E402
from src.ui.gui.session_store import GuiSessionStore  # noqa: E402
from src.tests.test_gui import test_wpj_groupc_render_evidence as R  # noqa: E402


def _senate():
    return open(SENATE_QML, encoding="utf-8").read()


def _store():
    return open(STORE_PY, encoding="utf-8").read()


# ---------------------------------------------------------------------------
# FC-C41 / FC-C42 —— 源码/结构断言
# ---------------------------------------------------------------------------

def test_r7_source_panel2_selection_set_and_helpers():
    """FC-C41(1)：② 专属选择集 + 读写函数存在（仿 ③）。"""
    src = _senate()
    assert "property var selectedSenateVoteIds: []" in src, "② 专属选择集须存在（FC-C41(1)）"
    assert "function hasSelectedSenateVote(id)" in src, "hasSelectedSenateVote 须存在（FC-C41(1)）"
    assert "function setSenateVoteSelected(id, checked)" in src, "setSenateVoteSelected 须存在（FC-C41(1)）"
    fn = src[src.find("function hasSelectedSenateVote(id)"):
             src.find("function setSenateVoteSelected(id, checked)")]
    assert "selectedSenateVoteIds.indexOf(id) >= 0" in fn, "hasSelectedSenateVote 谓词（FC-C41(1)）"


def test_r7_source_panel2_checkbox_binds_selection_and_toggle():
    """FC-C41(2)：② 勾选框 `checked` 绑定选择集 + `onToggled` 写回；不再常量 `checked: true`；
    平台默认指示器守恒（禁覆写 indicator）。"""
    src = _senate()
    idx = src.find("id: proposalVoteCheck")
    assert idx >= 0, "须定位 ② CheckBox（FC-C41）"
    seg = src[idx:idx + 900]
    assert "checked: root.hasSelectedSenateVote(Number(modelData.id))" in seg, \
        "checked 须绑定 ② 专属选择集（FC-C41(2)）"
    assert "onToggled: root.setSenateVoteSelected(Number(modelData.id), checked)" in seg, \
        "须新增 onToggled 写回选择集（FC-C41(2)）"
    assert "checked: true" not in seg, "不得残留常量 `checked: true`（FC-C41(2)）"
    assert "indicator:" not in seg, "禁覆写 indicator（平台默认；FC-C41(2)）"


def test_r7_source_panel2_submit_button_passes_selection():
    """FC-C42(3)：② 提交按钮把 ② 选择传给 store（与 ③ 同构）。"""
    src = _senate()
    assert "onTriggered: sessionStore.doSubmitSenateVotes(root.selectedSenateVoteIds)" in src, \
        "② 提交按钮须传 root.selectedSenateVoteIds（FC-C42(3)）"


def test_r7_source_selection_reset_on_session_change():
    """FC-C41(4)：选择集**随会期重置** —— `syncSenateVoteSelection()` 存在且挂于
    `onSenateViewChanged`（新会期 id 集变化即清空；OBS-R7-3）。"""
    src = _senate()
    assert "function syncSenateVoteSelection()" in src, "syncSenateVoteSelection 须存在（FC-C41(4)）"
    conn = src[src.find("function onSenateViewChanged()"):]
    conn = conn[:conn.find("function expandCheckedBills") if "function expandCheckedBills" in conn else 2000]
    assert "root.syncSenateVoteSelection()" in conn, \
        "syncSenateVoteSelection 须挂于 onSenateViewChanged（FC-C41(4)）"
    fn = src[src.find("function syncSenateVoteSelection()"):]
    fn = fn[:fn.find("function ", 10)]
    assert "selectedSenateVoteIds = []" in fn, "会期变化须清空选择集（FC-C41(4)）"


def test_r7_source_store_backcompat_signature_and_no_hardcoded_all_true():
    """FC-C42(1)(4)：`doSubmitSenateVotes(self, agree_ids=None)`；不含 `[True for` 硬编码；
    `votes` 由选择派生。"""
    src = _store()
    idx = src.find("    def doSubmitSenateVotes(")
    assert idx >= 0
    fn = src[idx:idx + 1800]
    assert "def doSubmitSenateVotes(self, agree_ids=None)" in fn, \
        "向后兼容签名 `agree_ids=None`（FC-C42(4)）"
    assert "[True for" not in fn, "硬编码全赞成须删除（FC-C42(1)）"
    assert "votes = [pid in" in fn, "votes 须由选择集派生（FC-C42(2)）"
    assert '@Slot("QVariant", result=dict)' in src[:idx][-400:], "槽须可接收 QML 参数（FC-C42(3)）"


# ---------------------------------------------------------------------------
# FC-C42 / FC-C43 —— DATA（PRODUCTION_CHAIN）：选择派生 + 日志双证 + 结果正确 + 对照
# ---------------------------------------------------------------------------

class _CaptureHandler:
    """轻量捕获 state.log_event(message, extra)（不依赖 logging 配置；实例级替换）。"""

    def __init__(self, state):
        self.records = []
        self._orig = state.log_event
        self._state = state

    def __enter__(self):
        outer = self

        def _rec(message, level=None, extra=None):
            outer.records.append((message, extra or {}))
            if level is None:
                return outer._orig(message, extra=extra)
            return outer._orig(message, level=level, extra=extra)

        self._state.log_event = _rec
        return self

    def __exit__(self, *exc):
        self._state.log_event = self._orig
        return False

    def has(self, pred):
        return any(pred(m, e) for (m, e) in self.records)


def _session_with_two_lands():
    """真实生产链：prototype session → viewer 执政官 → 提交 2 条 land；预录非 viewer 支持票
    （保证通过确定性）。返回 (store, state, viewer, viewer_player_id, pids)。"""
    result = session_api.create_gui_prototype_session(start_phase="senate")
    assert result["success"], result.get("message")
    state = result["data"]["state"]
    player_id = result["data"]["human_players"][0]
    viewer = state.get_player(player_id)
    living = list(state.get_living_members())
    consul = next(fig for fig in living if fig.faction_id == viewer.faction_id)
    consul.office = "consul"
    # 给 viewer 派系一个保民官 ⇒ veto_control_mode=HUMAN ⇒ 提交后停在 tribune_veto（投票账不被
    # NONE 自动结算清空，供 DATA 断言读取）。
    tribune = next(fig for fig in living
                   if fig.faction_id == viewer.faction_id and fig is not consul)
    tribune.office = "tribune"
    store = GuiSessionStore(state)
    store.initialize(player_id)
    store.selectPhase("senate")
    assert store.doSubmitSenateProposals([
        {"type": "land", "params": {"act_type": "sale", "amount_C": 300}},
        {"type": "land", "params": {"act_type": "distribution", "amount_C": 300}},
    ])["success"]
    for p in state.get_all_players():
        if p.player_id != player_id:
            for prop in state.get_senate_proposals():
                state.record_senate_vote(p.player_id, prop["id"], True)
    pids = [p["id"] for p in state.get_senate_proposals()]
    assert len(pids) == 2
    return store, state, viewer, player_id, pids


def test_r7_data_submit_derives_votes_from_selection():
    """FC-C42(2)：勾选 pids[0] ⇒ votes True；未勾选 pids[1] ⇒ votes False。"""
    store, state, _viewer, pid_viewer, pids = _session_with_two_lands()
    fb = store.doSubmitSenateVotes([pids[0]])
    assert fb["success"], fb
    votes = state.get_senate_votes_copy().get(pid_viewer, {})
    assert votes.get(pids[0]) is True, f"勾选 ⇒ 赞成（FC-C42）：{votes}"
    assert votes.get(pids[1]) is False, f"未勾选 ⇒ 反对（FC-C42）：{votes}"


def test_r7_data_no_arg_submit_is_not_all_yes():
    """FC-C42(4)：无参调用 ⇒ `None` ⇒ **非静默全赞成** ⇒ 全反对（原则）。"""
    store, state, _viewer, pid_viewer, pids = _session_with_two_lands()
    fb = store.doSubmitSenateVotes()
    assert fb["success"], fb
    votes = state.get_senate_votes_copy().get(pid_viewer, {})
    assert all(votes.get(pid) is False for pid in pids), \
        f"无参 ⇒ 全反对（不静默全赞成；FC-C42(4)）：{votes}"


def test_r7_data_default_vs_all_selected_contrast():
    """FC-C43(3)：默认（全不选）⇒ 全反对；全选 ⇒ 全赞成（对照）。"""
    s1, st1, _v1, pv1, pids1 = _session_with_two_lands()
    assert s1.doSubmitSenateVotes(pids1)["success"]
    v_all = st1.get_senate_votes_copy().get(pv1, {})
    assert all(v_all.get(pid) is True for pid in pids1), f"全选 ⇒ 全赞成：{v_all}"
    s2, st2, _v2, pv2, pids2 = _session_with_two_lands()
    assert s2.doSubmitSenateVotes([])["success"]
    v_none = st2.get_senate_votes_copy().get(pv2, {})
    assert all(v_none.get(pid) is False for pid in pids2), f"全不选 ⇒ 全反对：{v_none}"


def test_r7_data_unchecked_logged_vote_false_and_oppose_influence():
    """FC-C43(1)(2)（★）：取消勾选 ⇒ 人类票 = False（**日志双证**）+ 结果正确
    （`oppose_influence` 含该派系）。"""
    store, state, viewer, pid_viewer, pids = _session_with_two_lands()
    viewer_faction_id = viewer.faction_id
    inv = state.get_faction(viewer_faction_id).get_senate_influence(state)
    assert inv > 0

    with _CaptureHandler(state) as cap:
        fb = store.doSubmitSenateVotes([pids[0]])   # 取消勾选 pids[1]
        assert fb["success"], fb
        if store.senateCurrentStep == "tribune_veto":
            assert store.doSubmitSenateVetoes([])["success"]

    # 证 ①：record_vote 日志（extra player_id/proposal_id/vote）
    assert cap.has(lambda m, e: e.get("player_id") == pid_viewer
                   and e.get("proposal_id") == pids[1] and e.get("vote") is False), \
        f"须有 record_vote 日志 vote=False（pids[1]）：{[ (m,e) for m,e in cap.records if e.get('proposal_id')==pids[1] ]}"
    # 证 ②：senate_vote_decision 日志（人类票 reused，vote=False vote_source=human；owner 派系）
    assert cap.has(lambda m, e: e.get("type") == "senate_vote_decision"
                   and e.get("proposal_id") == pids[1] and e.get("faction_id") == viewer_faction_id
                   and e.get("vote") is False and e.get("vote_source") == "human"), \
        f"须有 senate_vote_decision vote=False vote_source=human：{[ (m,e) for m,e in cap.records if e.get('type')=='senate_vote_decision' ]}"

    # 结果正确：oppose_influence 含该派系影响力
    assert store.senateCurrentStep == "results", store.senateCurrentStep
    by_id = {r["proposal_id"]: r for r in (store.senateVoteResults or [])}
    row = by_id[pids[1]]
    assert row["oppose_influence"] >= inv, \
        f"oppose_influence 须含反对派系（FC-C43(2)）：{row} inv={inv}"
    assert row["support_influence"] + row["oppose_influence"] == row["total_influence"]


# ---------------------------------------------------------------------------
# FC-C41 / FC-C43 —— RENDER_AUTOMATED（默认未勾选 + 真实可切换；几何；有头 live）
# ---------------------------------------------------------------------------

def _setup_senate_vote_selection(ids):
    def _fn(window):
        root_item = R._window_root_item(window)
        for it in R._all_items(root_item):
            if R._has_property(it, "selectedSenateVoteIds"):
                it.setProperty("selectedSenateVoteIds", [int(x) for x in ids])
                break
    return _fn


def test_r7_render_senate_vote_default_unchecked_and_toggle():
    """FC-C41(3)：`senate_vote` 帧 ② 每行勾选框**默认未勾选**；写入 ② 选择集 ⇒ 该行**勾选**
    （真实可切换选择态）。1280×720 及更大视口。"""
    rows = []
    for (w, h, tag) in ((1440, 900, "1440x900"), (1280, 720, "1280x720")):
        store, _state, _viewer, _lbl, _kind = R._senate_vote_store_with_long_proposal()
        assert store.senateCurrentStep == "senate_vote", store.senateCurrentStep
        by_label = {r.get("label"): r for r in (store.senateSubmittedProposals or [])}
        labels = [l for l in by_label if l]
        # 默认未勾选
        engine, _ = R._create_engine(store)
        name = f"group-c-g7testr7-default-unchecked-{tag}.png"
        cap = R._capture(engine, os.path.join(EVIDENCE_BASE, _EVID_DIR, name), w, h)
        rows.append(R._emit(_EVID_DIR, name, cap,
                            "create_gui_prototype_session(senate)+doSubmitSenateProposals"
                            "+long_war_name(war_proposal)",
                            "senate_vote", (w, h)))
        window = engine.rootObjects()[0]
        _root, stage_root = R._find_stage_root(window)
        assert stage_root is not None
        p2 = R._panel2_rows(stage_root, labels)
        assert p2, f"须定位 ② 行（{tag}）"
        for label, _identity, cb, _card in p2:
            assert cb is not None and cb.property("visible"), f"senate_vote ② 行须有可见勾选框（{tag}）"
            assert not cb.property("checked"), f"默认须未勾选（FC-C41(3)）（{tag}）: {label!r}"
        R._teardown(engine)
        # 写入选择集 ⇒ 勾选
        target_label, target_id = p2[0][0], by_label[p2[0][0]].get("id")
        engine2, _ = R._create_engine(store)
        name2 = f"group-c-g7testr7-toggled-{tag}.png"
        cap2 = R._capture(engine2, os.path.join(EVIDENCE_BASE, _EVID_DIR, name2), w, h,
                          setup=_setup_senate_vote_selection([target_id]))
        rows.append(R._emit(_EVID_DIR, name2, cap2,
                            "create_gui_prototype_session(senate)+doSubmitSenateProposals"
                            "+selectedSenateVoteIds=[id]",
                            "senate_vote", (w, h)))
        window2 = engine2.rootObjects()[0]
        _r2, stage_root2 = R._find_stage_root(window2)
        p2b = {l: cb for (l, _i, cb, _c) in R._panel2_rows(stage_root2, labels)}
        assert p2b.get(target_label) is not None and p2b[target_label].property("checked"), \
            f"选择集含该 id ⇒ 勾选（FC-C41(2)）（{tag}）: {target_label!r}"
        R._teardown(engine2)
    with open(os.path.join(EVIDENCE_BASE, _EVID_DIR, "g7testr7-render-manifest.json"),
              "w", encoding="utf-8") as fh:
        json.dump({"schema": "wpj-groupc-render-manifest/v1", "rows": rows}, fh,
                  ensure_ascii=False, indent=2)
        fh.write("\n")
    assert all(r["capture_ok"] for r in rows), rows


def test_r7_render_geometry_1280x720_and_larger():
    """FC-C43(5)：`senate_vote` 帧于 1280×720 与更大视口渲染成功、窗口/阶段根几何非零（非回归）。"""
    for (w, h, tag) in ((1440, 900, "1440x900"), (1280, 720, "1280x720")):
        store = R._senate_vote_store_with_long_proposal()[0]
        engine, _ = R._create_engine(store)
        name = f"group-c-g7testr7-geometry-{tag}.png"
        cap = R._capture(engine, os.path.join(EVIDENCE_BASE, _EVID_DIR, name), w, h)
        assert cap and cap not in ("timeout",), f"截图须成功（{tag}）: {cap}"
        window = engine.rootObjects()[0]
        assert (window.width() or 0) > 0 and (window.height() or 0) > 0, f"窗口几何须非零（{tag}）"
        _root, stage_root = R._find_stage_root(window)
        assert stage_root is not None and (stage_root.width() or 0) > 0, f"阶段根几何须非零（{tag}）"
        R._teardown(engine)
    assert True


def test_r7_render_live_headed_recheck_recorded():
    """FC-C43(4) 有头/窗口化 live 复验如实登记：本 DA 运行环境为**无头 WSL**（无 DISPLAY；
    测试进程强制 offscreen）⇒ **NOT_APPLICABLE（不伪造）**；以离屏 RENDER_AUTOMATED 替代。
    注：「取消勾选 land 行」的有头复验待有头环境补做（离屏样本为 war 行）。"""
    display = os.environ.get("DISPLAY")
    plat = os.environ.get("QT_QPA_PLATFORM")
    out = os.path.join(EVIDENCE_BASE, _EVID_DIR, "g7testr7-live-headed.runtime.json")
    os.makedirs(os.path.dirname(out), exist_ok=True)
    record = {
        "schema": "wpj-groupc-live-headed/v1",
        "requested": "有头/窗口化 live 复验（真实 app.py；非 offscreen；含取消勾选 land 行 + 战争行）",
        "display": display,
        "QT_QPA_PLATFORM_env": plat,
        "status": "NOT_APPLICABLE_HEADLESS",
        "reason": ("本 DA 运行环境为无头 WSL（无可用 DISPLAY；测试进程强制 QT_QPA_PLATFORM=offscreen）；"
                   "无法进行有头实机 live 复验。已以离屏 RENDER_AUTOMATED（真实 Main.qml + 真实生产链"
                   " create_gui_prototype_session + 选择集写回）替代并如实登记。"),
    }
    with open(out, "w", encoding="utf-8") as fh:
        json.dump(record, fh, ensure_ascii=False, indent=2)
        fh.write("\n")
    assert not display, f"若有 DISPLAY 则应做有头复验（不得伪报）: {display}"


if __name__ == "__main__":
    import pytest
    raise SystemExit(pytest.main([__file__, "-v", "-s"]))
