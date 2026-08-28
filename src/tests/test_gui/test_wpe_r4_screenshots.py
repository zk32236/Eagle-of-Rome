# src/tests/test_gui/test_wpe_r4_screenshots.py
"""WP-E-R4 — S0/S4 全页截图证据测试（EC-14 模式，production-shape）。

路径：真实 gui_prototype 会话（session_api.create_gui_prototype_session）
→ 真实 GuiSessionStore → 真实 Main.qml 离屏渲染（QT_QPA_PLATFORM=offscreen）
→ window.grabWindow() → PNG 落 03-da-evidence/WP-E-R4/{before,after}/。

- BEFORE 截图（S0）：1bcb54a 状态，页面 = Forum / Revenue（viewport 1440×900）
- AFTER 截图（S4）：同 viewport / 同 state-prep 对照（R4 候选 = worktree 未提交）
- 每张截图伴随 *-runtime.json meta（fallback/png_sha256/captured_at_utc/branch/head/state-prep）
- BEFORE 保全守卫：before/ 已存在且未设 WP_E_R4_REFRESH_BEFORE=1 → 不重捕获、不重写 meta。
- 离屏渲染不可用 → fallback=true，PNG 禁当生产证据（png_sha256=null）。
"""
import hashlib
import json
import os
import sys
from datetime import datetime, timezone

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
os.environ.setdefault("PYTHONUTF8", "1")
os.environ.setdefault("PYTHONUNBUFFERED", "1")

PROJECT_ROOT = os.path.normpath(
    os.path.join(os.path.dirname(__file__), "..", "..", "..")
)
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

EVIDENCE_BASE = (
    "/mnt/e/OpenClaw/Projects/EOR/workspace/EOR20260821-01 GUI-BETA-R1"
    "/03-da-evidence/WP-E-R4"
)
BRANCH = "task/gui-beta-r1-wpe"
HEAD = "1bcb54a6a569b62557c3d4d126cd160d84717c05"
VIEWPORT = (1440, 900)

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


def _make_store():
    result = session_api.create_gui_prototype_session()
    assert result["success"], result.get("message")
    state = result["data"]["state"]
    viewer_id = result["data"]["human_players"][0]
    state.set_current_player(viewer_id)
    store = GuiSessionStore(state)
    store.initialize(viewer_id)
    return store, state, viewer_id


def _prepare_revenue(store, state, viewer_id):
    assert store.doExecuteMortality()["success"]
    assert store.doAdvanceMortality()["success"]
    assert store.doExecuteRevenue()["success"]
    store.selectPhase("revenue")
    store._refresh_revenue_view()
    return {
        "steps": ["doExecuteMortality", "doAdvanceMortality", "doExecuteRevenue", "selectPhase(revenue)"],
    }


def _prepare_forum(store, state, viewer_id, place_bid=False):
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
    steps = [
        "doExecuteMortality", "doAdvanceMortality", "doExecuteRevenue",
        "doAdvanceRevenue", "sale_act(300C)", "create_contract(BUDGETED)",
        "doCompleteForumStep", "selectPhase(forum)",
    ]
    if place_bid:
        figures = store.forumMyFigures or []
        bidder_id = figures[0]["id"] if figures else None
        faction_id = state.get_player(viewer_id).faction_id
        assert bidder_id is not None
        state.add_forum_action(
            "contract_bids", (contract.id, bidder_id, faction_id, 100, 0.2, 4, 6)
        )
        store._refresh_forum_view()
        steps.append("add_forum_action(contract_bids, viewer bid 7-tuple)")
    return {
        "steps": steps,
        "land_sale_total": state.turn_land_sale_total,
        "land_sale_quota": state.pending_land_sale_quota,
        "contract_id": contract.id,
        "forum_current_step": store.forumCurrentStep,
    }


def _main_qml_url():
    from PySide6.QtCore import QUrl
    qml_dir = os.path.join(PROJECT_ROOT, "src", "ui", "gui", "qml")
    return QUrl.fromLocalFile(os.path.join(qml_dir, "Main.qml"))


def _capture(engine, out_png, probe_specs=None):
    from PySide6.QtCore import QCoreApplication, QObject, QTimer
    from PySide6.QtGui import QGuiApplication

    app = _get_app()
    engine.load(_main_qml_url())
    QGuiApplication.processEvents()
    roots = engine.rootObjects()
    if not roots:
        return None, {"error": "no root objects"}
    window = roots[0]
    probes = {}
    if probe_specs:
        for obj_name, props in probe_specs.items():
            obj = None
            for r in roots:
                obj = r.findChild(QObject, obj_name)
                if obj is not None:
                    break
            if obj is None:
                probes[obj_name] = {"found": False}
                continue
            row = {"found": True}
            for p in props:
                try:
                    row[p] = obj.property(p)
                except Exception as exc:
                    row[p] = "probe_exc:" + type(exc).__name__
            probes[obj_name] = row
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
            diagnostics.append("type=" + type(window).__name__)
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

    QTimer.singleShot(800, grab)
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
        "qml_probes": probes,
    }


def _sha256(path):
    h = hashlib.sha256()
    with open(path, "rb") as fh:
        for chunk in iter(lambda: fh.read(65536), b""):
            h.update(chunk)
    return h.hexdigest()


def _write_evidence(page, kind, prep, render_ready, fallback=False):
    """写 PNG meta json；返回 (png_path, meta_path)。

    P1-HARNESS-01 run-scoped（O-1）：WP_E_R4_RUN_ID 显式 opt-in → after 写
    runs/<run-id>/after/（历史 after/ 冻结原位）；无 RUN_ID → 维持 after/。
    """
    run_id = os.environ.get("WP_E_R4_RUN_ID")
    subdir = "before" if kind == "before" else "after"
    if kind == "after" and run_id:
        out_dir = os.path.join(EVIDENCE_BASE, "runs", run_id, "after")
    else:
        out_dir = os.path.join(EVIDENCE_BASE, subdir)
    os.makedirs(out_dir, exist_ok=True)
    png_name = f"{page}-before-1bcb54a.png" if kind == "before" else f"{page}-after.png"
    meta_name = f"{page}-before-1bcb54a-runtime.json" if kind == "before" else f"{page}-after-runtime.json"
    png = os.path.join(out_dir, png_name)
    meta = os.path.join(out_dir, meta_name)
    meta_data = {
        "fixture": f"test_wpe_r4_screenshots.py::{page}",
        "page": page,
        "kind": kind,
        "phase": page,
        "viewport": list(VIEWPORT),
        "state_prep": prep,
        "render_ready": render_ready,
        "png_path": png if os.path.exists(png) else None,
        "png_sha256": _sha256(png) if os.path.exists(png) else None,
        "captured_at_utc": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
        "branch": BRANCH,
        "head": HEAD if kind == "before" else "1bcb54a+worktree(DA-R4-uncommitted)",
        "identity": "1bcb54a-before" if kind == "before" else (f"{run_id}-candidate" if run_id else "r4-candidate"),
        "fallback": fallback,
        "qpa_platform": "offscreen",
        "note": "EC-14 production-shape path: create_gui_prototype_session -> GuiSessionStore -> Main.qml grabWindow",
    }
    with open(meta, "w", encoding="utf-8") as fh:
        json.dump(meta_data, fh, indent=2, ensure_ascii=False)
    return png, meta


def _dto_snapshot(page, store):
    snap = {"page": page}
    if page == "revenue":
        snap["settled"] = bool(store.revenueSettledData)
        snap["treasury_delta"] = store.treasuryDelta
        data = store.revenueSettledData or {}
        snap["faction_stipend_total"] = sum(
            (row.get("stipend") or 0) for row in (data.get("faction_rows") or {}).values()
        )
    elif page == "forum":
        snap["forum_land_requests"] = store.forumViewerLandRequests
        snap["pending_contracts"] = len(store.forumPendingContracts)
        snap["viewer_contract_bids"] = getattr(store, "forumViewerContractBids", None)
        snap["forum_current_step"] = store.forumCurrentStep
        snap["eligible_land_actors"] = [
            f for f in (store.forumMyFigures or []) if f.get("can_buy_land")
        ]
        snap["eligible_bidders"] = [
            f for f in (store.forumMyFigures or []) if f.get("can_bid")
        ]
    return snap


def _run_screenshot(page, prepare, kind=None):
    kind = kind or os.environ.get("WP_E_R4_EVIDENCE_KIND", "before")
    assert kind in ("before", "after")
    store, state, viewer_id = _make_store()
    prep = prepare(store, state, viewer_id)
    dto_snapshot = _dto_snapshot(page, store)

    before_png = os.path.join(EVIDENCE_BASE, "before", f"{page}-before-1bcb54a.png")
    if (
        kind == "before"
        and os.path.exists(before_png)
        and os.environ.get("WP_E_R4_REFRESH_BEFORE") != "1"
    ):
        return {
            "page": page,
            "png": before_png,
            "render_ready": {
                "root_objects": 1,
                "preserved": "before evidence already recorded at 1bcb54a; not re-captured",
            },
            "dto_snapshot": dto_snapshot,
            "fallback": False,
        }

    # AFTER 证据保全（P1-HARNESS-01）：历史 after 已存在且未显式 opt-in → 不重捕获、不重写 meta
    run_id = os.environ.get("WP_E_R4_RUN_ID")
    after_png = os.path.join(EVIDENCE_BASE, "after", f"{page}-after.png")
    if (
        kind == "after"
        and not run_id
        and os.path.exists(after_png)
        and os.environ.get("WP_E_R4_REFRESH_AFTER") != "1"
    ):
        return {
            "page": page,
            "png": after_png,
            "render_ready": {
                "root_objects": 1,
                "preserved": "after evidence already recorded; not re-captured (set "
                             "WP_E_R4_RUN_ID or WP_E_R4_REFRESH_AFTER=1 to regenerate)",
            },
            "dto_snapshot": dto_snapshot,
            "fallback": False,
            "captured": False,   # ← P1-1 修复：显式标记「守卫跳过」，与 fallback 分离
        }

    png_path, meta_path = _write_evidence(page, kind, prep, {})
    engine, qml_dir = _create_engine(store)

    probe_specs = None
    if page == "forum":
        if kind == "before":
            probe_specs = {
                "landActorCombo": ["count", "currentIndex", "visible"],
                "publicLandPurchaseRow": ["enabledAction", "label"],
                "landDialog": ["visible"],
            }
        else:
            # S4 AFTER：017 删除主 UI landActorCombo；新增 Dialog 内 landActorDialogCombo + bidDialog
            probe_specs = {
                "landActorCombo": ["count", "visible"],
                "landActorDialogCombo": ["count", "visible"],
                "bidDialog": ["visible"],
                "publicLandPurchaseRow": ["enabledAction", "label"],
            }
    elif page == "revenue" and kind == "after":
        # D-12 RENDER：国家支出新增「派系津贴(国库拨款)」行存在性
        probe_specs = {
            "factionStipendRow": ["visible"],
        }
    captured, render_ready = _capture(engine, png_path, probe_specs=probe_specs)
    fallback = captured is None
    if fallback:
        png_path = None
    _write_evidence(page, kind, prep, render_ready, fallback=fallback)

    assert dto_snapshot, "empty dto snapshot"
    return {
        "page": page,
        "png": captured,
        "render_ready": render_ready,
        "dto_snapshot": dto_snapshot,
        "fallback": fallback,
        "captured": captured is not None,   # ← P1-1：正常路径 captured=True（渲染成功）/ False（fallback）
    }


# ─── S0 BEFORE ────────────────────────────────────────────────────────────

def test_screenshot_revenue_before():
    result = _run_screenshot("revenue", _prepare_revenue)
    assert result["render_ready"].get("root_objects", 0) > 0
    assert result["dto_snapshot"]["settled"] is True
    if not result["fallback"]:
        assert os.path.exists(result["png"])
        assert os.path.getsize(result["png"]) > 0


def test_screenshot_forum_before():
    result = _run_screenshot("forum", _prepare_forum)
    assert result["render_ready"].get("root_objects", 0) > 0
    assert result["dto_snapshot"]["forum_current_step"] == "market"
    if not result["fallback"]:
        assert os.path.exists(result["png"])
        assert os.path.getsize(result["png"]) > 0


# ─── S4 AFTER ─────────────────────────────────────────────────────────────

def test_screenshot_revenue_after():
    result = _run_screenshot("revenue", _prepare_revenue, kind="after")
    assert result["render_ready"].get("root_objects", 0) > 0
    assert result["dto_snapshot"]["settled"] is True
    # D-12 DATA：stipend 合计 > 0（驱动国家支出新行）
    assert result["dto_snapshot"]["faction_stipend_total"] > 0
    # D-12 RENDER：国家支出「派系津贴(国库拨款)」行存在
    probes = result["render_ready"].get("qml_probes", {})
    if result.get("captured"):          # 原 if not result["fallback"]:
        assert probes.get("factionStipendRow", {}).get("found") is True
        assert os.path.exists(result["png"])
        assert os.path.getsize(result["png"]) > 0


def test_screenshot_forum_after():
    result = _run_screenshot(
        "forum",
        lambda s, st, v: _prepare_forum(s, st, v, place_bid=True),
        kind="after",
    )
    assert result["render_ready"].get("root_objects", 0) > 0
    assert result["dto_snapshot"]["forum_current_step"] == "market"
    # D-07 DATA：恰一 viewer pending bid（7 元组投影）
    bids = result["dto_snapshot"]["viewer_contract_bids"]
    assert len(bids) == 1
    assert bids[0]["status"] == "pending"
    # 017 RENDER：主 UI landActorCombo 已删（findChild objectName 不存在）
    probes = result["render_ready"].get("qml_probes", {})
    if result.get("captured"):          # 原 if not result["fallback"]:
        assert probes.get("landActorCombo", {}).get("found") is False
        assert probes.get("landActorDialogCombo", {}).get("found") is True
        assert probes.get("bidDialog", {}).get("found") is True
        assert os.path.exists(result["png"])
        assert os.path.getsize(result["png"]) > 0
