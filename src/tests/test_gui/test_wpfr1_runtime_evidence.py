# src/tests/test_gui/test_wpfr1_runtime_evidence.py
"""WP-F-R1 runtime 证据采集（EC-14 模式，production-shape，DA-Plan §9 清单）。

路径：真实 gui_prototype 会话（session_api.create_gui_prototype_session）
→ 真实 GuiSessionStore → 真实 Main.qml 离屏渲染（QT_QPA_PLATFORM=offscreen）
→ window.grabWindow() → PNG 落 03-da-evidence/WP-F-R1/runtime/。

捕获项（DA-Plan §9）：
1. population-candidates-faction-colors      候选人三派系着色（R1-F-01）
2. population-results-winner-faction-colors  当选者派系色 + winner 状态（R1-F-02）
3. senate-results-support-rate-no-govops     支持率 + GovOps 卡缺席（R1-F-03/04）
4. forum-public-land-before                  首购前认购入口（R1-F-05）
5. forum-public-land-after-purchase          认购后 market 区（重复区已删；Dialog 过滤=DATA T-F09）
6. forum-public-land-canonical-only          resolve 后 canonical 公示区唯一呈现（R1-F-05）

守卫（P1-HARNESS-01 模式）：PNG 已存在且 meta 在 → 校验 sha256 后跳过（不重捕获）；
设 WP_F_R1_REFRESH_EVIDENCE=1 强制重捕获。离屏渲染不可用 → fallback=true（PNG 不作生产证据）。
DATA 证据处用 DATA 断言（本文件仅 render-proof；业务正确性由 T-F01~T-F12 承载）。
"""
import hashlib
import json
import os
import sys
from datetime import datetime, timezone

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
os.environ.setdefault("PYTHONUTF8", "1")
os.environ.setdefault("PYTHONUNBUFFERED", "1")
os.environ.setdefault("PYTHONDONTWRITEBYTECODE", "1")

PROJECT_ROOT = os.path.normpath(
    os.path.join(os.path.dirname(__file__), "..", "..", "..")
)
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

EVIDENCE_BASE = (
    "/mnt/e/OpenClaw/Projects/EOR/workspace/EOR20260821-01 GUI-BETA-R1"
    "/WP-F-GUIPolish/03-da-evidence/WP-F-R1/runtime"
)
BRANCH = "task/gui-beta-r1-wpf"
HEAD = "9aa20aa85732e7e2284014f1f9eabd561431862b"
VIEWPORT = (1440, 900)
REFRESH = os.environ.get("WP_F_R1_REFRESH_EVIDENCE", "0") == "1"

from src.api import session_api
from src.ui.gui.models.candidate_list_model import CandidateListModel
from src.ui.gui.models.event_list_model import EventListModel
from src.ui.gui.models.figure_list_model import FigureListModel
from src.ui.gui.session_store import GuiSessionStore


class _DummyGuiApp:
    pass


def _get_app():
    from PySide6.QtGui import QGuiApplication
    return QGuiApplication.instance() or QGuiApplication([])


def _create_engine(store):
    from PySide6.QtCore import QUrl
    from PySide6.QtQml import QQmlApplicationEngine, QQmlComponent, qmlRegisterType

    _get_app()
    qml_dir = os.path.join(PROJECT_ROOT, "src", "ui", "gui", "qml")
    engine = QQmlApplicationEngine()
    engine.addImportPath(qml_dir)

    qmlRegisterType(FigureListModel, "EOR.Models", 1, 0, "FigureListModel")
    qmlRegisterType(CandidateListModel, "EOR.Models", 1, 0, "CandidateListModel")
    qmlRegisterType(EventListModel, "EOR.Models", 1, 0, "EventListModel")

    theme_component = QQmlComponent(engine)
    theme_component.loadUrl(QUrl.fromLocalFile(os.path.join(qml_dir, "theme", "Theme.qml")))
    assert not theme_component.isError(), theme_component.errorString()
    theme = theme_component.create()
    assert theme is not None

    gui_app = _DummyGuiApp()
    engine.rootContext().setContextProperty("theme", theme)
    engine.rootContext().setContextProperty("sessionStore", store)
    engine.rootContext().setContextProperty("guiApp", gui_app)
    return engine, qml_dir


def _make_store(start_phase="population"):
    result = session_api.create_gui_prototype_session(start_phase=start_phase)
    assert result["success"], result.get("message")
    state = result["data"]["state"]
    viewer_id = result["data"]["human_players"][0]
    state.set_current_player(viewer_id)
    store = GuiSessionStore(state)
    store.initialize(viewer_id)
    return store, state, viewer_id


def _main_qml_url():
    from PySide6.QtCore import QUrl
    qml_dir = os.path.join(PROJECT_ROOT, "src", "ui", "gui", "qml")
    return QUrl.fromLocalFile(os.path.join(qml_dir, "Main.qml"))


def _capture(engine, out_png):
    from PySide6.QtCore import QCoreApplication, QTimer
    from PySide6.QtGui import QGuiApplication

    app = _get_app()
    engine.load(_main_qml_url())
    QGuiApplication.processEvents()
    roots = engine.rootObjects()
    if not roots:
        return None, {"error": "no root objects"}
    window = roots[0]
    result = []
    diagnostics = []

    def finish(value):
        if not result:
            result.append(value)
        QCoreApplication.quit()

    def grab():
        try:
            window.show()
            QGuiApplication.processEvents()
            QGuiApplication.processEvents()
            diagnostics.append("shown=" + str(window.isVisible()))
            img = None
            if hasattr(window, "grabWindow"):
                try:
                    img = window.grabWindow()
                    diagnostics.append("grabWindow_null=" + str(img is None or img.isNull()))
                except Exception as exc:
                    diagnostics.append("grabWindow_exc=" + type(exc).__name__ + ":" + str(exc))
            if img is None or img.isNull():
                scr = QGuiApplication.primaryScreen()
                if scr is not None:
                    try:
                        img = scr.grabWindow(int(window.winId()))
                        diagnostics.append("screen_grab_null=" + str(img is None or img.isNull()))
                    except Exception as exc:
                        diagnostics.append("screen_grab_exc=" + type(exc).__name__ + ":" + str(exc))
            if img is None or img.isNull():
                diagnostics.append("no_image")
                finish(None)
                return
            ok = img.save(out_png)
            diagnostics.append("save_ok=" + str(ok) + " size=" + str(img.width()) + "x" + str(img.height()))
            finish(out_png if ok else None)
        except Exception as exc:
            diagnostics.append("exception=" + type(exc).__name__ + ":" + str(exc))
            finish(None)

    QTimer.singleShot(900, grab)
    QTimer.singleShot(20000, lambda: finish("timeout"))
    app.exec()
    value = result[0] if result else None
    if value == "timeout":
        value = None
        diagnostics.append("watchdog_timeout")
    return value, {
        "window_width": int(window.property("width")),
        "window_height": int(window.property("height")),
        "root_objects": len(roots),
        "capture_diagnostics": diagnostics,
    }


def _sha256(path):
    h = hashlib.sha256()
    with open(path, "rb") as fh:
        for chunk in iter(lambda: fh.read(65536), b""):
            h.update(chunk)
    return h.hexdigest()


def _write_meta(page, png, prep, render_ready, fallback=False):
    meta = png.replace(".png", "-runtime.json")
    meta_data = {
        "fixture": f"test_wpfr1_runtime_evidence.py::{page}",
        "page": page,
        "phase": page.split("-")[0],
        "viewport": list(VIEWPORT),
        "state_prep": prep,
        "render_ready": render_ready,
        "png_path": png if os.path.exists(png) else None,
        "png_sha256": _sha256(png) if os.path.exists(png) else None,
        "captured_at_utc": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
        "branch": BRANCH,
        "head": HEAD + "+worktree(WP-F-R1-DA-uncommitted)",
        "identity": "wp-f-r1-candidate",
        "fallback": fallback,
        "qpa_platform": "offscreen",
        "note": "production-shape: create_gui_prototype_session -> GuiSessionStore -> Main.qml grabWindow; "
                "截图仅 render-proof（DATA 业务断言见 T-F01~T-F12）",
    }
    with open(meta, "w", encoding="utf-8") as fh:
        json.dump(meta_data, fh, indent=2, ensure_ascii=False)
    return meta


def _guarded(page, prep_fn):
    """PNG 已存在且 meta 在 → sha256 校验后跳过；否则捕获并写 meta。"""
    os.makedirs(EVIDENCE_BASE, exist_ok=True)
    png = os.path.join(EVIDENCE_BASE, page + ".png")
    meta = png.replace(".png", "-runtime.json")
    if os.path.exists(png) and os.path.exists(meta) and not REFRESH:
        with open(meta, encoding="utf-8") as fh:
            prev = json.load(fh)
        assert prev.get("png_sha256") == _sha256(png), f"{page}: PNG 与 meta 不一致（immutability guard）"
        return {"skipped": True, "png": png, "sha256": prev.get("png_sha256")}
    store, state, viewer_id = prep_fn()
    engine, _ = _create_engine(store)
    png_path, diag = _capture(engine, png)
    fallback = png_path is None
    if fallback:
        png = png.replace(".png", "-fallback.txt")
        with open(png, "w", encoding="utf-8") as fh:
            json.dump(diag, fh, indent=2, ensure_ascii=False)
    _write_meta(page, png, _prep_steps(page), render_ready=not fallback, fallback=fallback)
    return {"skipped": False, "png": png, "fallback": fallback, "diagnostics": diag}


_PREP_STEPS = {
    "population-candidates-faction-colors": ["create_gui_prototype_session(start_phase=population)", "selectPhase(population)"],
    "population-results-winner-faction-colors": ["submitPopulationVotes(selection_map)", "selectPhase(population)"],
    "senate-results-support-rate-no-govops": ["doSubmitSenateProposals", "doSubmitSenateVotes", "doSubmitSenateVetoes([first])", "results step"],
    "forum-public-land-before": ["mortality->revenue->forum", "land sale act(300C)", "completeForumStep"],
    "forum-public-land-after-purchase": ["buy_land(figure, 3)", "refresh_forum_view"],
    "forum-public-land-canonical-only": ["doResolveForum", "refresh_forum_view"],
}


def _prep_steps(page):
    return _PREP_STEPS.get(page, [])


def _seed_senate_proposals(store, state):
    """确定性种入 2 条公地提案（绕开 prototype 随机 consul/AI proposer 路由，
    投票/否决/resolve 链保持真实；propose 环节非 R1-F-03 测试面）。"""
    state.add_senate_proposal({
        "type": "land", "act_type": "sale", "amount_C": 50, "percent": 0.05,
        "proposer_faction": "optimates", "proposer_player": "player_optimates",
        "consul_id": 1, "description": "公地出售法案 50 C", "label": "卖地法案 — 出售 50 C",
    })
    state.add_senate_proposal({
        "type": "land", "act_type": "distribution", "amount_C": 50, "percent": 0.05,
        "proposer_faction": "optimates", "proposer_player": "player_optimates",
        "consul_id": 1, "description": "公地分配法案 50 C", "label": "分地法案 — 分配 50 C",
    })
    store._refresh_senate_view()


def _drive_population_and_senate(store, state, viewer_id, veto_first=True):
    """种入提案 → 投票 → 否决（可选）→ resolve → results（全真实 store 链）。"""
    _seed_senate_proposals(store, state)
    fb = store.doSubmitSenateVotes()
    assert fb.get("success"), fb.get("message")
    submitted = store.senateSubmittedProposals or []
    # 否决最后一个提案（仅当 ≥2 提案）——保证至少一个通过提案展示「通过 · 支持率 X%」；
    # tribune 归属随机 → 否决失败时降级空否决（resolve 仍执行）
    if veto_first and len(submitted) >= 2:
        try:
            store.doSubmitSenateVetoes([int(submitted[-1]["id"])])
        except Exception:
            store.doSubmitSenateVetoes([])
    else:
        store.doSubmitSenateVetoes([])
    return None


def _prepare_forum_with_land(store, state, viewer_id):
    from src.core.entities.contract import ContractType, ContractStatus
    from src.core.systems.political_system import PoliticalSystem

    assert store.doExecuteMortality()["success"]
    assert store.doAdvanceMortality()["success"]
    assert store.doExecuteRevenue()["success"]
    assert store.doAdvanceRevenue()["success"]
    assert store.currentPhaseId == "forum"

    ps = PoliticalSystem(state)
    assert ps.execute_passed_proposal({
        "type": "land", "act_type": "sale", "amount_C": 300, "percent": 100.0,
    })["success"]
    contract = state.create_contract(ContractType.TAX_FARMING, 1, 100, state.turn.turn_number)
    contract.status = ContractStatus.BUDGETED
    assert store.doCompleteForumStep()["success"]
    store.selectPhase("forum")
    store._refresh_forum_view()
    return contract


def _grab_phase(store, phase):
    store.selectPhase(phase)
    _get_app().processEvents()
    return store


def test_evidence_population_candidates_faction_colors():
    """证据 1：候选人三派系着色（R1-F-01）。"""
    def prep():
        store, state, viewer_id = _make_store(start_phase="population")
        _grab_phase(store, "population")
        return store, state, viewer_id
    result = _guarded("population-candidates-faction-colors", prep)
    if result.get("skipped"):
        return
    assert not result.get("fallback"), f"offscreen capture failed: {result.get('diagnostics')}"


def test_evidence_population_results_winner_faction_colors():
    """证据 2：当选者派系色 + winner 状态（R1-F-02）。"""
    def prep():
        store, state, viewer_id = _make_store(start_phase="population")
        selection_map = {}
        for office in ("consul", "censor", "praetor", "quaestor", "tribune"):
            for c in store.populationCandidates:
                if c.get("office") == office:
                    selection_map[office] = int(c.get("id"))
                    break
        store.submitPopulationVotes(selection_map)
        _grab_phase(store, "population")
        assert store.populationResolved
        return store, state, viewer_id
    result = _guarded("population-results-winner-faction-colors", prep)
    if result.get("skipped"):
        return
    assert not result.get("fallback"), f"offscreen capture failed: {result.get('diagnostics')}"


def test_evidence_senate_results_support_rate_no_govops():
    """证据 3：支持率展示 + GovOps 卡缺席（R1-F-03/04）。"""
    def prep():
        store, state, viewer_id = _make_store(start_phase="senate")
        _drive_population_and_senate(store, state, viewer_id, veto_first=True)
        assert store.senateCurrentStep == "results"
        # DATA 探针：vote_results 必须经 GUI store 链透传（R1-F-03 全链）
        assert store.senateVoteResults, "senateVoteResults must flow through GUI store chain"
        return store, state, viewer_id
    result = _guarded("senate-results-support-rate-no-govops", prep)
    if result.get("skipped"):
        return
    assert not result.get("fallback"), f"offscreen capture failed: {result.get('diagnostics')}"


def test_evidence_forum_public_land_before():
    """证据 4：首购前认购入口（R1-F-05）。"""
    def prep():
        store, state, viewer_id = _make_store(start_phase="mortality")
        _prepare_forum_with_land(store, state, viewer_id)
        return store, state, viewer_id
    result = _guarded("forum-public-land-before", prep)
    if result.get("skipped"):
        return
    assert not result.get("fallback"), f"offscreen capture failed: {result.get('diagnostics')}"


def _land_purchase_args(store):
    """按财富选买家并计算可负担数量（prototype 人物财富随机，防财富不足 flake）。"""
    buyers = [f for f in (store.forumMyFigures or []) if f.get("can_buy_land")]
    assert buyers, "prototype must have >=1 eligible land buyer"
    buyer = max(buyers, key=lambda f: f.get("wealth") or 0)
    price = store.forumLandPricePerUnit or 10
    amount = max(1, min(2, (buyer.get("wealth") or 0) // price))
    return int(buyer["id"]), amount


def test_evidence_forum_public_land_after_purchase():
    """证据 5：认购后 market 区（重复结果区已删；买家过滤=DATA T-F09）。"""
    def prep():
        store, state, viewer_id = _make_store(start_phase="mortality")
        _prepare_forum_with_land(store, state, viewer_id)
        fig_id, amount = _land_purchase_args(store)
        res = store.doBuyLand(fig_id, amount)
        assert res.get("success"), res.get("message")
        store._refresh_forum_view()
        return store, state, viewer_id
    result = _guarded("forum-public-land-after-purchase", prep)
    if result.get("skipped"):
        return
    assert not result.get("fallback"), f"offscreen capture failed: {result.get('diagnostics')}"


def test_evidence_forum_public_land_canonical_only():
    """证据 6：resolve 后 canonical 公示区唯一呈现（R1-F-05 ②）。"""
    def prep():
        store, state, viewer_id = _make_store(start_phase="mortality")
        _prepare_forum_with_land(store, state, viewer_id)
        buyers = [f for f in (store.forumMyFigures or []) if f.get("can_buy_land")]
        if buyers:
            fig_id, amount = _land_purchase_args(store)
            store.doBuyLand(fig_id, amount)
            store._refresh_forum_view()
        res = store.doResolveForum()
        assert res.get("success"), res.get("message")
        store._refresh_forum_view()
        return store, state, viewer_id
    result = _guarded("forum-public-land-canonical-only", prep)
    if result.get("skipped"):
        return
    assert not result.get("fallback"), f"offscreen capture failed: {result.get('diagnostics')}"
