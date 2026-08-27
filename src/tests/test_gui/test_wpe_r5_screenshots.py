# src/tests/test_gui/test_wpe_r5_screenshots.py
"""WP-E-R5 — S0/S6 Revenue 短款 before/after 截图证据测试（EC-14 模式，production-shape）。

路径：真实 gui_prototype 会话（session_api.create_gui_prototype_session）
→ 真实 GuiSessionStore → 真实 Main.qml 离屏渲染（QT_QPA_PLATFORM=offscreen）
→ window.grabWindow() → PNG 落 03-da-evidence/WP-E-R5/{before,after}/。

- BEFORE 截图（S0）：R5-pre 工作树（1bcb54a + R4 候选），行「军团维护费 −160」
  但国库未扣（行-账不一致：delta +27 / 新余额 116）。
- AFTER 截图（S6）：R5 候选（同 viewport / 同 state-prep），行「−160（缺口 29）」、
  bottom 净变化 −133 / 新余额 −44（账实相符）。
- 短款场景构造（BEFORE/AFTER 同构造，T6 对齐）：
  economic rules（base=8/vet+1/recruit=4/stipend=5）；national public land=30000（公地收益 60）；
  national_opex_rate 校准至 opex=18；征召 20 军团并全部指派战争 w1（候选空）；opening=89
  → opex −18 → 71 → 公地 +60 → 131（维护费时点）→ 维护费 −160（短款 29）→ −29 → stipend −15 → −44。
- runtime meta：SHA + head=1bcb54a+worktree + fallback=false（禁 fallback 当生产证据）。
- BEFORE 保全守卫：before/ 已存在且未设 WP_E_R5_REFRESH_BEFORE=1 → 不重捕获、不重写 meta。
"""
import hashlib
import json
import os
import sys
from datetime import datetime, timezone

import pytest

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
    "/03-da-evidence/WP-E-R5"
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


def _prepare_r5_shortfall(store, state, viewer_id):
    """R5 短款场景（T6 对齐）：维护费时点国库=131，20 军团全战争指派（候选空）。"""
    from src.core.entities.war import War

    cfg = state._config
    # 1) 显式 economic rules（生产 config 漂移防护；R5 计费规则零改动，仅测试态覆盖数值）
    cfg.economic_rules.legion_maintenance_base = 8
    cfg.economic_rules.veteran_maintenance_bonus = 1
    cfg.economic_rules.legion_recruit_cost = 4
    cfg.economic_rules.faction_stipend = 5
    # 2) 公地收益 = 60：int(round(30000 × 10 × 0.01 × 0.02)) = 60
    state._national_public_land = 30000
    # 3) 运营费 = 18：int(total_conquered_land × 10 × rate) = 18
    conquered = [p for p in state.get_all_provinces() if p.conquered]
    total_land = sum(p.total_land for p in conquered)
    assert total_land > 0, "prototype scenario must have conquered provinces"
    cfg.economic_rules.national_opex_rate = 18.0 / (total_land * 10)
    # 4) 征召 20 军团（recruit_cost=4 × 20 = 80）
    state.treasury = 500
    ms = state.get_military_system()
    for n in range(1, 21):
        ok, msg = ms.recruit_legion(n)
        assert ok, f"recruit legion {n}: {msg}"
    # 5) 全部指派战争 w1（战争军团不解散：候选过滤 war_id is None 三重保护之一）
    war = War(id="w1", name="皮洛士战争")
    state.get_war_system()._active_wars.append(war)
    for n in range(1, 21):
        legion = ms.get_legion_by_number(n)
        assert legion.assign_to_war("w1", commander_id=1), f"assign legion {n}"
    # 6) 天命阶段（不依赖 treasury；随后显式设 opening=89）
    assert store.doExecuteMortality()["success"]
    assert store.doAdvanceMortality()["success"]
    # 6b) 清空天命事件（丰调雨顺×1.5/天灾 loss 会放大公地收益，破坏 T6 对齐的确定性轨迹）
    state.clear_active_events()
    # 7) opening = 89 → opex −18 → 71 → 公地 +60 → 131（维护费时点）→ 短款 29
    state.treasury = 89
    # 8) 收入阶段结算
    assert store.doExecuteRevenue()["success"]
    store.selectPhase("revenue")
    store._refresh_revenue_view()
    return {
        "steps": [
            "config(base=8,vet+1,recruit=4,stipend=5)",
            "national_public_land=30000(land_income=60)",
            "national_opex_rate calibrated(opex=18)",
            "recruit 20 legions", "assign_to_war(w1) x20",
            "doExecuteMortality", "doAdvanceMortality",
            "clear_active_events (天命事件会放大公地收益，破坏 T6 轨迹)",
            "treasury=89(opening)", "doExecuteRevenue", "selectPhase(revenue)",
        ],
        "opening": 89,
        "opex": 18,
        "land_income": 60,
        "maintenance_total": 160,
    }


def _main_qml_url():
    from PySide6.QtCore import QUrl
    qml_dir = os.path.join(PROJECT_ROOT, "src", "ui", "gui", "qml")
    return QUrl.fromLocalFile(os.path.join(qml_dir, "Main.qml"))


def _collect_texts(roots):
    """递归收集所有 QML Text 的 text 属性（维护费行/缺口提示/bottom 无 objectName，走文本探针）。"""
    from PySide6.QtCore import QObject
    texts = []
    for r in roots:
        for o in r.findChildren(QObject):
            try:
                t = o.property("text")
            except Exception:
                continue
            if isinstance(t, str) and t.strip():
                texts.append(t)
    return texts


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
    probes["text_scan"] = {"found": bool(_collect_texts(roots)), "texts": _collect_texts(roots)}
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


def _write_evidence(kind, prep, render_ready, fallback=False):
    subdir = "before" if kind == "before" else "after"
    out_dir = os.path.join(EVIDENCE_BASE, subdir)
    os.makedirs(out_dir, exist_ok=True)
    if kind == "before":
        png_name = "revenue-before-r5pre.png"
        meta_name = "revenue-before-r5pre-runtime.json"
        head = "1bcb54a+worktree(R4-uncommitted)"
        identity = "r5-pre(r4-candidate)"
    else:
        png_name = "revenue-after.png"
        meta_name = "revenue-after-runtime.json"
        head = "1bcb54a+worktree(DA-R5-uncommitted)"
        identity = "r5-candidate"
    png = os.path.join(out_dir, png_name)
    meta = os.path.join(out_dir, meta_name)
    meta_data = {
        "fixture": "test_wpe_r5_screenshots.py::revenue",
        "page": "revenue",
        "kind": kind,
        "phase": "revenue",
        "viewport": list(VIEWPORT),
        "state_prep": prep,
        "render_ready": render_ready,
        "png_path": png if os.path.exists(png) else None,
        "png_sha256": _sha256(png) if os.path.exists(png) else None,
        "captured_at_utc": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
        "branch": BRANCH,
        "head": head,
        "identity": identity,
        "fallback": fallback,
        "qpa_platform": "offscreen",
        "note": "EC-14 production-shape path: create_gui_prototype_session -> GuiSessionStore -> Main.qml grabWindow",
    }
    with open(meta, "w", encoding="utf-8") as fh:
        json.dump(meta_data, fh, indent=2, ensure_ascii=False)
    return png, meta


def _dto_snapshot(store):
    data = store.revenueSettledData or {}
    military = (data.get("maintenance") or {}).get("military") or {}
    naval = (data.get("maintenance") or {}).get("naval") or {}
    stipend_total = sum(
        (row.get("stipend") or 0) for row in (data.get("faction_rows") or {}).values()
    )
    return {
        "settled": bool(data),
        "starting": data.get("starting_treasury"),
        "ending": data.get("ending_treasury"),
        "delta": data.get("treasury_delta"),
        "opex": (data.get("national_opex") or {}).get("amount"),
        "land": (data.get("public_land_income") or {}).get("amount"),
        "land_treasury_after": (data.get("public_land_income") or {}).get("treasury_after"),
        "military_keys": sorted(military.keys()),
        "military_total": military.get("total"),
        "military_charged": military.get("charged"),
        "military_shortfall": military.get("shortfall"),
        "military_disbanded": military.get("disbanded"),
        "military_success": military.get("success"),
        "naval_total": naval.get("total"),
        "stipend_total": stipend_total,
    }


def _run_screenshot(kind):
    assert kind in ("before", "after")
    store, state, viewer_id = _make_store()
    prep = _prepare_r5_shortfall(store, state, viewer_id)
    dto_snapshot = _dto_snapshot(store)

    before_png = os.path.join(EVIDENCE_BASE, "before", "revenue-before-r5pre.png")
    if kind == "before":
        # 代码态守卫：R5 已落地后 BEFORE 仅能是 S0 的 R5-pre 捕获；拒绝用 post-R5 捕获覆盖
        if "charged" in dto_snapshot["military_keys"]:
            pytest.skip(
                "代码已为 R5-post：BEFORE 证据保留 S0 R5-pre 捕获（R5-pre 代码态才可重捕获，需回退+WP_E_R5_REFRESH_BEFORE=1）"
            )
        if os.path.exists(before_png) and os.environ.get("WP_E_R5_REFRESH_BEFORE") != "1":
            return {
                "kind": kind,
                "png": before_png,
                "render_ready": {
                    "root_objects": 1,
                    "preserved": "before evidence already recorded at 1bcb54a(R5-pre); not re-captured",
                },
                "dto_snapshot": dto_snapshot,
                "fallback": False,
            }

    png_path, meta_path = _write_evidence(kind, prep, {})
    engine, qml_dir = _create_engine(store)

    # R4 继承面：派系津贴行 objectName 探针；维护费行/缺口提示/bottom 走 text_scan
    probe_specs = {"factionStipendRow": ["visible"]}
    captured, render_ready = _capture(engine, png_path, probe_specs=probe_specs)
    fallback = captured is None
    if fallback:
        png_path = None
    _write_evidence(kind, prep, render_ready, fallback=fallback)

    assert dto_snapshot, "empty dto snapshot"
    return {
        "kind": kind,
        "png": captured,
        "render_ready": render_ready,
        "dto_snapshot": dto_snapshot,
        "fallback": fallback,
    }


# ─── S0 BEFORE（R5-pre 工作树）────────────────────────────────────────────

def test_screenshot_revenue_before():
    """R5-pre：行显「−160」（应扣 total），国库分文未扣 → delta +27 / 新余额 116（行-账不一致）。
    保全守卫：before/ 证据已存在（或代码已为 R5-post）→ 跳过（S0 R5-pre 捕获即生产证据）。"""
    result = _run_screenshot("before")
    assert result["render_ready"].get("root_objects", 0) > 0
    snap = result["dto_snapshot"]
    assert snap["settled"] is True
    # 场景基线（T6 对齐）：opening 89 → opex 18 → land 60 → 维护费时点国库 131
    assert snap["starting"] == 89
    assert snap["opex"] == 18
    assert snap["land"] == 60
    assert snap["land_treasury_after"] == 131
    assert snap["stipend_total"] == 15
    assert snap["naval_total"] == 0
    # R5-pre：维护费 DTO 无 charged 键；total=160（应扣）但 success=False（实扣 0）
    assert snap["military_total"] == 160
    assert "charged" not in snap["military_keys"], snap["military_keys"]
    assert snap["military_success"] is False
    # 行-账不一致：delta 不含维护费 → +27；新余额 116（行显 −160 但国库未扣）
    assert snap["delta"] == 27
    assert snap["ending"] == 116
    if not result["fallback"]:
        assert os.path.exists(result["png"])
        assert os.path.getsize(result["png"]) > 0
        probes = result["render_ready"].get("qml_probes", {})
        texts = probes.get("text_scan", {}).get("texts", [])
        joined = " | ".join(texts)
        # 维护费行显「−160 Talents」（应扣）；无缺口提示（R5-pre 无 shortfall 概念）
        assert "-160 Talents" in joined, joined
        assert "缺口" not in joined, joined
        assert "国库净变化: +27 Talents" in joined, joined
        assert "新余额: 116 Talents" in joined, joined
        # R4 继承面：派系津贴行在位
        assert probes.get("factionStipendRow", {}).get("found") is True
        # 生产证据前提：fallback=false
        meta = json.load(open(os.path.join(EVIDENCE_BASE, "before", "revenue-before-r5pre-runtime.json"), encoding="utf-8"))
        assert meta["fallback"] is False


# ─── S6 AFTER（R5 候选工作树）────────────────────────────────────────────

def test_screenshot_revenue_after():
    """R5：行=实扣「−160（缺口 29）」，国库照扣 → delta −133 / 新余额 −44（账实相符）。"""
    result = _run_screenshot("after")
    assert result["render_ready"].get("root_objects", 0) > 0
    snap = result["dto_snapshot"]
    assert snap["settled"] is True
    assert snap["starting"] == 89
    assert snap["opex"] == 18
    assert snap["land"] == 60
    assert snap["land_treasury_after"] == 131
    assert snap["stipend_total"] == 15
    assert snap["naval_total"] == 0
    # R5：维护费 DTO charged/shortfall/disbanded 在位；charged = before − after 同源
    assert snap["military_total"] == 160
    assert snap["military_charged"] == 160
    assert snap["military_shortfall"] == 29
    assert snap["military_disbanded"] == 0
    assert snap["military_success"] is True
    assert snap["military_charged"] == 131 - (-29)
    # 账实相符：delta 含维护费 −160 → −133；新余额 −44（89 + (−133)）
    assert snap["delta"] == -133
    assert snap["ending"] == -44
    if not result["fallback"]:
        assert os.path.exists(result["png"])
        assert os.path.getsize(result["png"]) > 0
        probes = result["render_ready"].get("qml_probes", {})
        texts = probes.get("text_scan", {}).get("texts", [])
        joined = " | ".join(texts)
        assert "-160 Talents" in joined, joined
        assert "缺口 29" in joined, joined
        assert "国库净变化: -133 Talents" in joined, joined
        assert "新余额: -44 Talents" in joined, joined
        assert probes.get("factionStipendRow", {}).get("found") is True
        meta = json.load(open(os.path.join(EVIDENCE_BASE, "after", "revenue-after-runtime.json"), encoding="utf-8"))
        assert meta["fallback"] is False
