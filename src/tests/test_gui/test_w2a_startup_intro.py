"""W2a — 1H+AI neutral startup page: 「开始游戏」 + 【游戏介绍】.

RED-first for G4 §1 (EOR20261013-02 / W2a). These tests pin the frozen copy
(Owner 2026-10-18 21:54) to the REAL production overlay and the REAL store value
channel (``self._state`` at neutral startup, never ``_snapshot``).

Covered: AC-01 (1H render), AC-02 (no auto-activation), AC-03 (3H unchanged),
AC-04 (locale switch / no residue / a11y), AC-05 (1H privacy), AC-06 (scenario
values 142 vs 100), N5 (missing/unparsable -> em dash; any legal non-empty real
name is preserved verbatim). R2 adds the real-state territory contract (never a
fixed catalog literal) and automated startup-page PNG capture (zh-CN + en-US).
"""
import hashlib
import os
import sys
from datetime import datetime, timezone

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
os.environ.setdefault("PYTHONUTF8", "1")
os.environ.setdefault("PYTHONUNBUFFERED", "1")
os.environ.setdefault("PYTHONDONTWRITEBYTECODE", "1")

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(__file__))))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

import pytest
from PySide6.QtCore import QObject, QUrl, Slot
from PySide6.QtGui import QGuiApplication
from PySide6.QtQml import QQmlApplicationEngine, QQmlComponent
from PySide6.QtTest import QTest
from PySide6.QtQuick import QQuickItem

from src.api import session_api
from src.core.entities.player import Player, PlayerType
from src.tests._evidence_root import evidence_root
from src.ui.gui.localization import gui_localization
from src.ui.gui.session_store import (
    GuiSessionStore,
    SEAT_ACTIVE,
    SEAT_MASKED_PENDING,
)

QML_DIR = os.path.join(PROJECT_ROOT, "src", "ui", "gui", "qml")


def _load_cjk_font():
    """Harness-scoped CJK font load (never a product/global change).

    Offscreen Qt has no guaranteed CJK coverage; without this the startup page
    renders tofu boxes. Loading a Windows font keeps the PNG machine-readable so
    the evidence class can stay RENDER_AUTOMATED (screenshot spec §1.3).
    """
    from PySide6.QtGui import QFontDatabase

    for path in (
        "/mnt/c/Windows/Fonts/msyh.ttc",
        "/mnt/c/Windows/Fonts/simhei.ttf",
        "/mnt/c/Windows/Fonts/simsun.ttc",
    ):
        if os.path.exists(path) and QFontDatabase.addApplicationFont(path) != -1:
            return path
    return ""


def _app():
    return QGuiApplication.instance() or QGuiApplication([])


def _events(rounds=4):
    for _ in range(rounds):
        QGuiApplication.processEvents()
        QTest.qWait(5)


def _has_cjk(text):
    for ch in text or "":
        if "\u4e00" <= ch <= "\u9fff":
            return True
    return False


def _single_human_state(scenario="gui_prototype.json"):
    """Hot-seat session with EXACTLY one actual HUMAN (default scenario is 1H2AI)."""
    result = session_api.create_gui_hotseat_session(scenario_file=scenario)
    assert result["success"], result.get("message")
    state = result["data"]["state"]
    pids = [p.player_id for p in state.get_all_players()]
    if len(pids) > 1:
        for pid in pids[1:]:
            old = state.get_player(pid)
            state.remove_player(pid)
            state.add_player(Player(player_id=pid, faction_id=old.faction_id,
                                    player_type=PlayerType.AI))
        state.set_turn_order([pids[0]])
        state.set_current_player(pids[0])
    return state, pids


def _store_for(state, pids):
    store = GuiSessionStore(state, neutral_startup=True)
    store.initialize(pids[0])
    return store


class _Barrier:
    """Synchronous witness used by the existing activation chain."""

    def __init__(self):
        self.calls = []

    def show_pending(self, txn, faction, mode=""):
        self.calls.append(("pending", txn, faction, mode))
        return True

    def arm_barrier(self, txn):
        self.calls.append(("arm", txn))
        return True

    def request_unmask(self, txn):
        self.calls.append(("unmask", txn))
        return True

    def show_failure(self, txn, kind):
        self.calls.append(("failure", txn, kind))
        return True


# ===========================================================================
# Store: 1H detection / truthful values / activation timing
# ===========================================================================
def test_single_human_store_mode_is_actual_human_count():
    state, pids = _single_human_state()
    store = _store_for(state, pids)

    assert store.startupMode == "single_human"
    # 3H zero-change contract: actual HUMAN count is 3 for gr_f_3h.
    result = session_api.create_gui_hotseat_session(scenario_file="gr_f_3h.json")
    assert result["success"], result.get("message")
    state3 = result["data"]["state"]
    pids3 = [p.player_id for p in state3.get_all_players()]
    store3 = _store_for(state3, pids3)
    assert store3.startupMode == "multi_human"


def test_single_human_startup_reads_real_state_not_snapshot():
    state, pids = _single_human_state()
    store = _store_for(state, pids)

    assert store._snapshot == {}
    assert store.startupYearText == "公元前 282 年"
    assert store.startupTreasuryText == "142"
    assert store.startupTerritoryText == "意大利"
    assert store.handoffPendingFactionName == ""


def test_single_human_startup_does_not_activate_before_explicit_click():
    state, pids = _single_human_state()
    store = _store_for(state, pids)
    assert store.seatLifecycle == SEAT_MASKED_PENDING
    assert store.viewerPlayerId == ""

    store.setHandoffBarrierProvider(_Barrier())
    result = store.requestTakeover()
    assert result["accepted"] is True
    assert store.seatLifecycle == SEAT_ACTIVE


def test_startup_values_are_scenario_driven_142_vs_100():
    state142, pids142 = _single_human_state()
    store142 = _store_for(state142, pids142)
    assert store142.startupTreasuryText == "142"

    state100, pids100 = _single_human_state("gr_f_3h.json")
    store100 = _store_for(state100, pids100)
    assert store100.startupMode == "single_human"
    assert store100.startupTreasuryText == "100"
    assert store100.startupYearText == "公元前 282 年"


def test_missing_values_render_em_dash_never_zero_or_empty():
    state, pids = _single_human_state()
    store = _store_for(state, pids)

    state.turn.year = None
    state.treasury = None
    state._provinces.pop(0)
    assert store.startupYearText == "—"
    assert store.startupTreasuryText == "—"
    assert store.startupTerritoryText == "—"


def test_territory_value_is_real_state_name_not_fixed_catalog_literal():
    """AC-01/N5: the value must come from province.name, never fixed Italy."""
    state, pids = _single_human_state()
    store = _store_for(state, pids)
    province = state.get_province(0)
    assert province is not None
    assert province.name == "意大利"

    # Known canonical value: localized (translation), still state-derived.
    assert store.startupTerritoryText == "意大利"
    try:
        gui_localization.setLocale("en-US")
        assert store.startupTerritoryText == "Italy"
    finally:
        gui_localization.setLocale("zh-CN")

    # A different non-empty real state name must be preserved verbatim (zh).
    province._name = "Latium"
    assert store.startupTerritoryText == "Latium"
    assert "意大利" not in store.startupTerritoryText
    assert "Italy" not in store.startupTerritoryText


def test_unregistered_nonempty_territory_is_preserved_verbatim():
    """F1(1)/N5: real names are shown as-is; only None/missing -> `—`."""
    state, pids = _single_human_state()
    store = _store_for(state, pids)
    province = state.get_province(0)

    # zh oracle: verbatim real name, no catalog substitution.
    province._name = "Latium"
    assert store.startupTerritoryText == "Latium"

    # en oracle: another verbatim real name under en-US.
    province._name = "Magna Graecia"
    try:
        gui_localization.setLocale("en-US")
        assert store.startupTerritoryText == "Magna Graecia"
        assert "Italy" not in store.startupTerritoryText
    finally:
        gui_localization.setLocale("zh-CN")

    # Only a genuinely missing/unparsable value falls back to the placeholder.
    province._name = None
    assert store.startupTerritoryText == "—"


def test_homeland_suffix_is_i18n_and_only_for_homeland_province():
    """F1(2): the (本土) suffix resolves through the catalog, not QML literal."""
    state, pids = _single_human_state()
    store = _store_for(state, pids)

    assert store.startupTerritorySuffix == "(本土)"
    try:
        gui_localization.setLocale("en-US")
        assert store.startupTerritorySuffix == "(homeland)"
    finally:
        gui_localization.setLocale("zh-CN")

    # The startup page reads province 0; when it is absent the suffix must not
    # fabricate a homeland marker for a missing value.
    state._provinces.pop(0)
    assert store.startupTerritorySuffix == ""


def test_locale_switch_reformats_store_values():
    state, pids = _single_human_state()
    store = _store_for(state, pids)
    try:
        gui_localization.setLocale("en-US")
        assert store.startupYearText == "282 BC"
        assert store.startupTerritoryText == "Italy"
    finally:
        gui_localization.setLocale("zh-CN")


# ===========================================================================
# Real QML overlay (production PlayerHandoffOverlay.qml)
# ===========================================================================
_WRAPPER = """
import QtQuick 2.15
import QtQuick.Window 2.15
import "shell"
Window {
    id: win
    width: 1440; height: 900
    visible: true
    PlayerHandoffOverlay { id: ov; anchors.fill: parent }
}
"""


def _find(root, object_name):
    if hasattr(root, "findChild"):
        return root.findChild(QObject, object_name)
    return None


def _visible_copy(win):
    out = []
    for node in win.findChildren(QQuickItem):
        try:
            text = node.property("text")
        except Exception:
            continue
        if text and node.isVisible():
            out.append(str(text))
    return out


@pytest.fixture
def startup_runtime():
    _app()
    _load_cjk_font()
    state, pids = _single_human_state()
    store = _store_for(state, pids)

    eng = QQmlApplicationEngine()
    eng.setOutputWarningsToStandardError(False)
    eng.addImportPath(QML_DIR)

    theme_component = QQmlComponent(eng)
    theme_component.loadUrl(QUrl.fromLocalFile(os.path.join(QML_DIR, "theme", "Theme.qml")))
    assert not theme_component.isError(), theme_component.errorString()
    theme = theme_component.create()

    class _AppStub(QObject):
        @Slot(str, result=bool)
        def confirmHandoff(self, next_player_id):
            return True

    eng.rootContext().setContextProperty("theme", theme)
    eng.rootContext().setContextProperty("sessionStore", store)
    eng.rootContext().setContextProperty("guiApp", _AppStub())

    comp = QQmlComponent(eng)
    comp.setData(_WRAPPER.encode("utf-8"),
                 QUrl.fromLocalFile(os.path.join(QML_DIR, "_w2a_overlay_wrapper.qml")))
    assert not comp.isError(), comp.errorString()
    win = comp.create()
    assert win is not None
    _events()
    overlay = win.findChild(QObject, "playerHandoffOverlay")
    assert overlay is not None
    win._refs = (eng, theme, store, comp)
    yield win, overlay, store
    win.close()
    _events(1)


def _pending_copy(win):
    out = {}
    for name in ("startupIntroTitle", "startupIntroDescription", "startupIntroYear",
                 "startupIntroTreasury", "startupIntroTerritory"):
        item = _find(win, name)
        assert item is not None, name
        out[name] = item.property("text")
    return out


def test_single_human_overlay_renders_frozen_copy(startup_runtime):
    win, overlay, store = startup_runtime
    overlay.showMaskedStartup("", "single_human")
    _events()

    assert overlay.property("startupIntro") is True
    assert overlay.property("pendingFactionName") == ""
    assert _find(win, "grHandoffStart").property("text") == "开始游戏"
    assert _pending_copy(win) == {
        "startupIntroTitle": "【游戏介绍】",
        "startupIntroDescription": "基于罗马共和国历史背景的政治策略游戏",
        "startupIntroYear": "开始年份：公元前 282 年",
        "startupIntroTreasury": "国库资金：142 塔兰特",
        "startupIntroTerritory": "罗马领土：意大利(本土)",
    }
    assert overlay.property("dialogAccessibleName") == "游戏介绍"


def test_single_human_overlay_switches_locale_without_residue(startup_runtime):
    win, overlay, store = startup_runtime
    overlay.showMaskedStartup("", "single_human")
    _events()
    try:
        gui_localization.setLocale("en-US")
        _events()

        assert _find(win, "grHandoffStart").property("text") == "Start Game"
        assert _pending_copy(win) == {
            "startupIntroTitle": "[Game Overview]",
            "startupIntroDescription": "A political strategy game set in the Roman Republic",
            "startupIntroYear": "Start year: 282 BC",
            "startupIntroTreasury": "Treasury: 142 Talents",
            "startupIntroTerritory": "Roman territory: Italy (homeland)",
        }
        assert overlay.property("dialogAccessibleName") == "Game Overview"

        visible_copy = _visible_copy(win)
        assert visible_copy, "no visible copy found"
        for text in visible_copy:
            assert not _has_cjk(text), f"Chinese residue: {text!r}"
    finally:
        gui_localization.setLocale("zh-CN")


def test_single_human_overlay_missing_values_render_bare_em_dash(startup_runtime):
    """N5 at the rendered line level: missing year/treasury/territory -> `—`."""
    win, overlay, store = startup_runtime
    overlay.showMaskedStartup("", "single_human")
    _events()

    store._state.turn.year = None
    store._state.treasury = None
    store._state._provinces.pop(0)
    store.startupChanged.emit()
    _events()

    copy = _pending_copy(win)
    assert copy["startupIntroYear"] == "—"
    assert copy["startupIntroTreasury"] == "—"
    assert copy["startupIntroTerritory"] == "—"


def test_single_human_overlay_has_no_faction_identity(startup_runtime):
    win, overlay, store = startup_runtime
    overlay.showMaskedStartup("", "single_human")
    _events()

    assert overlay.property("pendingFactionName") == ""
    faction = state_faction_name(store._state, store._state.get_current_player().player_id)
    assert faction
    visible_copy = _visible_copy(win)
    assert all(faction not in text for text in visible_copy)
    assert faction not in (overlay.property("dialogAccessibleName") or "")


def state_faction_name(state, player_id):
    player = state.get_player(player_id)
    return state.get_faction(player.faction_id).name


def test_three_human_overlay_is_byte_semantics_unchanged(startup_runtime):
    win, overlay, store = startup_runtime
    overlay.showMaskedPending("Optimates")
    _events()

    assert overlay.property("startupIntro") is False
    assert _find(win, "startupIntroBlock").property("visible") is False
    assert _find(win, "handoffPendingLabel").property("text") == "下一位：Optimates"
    assert _find(win, "handoffPendingInstruction").property("text") == "请该派系玩家点击“接管”。"
    assert _find(win, "grHandoffStart").property("text") == "接管"


# ===========================================================================
# F3 — automated startup-page pixels (zh-CN + en-US)
# ===========================================================================
def _sha256_file(path):
    digest = hashlib.sha256()
    with open(path, "rb") as fh:
        for chunk in iter(lambda: fh.read(65536), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _grab_png(win, path):
    """Render the live production overlay window and save its pixels."""
    from PySide6.QtGui import QGuiApplication

    win.show()
    for _ in range(8):
        QGuiApplication.processEvents()
        QTest.qWait(25)
    image = win.grabWindow()
    assert image is not None and not image.isNull(), "grabWindow returned no image"
    assert image.width() > 0 and image.height() > 0
    assert image.save(path), f"PNG save failed: {path}"
    return image.width(), image.height()


def test_capture_startup_page_zh_and_en_png(startup_runtime, tmp_path):
    """G4 AC-01/04/06: real startup page pixels, one PNG per locale."""
    win, overlay, store = startup_runtime
    shot_dir = evidence_root(tmp_path, namespace="w2a-startup").ensure_dir()
    gui_localization.setLocale("zh-CN")

    overlay.showMaskedStartup("", "single_human")
    _events(8)

    zh_path = os.path.join(shot_dir, "startup_zh.png")
    zh_w, zh_h = _grab_png(win, zh_path)
    assert _find(win, "grHandoffStart").property("text") == "开始游戏"
    assert _pending_copy(win)["startupIntroTerritory"] == "罗马领土：意大利(本土)"

    try:
        gui_localization.setLocale("en-US")
        _events(8)
        assert _find(win, "grHandoffStart").property("text") == "Start Game"
        assert _pending_copy(win)["startupIntroTerritory"] == (
            "Roman territory: Italy (homeland)"
        )
        en_path = os.path.join(shot_dir, "startup_en.png")
        en_w, en_h = _grab_png(win, en_path)
    finally:
        gui_localization.setLocale("zh-CN")

    zh_sha = _sha256_file(zh_path)
    en_sha = _sha256_file(en_path)
    captured_at = datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")
    log_path = os.path.join(shot_dir, "capture.log")
    with open(log_path, "w", encoding="utf-8", newline="\n") as fh:
        fh.write("W2a startup-page automated capture\n")
        fh.write(
            "command: /home/openclaw/.openclaw/safe-bin/oc-pytest-run -m pytest "
            "src/tests/test_gui/test_w2a_startup_intro.py::"
            "test_capture_startup_page_zh_and_en_png -v --tb=short\n"
        )
        fh.write(f"captured_at_utc: {captured_at}\n")
        fh.write(
            "identity: task=EOR20261013-02/W2a-R3; product_head="
            "bc9dafa1eacdd1c51c5f9272cbff1952f39d4e81; "
            "worktree=8-file-W2a-write-face; qpa=offscreen; "
            "fixture=test_w2a_startup_intro.py::test_capture_startup_page_zh_and_en_png\n"
        )
        fh.write(f"cjk_font: {_load_cjk_font() or 'unavailable'}\n")
        fh.write(
            f"locale=zh-CN file=startup_zh.png size={zh_w}x{zh_h} "
            f"sha256={zh_sha} render_class=RENDER_AUTOMATED\n"
        )
        fh.write(
            f"locale=en-US file=startup_en.png size={en_w}x{en_h} "
            f"sha256={en_sha} render_class=RENDER_AUTOMATED\n"
        )

    assert zh_sha and en_sha
