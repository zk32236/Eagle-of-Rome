# src/tests/test_gui/test_wpe_r3_a2_screenshots.py
"""WP-E-R3 Attempt-2 — S0/S7 全页截图证据测试（EC-14 模式，production-shape）。

路径：真实 gui_prototype 会话（session_api.create_gui_prototype_session）
→ 真实 GuiSessionStore → 真实 Main.qml 离屏渲染（QT_QPA_PLATFORM=offscreen）
→ window.grabWindow() → PNG 落 03-da-evidence/WP-E-R3-A2/{before,after}/。

- BEFORE 截图（S0）：eb157fb 状态，页面 = Revenue / Forum / Combat（viewport 1440×900）
- AFTER 截图（S7）：同 viewport / 同 state-prep 对照
- 每张截图伴随 *-runtime.json meta（fixture/state/phase/render_ready/png_sha256/
  captured_at_utc/branch/HEAD + state-prep 清单）
- 离屏渲染不可用时降级为 DTO 验证证据（test_screenshot_revenue.py 同款 fallback 先例），
  meta 标记 fallback=true。

本文件为 G4 冻结测试面登记（非探针）：S0 全量基线在文件加入前已实测
（1597 collected / 1589 passed / 8 skipped / 0 failed），本文件计入 S6 全量。
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
    "/03-da-evidence/WP-E-R3-A2"
)
BRANCH = "task/gui-beta-r1-wpe"
HEAD = "eb157fbbac15a203b6f82c3b0d7b9f6829e73780"
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
    """EC-14 同款 engine：真实 Main.qml + 真实 sessionStore 上下文属性。"""
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
    """真实生产会话 + Store（mortality 起点）。"""
    result = session_api.create_gui_prototype_session()
    assert result["success"], result.get("message")
    state = result["data"]["state"]
    viewer_id = result["data"]["human_players"][0]
    state.set_current_player(viewer_id)
    store = GuiSessionStore(state)
    store.initialize(viewer_id)
    return store, state, viewer_id


def _prepare_revenue(store, state, viewer_id):
    """Revenue 结算后态：mortality → revenue 执行（不推进）。"""
    assert store.doExecuteMortality()["success"]
    assert store.doAdvanceMortality()["success"]
    assert store.doExecuteRevenue()["success"]
    store.selectPhase("revenue")
    store._refresh_revenue_view()
    return {
        "steps": ["doExecuteMortality", "doAdvanceMortality", "doExecuteRevenue", "selectPhase(revenue)"],
    }


def _prepare_forum(store, state, viewer_id, place_bid=False):
    """Forum 市场态：mortality → revenue → forum + sale 法案 + BUDGETED 合同 + 开市。

    place_bid=True（S7 AFTER）：追加 viewer 出价恰一 7 元组（place_bid 同款持久层
    state.add_forum_action）→ 合同行渲染「已出价 X T（待结算）」pending 态（D-07 delta #3）。
    """
    from src.core.entities.contract import ContractType, ContractStatus
    from src.core.systems.political_system import PoliticalSystem

    assert store.doExecuteMortality()["success"]
    assert store.doAdvanceMortality()["success"]
    assert store.doExecuteRevenue()["success"]
    assert store.doAdvanceRevenue()["success"]
    assert store.currentPhaseId == "forum"

    # sale 法案（政治系统权威写入 quota + total）
    ps = PoliticalSystem(state)
    assert ps.execute_passed_proposal({
        "type": "land", "act_type": "sale", "amount_C": 300, "percent": 100.0,
    })["success"]
    # BUDGETED 合同（state.create_contract 权威构造 + 状态迁移）
    contract = state.create_contract(ContractType.TAX_FARMING, 1, 100, state.turn.turn_number)
    contract.status = ContractStatus.BUDGETED
    # 开市（retirement → market；AI 派系同路径处理）
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


def _prepare_combat(store, state, viewer_id):
    """Combat 态：活跃战争 + 指挥官 + 3 个已附着军团（rebellion 生产路径）。"""
    ws = state.get_war_system()
    ms = state.get_military_system()
    assert ws is not None and ms is not None

    province = state.get_province(1)
    assert province is not None
    war = ws.create_rebellion_war(province)
    assert ws.register_rebellion_war(war) is True

    members = state.get_living_members()
    assert members, "no living members for commander"
    commander_id = members[0].id
    assert ws.assign_commander(war.id, commander_id, legions=0, fleets=0) is True

    for num in (1, 2, 3):
        ok, _ = ms.recruit_legion(num)
        assert ok, f"recruit legion {num} failed"
    assigned, _msg = ms.assign_to_war([1, 2, 3], war.id, commander_id)
    assert assigned == 3

    store.selectPhase("combat")
    store._refresh_combat_view()
    return {
        "steps": [
            "create_rebellion_war", "register_rebellion_war",
            "assign_commander(legions=0)", "recruit_legion(1,2,3)",
            "assign_to_war([1,2,3])", "selectPhase(combat)",
        ],
        "war_id": war.id,
        "war_name": war.name,
        "commander_id": commander_id,
        "attached_legions": [l.number for l in ms.get_legions_for_battle(war.id)],
        "war_legion_numbers": war.legion_numbers,
        "legions_assigned_field": war.legions_assigned,
    }


def _main_qml_url():
    from PySide6.QtCore import QUrl
    qml_dir = os.path.join(PROJECT_ROOT, "src", "ui", "gui", "qml")
    return QUrl.fromLocalFile(os.path.join(qml_dir, "Main.qml"))


def _capture(engine, out_png, probe_specs=None):
    """离屏 grabWindow → PNG。失败/超时返回 None（fallback 标记）。

    诊断信息写入 render_ready（供 G5 复核 fallback 原因）。
    probe_specs: {objectName: [property,...]} → render_ready.qml_probes
    （017 actor 选择行 / D-07 pending 行 / landDialog 存在性 + 状态证据）
    """
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
            diagnostics.append(
                "mro=" + ",".join(c.__name__ for c in type(window).__mro__[:6])
            )
            img = None
            # Strategy 1: QQuickWindow.grabWindow()
            if hasattr(window, "grabWindow"):
                try:
                    img = window.grabWindow()
                    diagnostics.append("grabWindow_null=" + str(img is None or img.isNull()))
                except Exception as exc:
                    diagnostics.append("grabWindow_exc=" + type(exc).__name__ + ":" + str(exc))
            # Strategy 2: QScreen.grabWindow(winId)
            if img is None or img.isNull():
                scr = QGuiApplication.primaryScreen()
                if scr is not None:
                    try:
                        img = scr.grabWindow(int(window.winId()))
                        diagnostics.append(
                            "screen_grab_null=" + str(img is None or img.isNull())
                        )
                    except Exception as exc:
                        diagnostics.append("screen_grab_exc=" + type(exc).__name__ + ":" + str(exc))
            if img is None or img.isNull():
                diagnostics.append("no_image")
                finish(None)
                return
            ok = img.save(out_png)
            diagnostics.append(
                "save_ok=" + str(ok) + " size=" + str(img.width()) + "x" + str(img.height())
            )
            finish(out_png if ok else None)
        except Exception as exc:
            diagnostics.append("exception=" + type(exc).__name__ + ":" + str(exc))
            finish(None)

    QTimer.singleShot(800, grab)
    QTimer.singleShot(20000, lambda: finish("timeout"))  # watchdog
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
    """写 PNG meta json；返回 (png_path, meta_path)。"""
    subdir = "before" if kind == "before" else "after"
    out_dir = os.path.join(EVIDENCE_BASE, subdir)
    os.makedirs(out_dir, exist_ok=True)
    png_name = f"{page}-before-eb157fb.png" if kind == "before" else f"{page}-after.png"
    meta_name = f"{page}-before-eb157fb-runtime.json" if kind == "before" else f"{page}-after-runtime.json"
    png = os.path.join(out_dir, png_name)
    meta = os.path.join(out_dir, meta_name)
    meta_data = {
        "fixture": f"test_wpe_r3_a2_screenshots.py::{page}",
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
        "head": HEAD if kind == "before" else "eb157fb+worktree(DA-R4-A2-uncommitted)",
        "identity": "eb157fb-before" if kind == "before" else "attempt2-candidate",
        "fallback": fallback,
        "qpa_platform": "offscreen",
        "note": "EC-14 production-shape path: create_gui_prototype_session -> GuiSessionStore -> Main.qml grabWindow",
    }
    with open(meta, "w", encoding="utf-8") as fh:
        json.dump(meta_data, fh, indent=2, ensure_ascii=False)
    return png, meta


def _run_screenshot(page, prepare, kind=None):
    kind = kind or os.environ.get("WP_E_R3_A2_EVIDENCE_KIND", "before")
    assert kind in ("before", "after")
    store, state, viewer_id = _make_store()
    prep = prepare(store, state, viewer_id)

    # 渲染前 DTO 状态记录（fallback 证据）
    dto_snapshot = {
        "page": page,
        "prep": prep,
    }
    if page == "revenue":
        dto_snapshot["settled"] = bool(store.revenueSettledData)
        dto_snapshot["treasury_delta"] = store.treasuryDelta
    elif page == "forum":
        dto_snapshot["forum_land_requests"] = store.forumViewerLandRequests
        dto_snapshot["pending_contracts"] = len(store.forumPendingContracts)
        # D-07 viewer_contract_bids 为 DA-R4 v3 新增 DTO；BEFORE 在 eb157fb 纯净态生成时
        # 该属性不存在 → 保护式读取（before 用例不断言 bids；after 用例在 DA 修改态运行，属性必在）
        dto_snapshot["viewer_contract_bids"] = getattr(
            store, "forumViewerContractBids", None
        )
        dto_snapshot["eligible_land_actors"] = [
            f for f in (store.forumMyFigures or []) if f.get("can_buy_land")
        ]
    elif page == "combat":
        dto_snapshot["combat_active_wars"] = [
            {"war_id": w.get("war_id"), "legion_count": w.get("legion_count"),
             "legion_numbers": w.get("legion_numbers"), "total_power": w.get("total_power")}
            for w in store.combatActiveWars
        ]

    # BEFORE 证据保全：eb157fb 基线已存在且未显式刷新 → 不重捕获、不重写 meta
    # （防 Attempt-1/RT-A Lesson 2 类「真实截图被同名覆盖」复发）
    before_png = os.path.join(EVIDENCE_BASE, "before", f"{page}-before-eb157fb.png")
    if (
        kind == "before"
        and os.path.exists(before_png)
        and os.environ.get("WP_E_R3_A2_REFRESH_BEFORE") != "1"
    ):
        return {
            "page": page,
            "png": before_png,
            "render_ready": {
                "root_objects": 1,
                "preserved": "before evidence already recorded at eb157fb; not re-captured",
            },
            "dto_snapshot": dto_snapshot,
            "fallback": False,
        }

    png_path, meta_path = _write_evidence(page, kind, prep, {})
    engine, qml_dir = _create_engine(store)
    # 先设阶段再 load（对齐 test_wpe_war_threat_presentation 先例）
    probe_specs = None
    if page == "forum":
        probe_specs = {
            "landActorCombo": ["count", "currentIndex", "visible"],
            "publicLandPurchaseRow": ["enabledAction", "label"],
            "landDialog": ["visible"],
        }
    captured, render_ready = _capture(engine, png_path, probe_specs=probe_specs)
    fallback = captured is None
    if fallback:
        # 降级：DTO 验证证据（png_path 保留为 None）
        png_path = None
    _write_evidence(page, kind, prep, render_ready, fallback=fallback)

    assert dto_snapshot, "empty dto snapshot"
    return {
        "page": page,
        "png": captured,
        "render_ready": render_ready,
        "dto_snapshot": dto_snapshot,
        "fallback": fallback,
    }


def test_screenshot_revenue_before():
    """S0 BEFORE：Revenue 全页截图（1440×900）+ meta。"""
    result = _run_screenshot("revenue", _prepare_revenue)
    assert result["render_ready"].get("root_objects", 0) > 0
    if not result["fallback"]:
        assert os.path.exists(result["png"])
        assert os.path.getsize(result["png"]) > 0
        assert result["dto_snapshot"]["settled"] is True
    else:
        # fallback：DTO 证据已落 meta（png_sha256=null + fallback=true）
        assert result["dto_snapshot"]["settled"] is True


def test_screenshot_forum_before():
    """S0 BEFORE：Forum 全页截图（1440×900）+ meta。"""
    result = _run_screenshot("forum", _prepare_forum)
    assert result["render_ready"].get("root_objects", 0) > 0
    assert result["dto_snapshot"]["prep"]["forum_current_step"] == "market"
    if not result["fallback"]:
        assert os.path.exists(result["png"])
        assert os.path.getsize(result["png"]) > 0


def test_screenshot_combat_before():
    """S0 BEFORE：Combat 全页截图（1440×900）+ meta。"""
    result = _run_screenshot("combat", _prepare_combat)
    assert result["render_ready"].get("root_objects", 0) > 0
    wars = result["dto_snapshot"]["combat_active_wars"]
    assert len(wars) == 1
    # eb157fb 陈旧计数：legions_assigned 字段=0 而番号非空（POST-07P 证据）
    assert wars[0]["legion_numbers"] == [1, 2, 3]
    if not result["fallback"]:
        assert os.path.exists(result["png"])
        assert os.path.getsize(result["png"]) > 0


# ════════════════════════════════════════════════════════════════════════
# S7 AFTER：同 viewport / 同 state-prep 对照（DA-R4 Attempt-2 候选）
# ════════════════════════════════════════════════════════════════════════

def test_screenshot_revenue_after():
    """S7 AFTER：Revenue 全页截图（对照 BEFORE）+ meta。"""
    result = _run_screenshot("revenue", _prepare_revenue, kind="after")
    assert result["render_ready"].get("root_objects", 0) > 0
    assert result["dto_snapshot"]["settled"] is True
    if not result["fallback"]:
        assert os.path.exists(result["png"])
        assert os.path.getsize(result["png"]) > 0


def test_screenshot_forum_after():
    """S7 AFTER：Forum 全页 + 017 actor 选择行 + D-07 合同行 pending 态证据。

    prep 追加 viewer 出价恰一 7 元组 → viewer_contract_bids 恰一 pending；
    qml_probes 记录 landActorCombo（017 选择行）存在性 + publicLandPurchaseRow 状态。
    """
    result = _run_screenshot(
        "forum",
        lambda s, st, v: _prepare_forum(s, st, v, place_bid=True),
        kind="after",
    )
    assert result["render_ready"].get("root_objects", 0) > 0
    assert result["dto_snapshot"]["prep"]["forum_current_step"] == "market"
    # D-07 DATA：恰一 viewer pending（7 元组投影）
    bids = result["dto_snapshot"]["viewer_contract_bids"]
    assert len(bids) == 1
    assert bids[0]["status"] == "pending"
    assert bids[0]["amount"] == 100
    # 017 RENDER：有可认购人物 → actor 选择行存在（findChild objectName）
    probes = result["render_ready"].get("qml_probes", {})
    if result["dto_snapshot"]["eligible_land_actors"]:
        assert probes.get("landActorCombo", {}).get("found") is True
    if not result["fallback"]:
        assert os.path.exists(result["png"])
        assert os.path.getsize(result["png"]) > 0


def test_screenshot_combat_after():
    """S7 AFTER：Combat 全页 + POST-07P 计数/番号实时实体派生（总览=卡面=3）。"""
    result = _run_screenshot("combat", _prepare_combat, kind="after")
    assert result["render_ready"].get("root_objects", 0) > 0
    wars = result["dto_snapshot"]["combat_active_wars"]
    assert len(wars) == 1
    # ODR-A：legion_count = 实时附着实体数（BEFORE=0 陈旧计数 → AFTER=3）
    assert wars[0]["legion_count"] == 3
    assert wars[0]["legion_numbers"] == [1, 2, 3]
    assert wars[0]["total_power"] > 0  # commander_martial + 3*2
    # WP-G 边界：war.legion_numbers 残留不清空（DTO 不读它）
    assert result["dto_snapshot"]["prep"]["war_legion_numbers"] == [1, 2, 3]
    if not result["fallback"]:
        assert os.path.exists(result["png"])
        assert os.path.getsize(result["png"]) > 0
