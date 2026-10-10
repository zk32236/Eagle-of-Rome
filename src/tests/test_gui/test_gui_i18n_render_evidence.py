# src/tests/test_gui/test_gui_i18n_render_evidence.py
"""GUI-I18N S2 — RENDER_AUTOMATED bilingual proof (route = DIRECT_PRODUCTION).

Single live session, one engine, no restart:
    zh-CN -> en-US -> zh-CN  (``GuiLocalization.setLocale`` + ``localeChanged``)
capturing TopStatusBar + PhaseRail + MortalityStage at 1440x900 each time.

Production chain only: ``create_gui_prototype_session`` -> real ``GuiSessionStore``
-> real ``Main.qml`` offscreen render -> ``window.grabWindow()`` -> PNG. No mock /
no HTML capture. Locale before/after, ``localeChanged`` emissions and the
authoritative GameState fingerprint before/after are recorded in the manifest.

Evidence: ``03-da-evidence/GUI-I18N-S2/render/``.
"""
import hashlib
import json
import os
import sys
import time
from datetime import datetime, timezone

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
os.environ.setdefault("PYTHONUTF8", "1")
os.environ.setdefault("PYTHONUNBUFFERED", "1")

PROJECT_ROOT = os.path.normpath(os.path.join(os.path.dirname(__file__), "..", "..", ".."))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

EVIDENCE_BASE = (
    "/mnt/e/OpenClaw/Projects/EOR/workspace/EOR20261009-01 GUI-i18n-Fundation"
    "/03-da-evidence/GUI-I18N-S2/render"
)

from src.api import session_api  # noqa: E402
from src.ui.gui.localization import DEFAULT_LOCALE, gui_localization  # noqa: E402
from src.ui.gui.models.candidate_list_model import CandidateListModel  # noqa: E402
from src.ui.gui.models.event_list_model import EventListModel  # noqa: E402
from src.ui.gui.models.figure_list_model import FigureListModel  # noqa: E402
from src.ui.gui.session_store import GuiSessionStore  # noqa: E402


class _DummyGuiApp:
    pass


# Keep the engine/window alive: collecting a live QQmlApplicationEngine with
# created objects is a known PySide6 crash/deadlock source under suite load.
_LIVE = []


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

    engine.rootContext().setContextProperty("theme", theme)
    engine.rootContext().setContextProperty("sessionStore", store)
    engine.rootContext().setContextProperty("guiApp", _DummyGuiApp())
    engine.rootContext().setContextProperty("localization", gui_localization)
    engine._test_refs = (store, theme)
    _LIVE.append(engine)
    return engine, qml_dir


def _make_store():
    result = session_api.create_gui_prototype_session("mortality")
    assert result["success"], result.get("message")
    state = result["data"]["state"]
    viewer_id = result["data"]["human_players"][0]
    state.set_current_player(viewer_id)
    store = GuiSessionStore(state)
    store.initialize(viewer_id)
    store.selectPhase("mortality")
    return store, state


def _fingerprint(state):
    current = state.get_current_player()
    return {
        "turn_number": state.turn.turn_number if state.turn else None,
        "treasury": state.treasury,
        "current_player_id": current.player_id if current else None,
        "players": sorted(p.player_id for p in state.get_all_players()),
        "living_members": len(state.get_living_members()),
    }


def _grab(window, out_png, width=1440, height=900, attempts=200):
    app = _get_app()
    out_dir = os.path.dirname(out_png)
    if out_dir:
        os.makedirs(out_dir, exist_ok=True)
    window.show()
    try:
        window.setWidth(width)
        window.setHeight(height)
    except Exception:
        pass
    for _ in range(attempts):
        for _ in range(2):
            app.processEvents()
        try:
            window.requestUpdate()
        except Exception:
            pass
        app.processEvents()
        img = None
        try:
            if hasattr(window, "grabWindow") and window.width() > 0 and window.height() > 0:
                img = window.grabWindow()
        except Exception:
            img = None
        if img is None or img.isNull():
            try:
                from PySide6.QtGui import QGuiApplication
                scr = QGuiApplication.primaryScreen()
                if scr is not None:
                    img = scr.grabWindow(int(window.winId()))
            except Exception:
                img = None
        if img is not None and not img.isNull():
            ok = img.save(out_png)
            if ok:
                return {"png": out_png, "width": img.width(), "height": img.height()}
            return None
        time.sleep(0.05)
    return None


def _sha256(path):
    h = hashlib.sha256()
    with open(path, "rb") as fh:
        for chunk in iter(lambda: fh.read(65536), b""):
            h.update(chunk)
    return h.hexdigest()


def _walk(obj):
    yield obj
    seen = set()
    kids = []
    try:
        kids.extend(obj.childItems())
    except Exception:
        pass
    try:
        kids.extend(obj.children())
    except Exception:
        pass
    for child in kids:
        cid = id(child)
        if cid in seen:
            continue
        seen.add(cid)
        yield from _walk(child)


def _texts(root, object_name):
    from PySide6.QtCore import QObject
    node = root.findChild(QObject, object_name)
    if node is None:
        return []
    out = []
    for item in _walk(node):
        try:
            text = item.property("text")
        except Exception:
            continue
        if isinstance(text, str) and text:
            out.append(text)
    return out


def _proof_snapshot(root):
    return {
        "topStatusBar": _texts(root, "topStatusBar"),
        "phaseRail": _texts(root, "phaseRail"),
        "mortalityStage": _texts(root, "mortalityStage"),
    }


def test_render_proof_surface_zh_en_zh_same_session():
    _get_app()
    store, state = _make_store()
    engine, qml_dir = _create_engine(store)

    from PySide6.QtCore import QUrl
    engine.load(QUrl.fromLocalFile(os.path.join(qml_dir, "Main.qml")))
    _get_app().processEvents()
    roots = engine.rootObjects()
    assert roots, "Main.qml loaded with no root object"
    window = roots[0]
    _LIVE.append(window)

    emissions = []
    gui_localization.localeChanged.connect(lambda: emissions.append(gui_localization.currentLocale))

    fp_before = _fingerprint(state)
    frames = []

    for locale, tag in ((DEFAULT_LOCALE, "A"), ("en-US", "B"), (DEFAULT_LOCALE, "C")):
        gui_localization.setLocale(locale)
        _get_app().processEvents()
        snapshot = _proof_snapshot(window)
        name = f"gui-i18n-s2-{tag}-{locale}-1440x900.png"
        grab = _grab(window, os.path.join(EVIDENCE_BASE, name))
        frames.append({
            "frame": tag,
            "locale": locale,
            "png": name,
            "grab": grab,
            "png_sha256": _sha256(os.path.join(EVIDENCE_BASE, name)) if grab else None,
            "proof_texts": snapshot,
        })

    fp_after = _fingerprint(state)

    manifest = {
        "schema": "gui-i18n-s2-render-manifest/v1",
        "route": "DIRECT_PRODUCTION",
        "viewport": [1440, 900],
        "surfaces": ["topStatusBar", "phaseRail", "mortalityStage"],
        "locale_sequence": [f["locale"] for f in frames],
        "locale_changed_emissions": emissions,
        "fingerprint_before": fp_before,
        "fingerprint_after": fp_after,
        "frames": frames,
        "captured_at_utc": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
    }
    os.makedirs(EVIDENCE_BASE, exist_ok=True)
    with open(os.path.join(EVIDENCE_BASE, "render-manifest.json"), "w", encoding="utf-8") as fh:
        json.dump(manifest, fh, ensure_ascii=False, indent=2)
        fh.write("\n")

    # --- assertions ---------------------------------------------------------
    assert [f["locale"] for f in frames] == [DEFAULT_LOCALE, "en-US", DEFAULT_LOCALE]
    assert emissions == ["en-US", DEFAULT_LOCALE], emissions
    assert all(f["grab"] is not None for f in frames), frames
    assert fp_after == fp_before, (fp_before, fp_after)

    zh_top = frames[0]["proof_texts"]["topStatusBar"]
    en_top = frames[1]["proof_texts"]["topStatusBar"]
    zh_rail = frames[0]["proof_texts"]["phaseRail"]
    en_rail = frames[1]["proof_texts"]["phaseRail"]
    zh_mort = frames[0]["proof_texts"]["mortalityStage"]
    en_mort = frames[1]["proof_texts"]["mortalityStage"]

    assert "国库" in zh_top and "Treasury" in en_top, (zh_top, en_top)
    assert "天命" in zh_rail and "Mortality" in en_rail, (zh_rail, en_rail)
    assert any("点击下方「执行天命」" in t for t in zh_mort), zh_mort
    assert any("Execute Mortality" in t for t in en_mort), en_mort
    # frame C returns to the zh-CN baseline
    assert frames[2]["proof_texts"]["topStatusBar"] == zh_top
