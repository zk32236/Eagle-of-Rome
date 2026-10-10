"""GUI-I18N S2 — QML proof-surface binding, reactivity, guard, catalog (slice S2).

Covers the frozen-contract slice S2 (QML side):
  * proof-surface copy resolves from the catalog           (FC-GI18N-02/08, AC-05)
  * reactive re-resolution on ``setLocale`` w/o restart    (FC-GI18N-05, AC-13)
  * direct C++ slot binding does NOT refresh (negative)    (FC-GI18N-05, B-14)
  * new-copy guard incl. ``\\uXXXX`` normalization          (FC-GI18N-07, AC-09)
  * missing / malformed catalog fallback                    (FC-GI18N-04, AC-07/OBS-2)
  * state neutrality across a live QML locale switch        (FC-GI18N-06, AC-04)
"""
import json
import os
import re
import sys

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
os.environ.setdefault("PYTHONUTF8", "1")
os.environ.setdefault("PYTHONDONTWRITEBYTECODE", "1")

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(__file__))))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

import pytest  # noqa: E402
from PySide6.QtCore import QObject, QUrl  # noqa: E402
from PySide6.QtGui import QGuiApplication  # noqa: E402
from PySide6.QtQml import QQmlApplicationEngine, QQmlComponent, qmlRegisterType  # noqa: E402

from src.api import session_api  # noqa: E402
from src.ui.gui import localization as localization_module  # noqa: E402
from src.ui.gui.localization import DEFAULT_LOCALE, gui_localization  # noqa: E402
from src.ui.gui.models.candidate_list_model import CandidateListModel  # noqa: E402
from src.ui.gui.models.event_list_model import EventListModel  # noqa: E402
from src.ui.gui.models.figure_list_model import FigureListModel  # noqa: E402
from src.ui.gui.session_store import GuiSessionStore  # noqa: E402

QML_DIR = os.path.join(PROJECT_ROOT, "src", "ui", "gui", "qml")
I18N_DIR = os.path.join(PROJECT_ROOT, "data", "i18n")

# The write-face QML fully key-ized by this slice (whole-file copy scan applies).
FULLY_KEYED_QML = [
    os.path.join(QML_DIR, "i18n", "L10n.qml"),
    os.path.join(QML_DIR, "i18n", "GuiText.qml"),
    os.path.join(QML_DIR, "shell", "TopStatusBar.qml"),
    os.path.join(QML_DIR, "shell", "PhaseRail.qml"),
    os.path.join(QML_DIR, "stages", "MortalityStage.qml"),
]

# §A proof-surface keys — required in BOTH catalogs (catalog-key-map §A).
PROOF_KEYS = [
    "topStatusBar.stat.treasury", "topStatusBar.stat.faction",
    "topStatusBar.stat.influence", "topStatusBar.stat.stability",
    "topStatusBar.stat.war", "topStatusBar.turn",
    "phase.mortality.name", "phase.revenue.name", "phase.forum.name",
    "phase.population.name", "phase.senate.name", "phase.combat.name",
    "phase.resolution.name", "phase.mortality.subtitle",
    "phase.mortality.description", "mortality.title", "mortality.intro",
    "mortality.resolved", "mortality.events.title", "mortality.prompt.body",
    "mortality.death.faction_suffix", "mortality.faction.none",
    "mortality.confiscate.wealth", "mortality.confiscate.land",
    "mortality.action.execute", "mortality.action.done",
]


@pytest.fixture(autouse=True)
def _reset_locale():
    gui_localization.setLocale(DEFAULT_LOCALE)
    yield
    gui_localization.setLocale(DEFAULT_LOCALE)


class _DummyGuiApp(QObject):
    pass


# Keep every QML engine / window alive: collecting a live QQmlApplicationEngine
# with created objects is a known PySide6 crash/deadlock source under suite load.
_LIVE = []


def _get_app():
    return QGuiApplication.instance() or QGuiApplication([])


def _create_engine():
    """Production-shaped engine (theme + sessionStore + guiApp + localization)."""
    _get_app()
    result = session_api.create_gui_prototype_session()
    assert result["success"], result.get("message")
    state = result["data"]["state"]
    store = GuiSessionStore(state)
    store.initialize(result["data"]["human_players"][0])
    store.selectPhase("mortality")

    engine = QQmlApplicationEngine()
    engine.addImportPath(QML_DIR)
    for model in (FigureListModel, CandidateListModel, EventListModel):
        qmlRegisterType(model, "EOR.Models", 1, 0, model.__name__)

    theme_component = QQmlComponent(engine)
    theme_component.loadUrl(QUrl.fromLocalFile(os.path.join(QML_DIR, "theme", "Theme.qml")))
    assert not theme_component.isError(), theme_component.errorString()
    theme = theme_component.create()
    assert theme is not None

    engine.rootContext().setContextProperty("theme", theme)
    engine.rootContext().setContextProperty("sessionStore", store)
    engine.rootContext().setContextProperty("guiApp", _DummyGuiApp())
    engine.rootContext().setContextProperty("localization", gui_localization)
    engine._test_refs = (store, theme, state)
    _LIVE.append(engine)
    engine.load(QUrl.fromLocalFile(os.path.join(QML_DIR, "Main.qml")))
    _get_app().processEvents()
    roots = engine.rootObjects()
    assert roots, "Main.qml loaded with no root object"
    return engine, roots[0], store, state


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


def _all_texts(root):
    out = []
    for item in _walk(root):
        try:
            text = item.property("text")
        except Exception:
            continue
        if isinstance(text, str) and text:
            out.append(text)
    return out


def _fingerprint(state):
    current = state.get_current_player()
    return (
        state.turn.turn_number if state.turn else None,
        state.treasury,
        current.player_id if current else None,
        tuple(sorted(p.player_id for p in state.get_all_players())),
        len(state.get_living_members()),
    )


# --- AC-05 / AC-13: proof surface resolves + reactive re-resolution -----------

def test_proof_surface_copy_resolves_from_catalog():
    engine, root, _store, _state = _create_engine()
    texts = _all_texts(root)
    joined = " ".join(texts)
    # TopStatusBar stat labels + PhaseRail names + MortalityStage prompt body.
    assert "国库" in texts, texts
    assert "天命" in texts, texts
    assert "点击下方「执行天命」按钮，触发一个随机事件。" in joined, joined
    assert "topStatusBar.stat.treasury" not in joined, joined
    assert "mortality.prompt.body" not in joined, joined
    assert "phase.mortality.name" not in joined, joined


def test_locale_switch_re_resolves_live_without_restart():
    engine, root, _store, state = _create_engine()
    before = _fingerprint(state)

    topbar = root.findChild(QObject, "topStatusBar")
    rail = root.findChild(QObject, "phaseRail")
    mort = root.findChild(QObject, "mortalityStage")
    assert topbar is not None and rail is not None and mort is not None

    def snapshot():
        return (_all_texts(topbar), _all_texts(rail), _all_texts(mort))

    zh_top, zh_rail, zh_mort = snapshot()
    assert "国库" in zh_top and "派系" in zh_top, zh_top
    assert "天命" in zh_rail and "决算" in zh_rail, zh_rail
    assert any("点击下方「执行天命」" in t for t in zh_mort), zh_mort

    gui_localization.setLocale("en-US")
    _get_app().processEvents()
    en_top, en_rail, en_mort = snapshot()
    assert "Treasury" in en_top and "Faction" in en_top, en_top
    assert "国库" not in en_top, en_top
    assert "Mortality" in en_rail and "Resolution" in en_rail, en_rail
    assert "天命" not in en_rail, en_rail
    assert any("Execute Mortality" in t for t in en_mort), en_mort

    gui_localization.setLocale(DEFAULT_LOCALE)
    _get_app().processEvents()
    back_top, back_rail, _back_mort = snapshot()
    assert "国库" in back_top and "派系" in back_top, back_top
    assert "天命" in back_rail, back_rail

    # AC-04: locale switching never mutates the authoritative game state.
    assert _fingerprint(state) == before


def test_direct_slot_binding_does_not_refresh_negative():
    """B-14: binding straight to the C++ slot has no QML catalog dependency."""
    _get_app()
    engine = QQmlApplicationEngine()
    engine.rootContext().setContextProperty("localization", gui_localization)
    _LIVE.append(engine)
    comp = QQmlComponent(engine)
    comp.setData(
        b'import QtQuick 2.15\nQtObject { property string probe: localization.text("mortality.resolved") }',
        QUrl(""),
    )
    assert not comp.isError(), comp.errorString()
    obj = comp.create()
    assert obj is not None, comp.errorString()
    _LIVE.append(obj)
    assert obj.property("probe") == "天命已执行"
    gui_localization.setLocale("en-US")
    _get_app().processEvents()
    assert obj.property("probe") == "天命已执行"  # NOT re-evaluated (no catalog read)


def test_l10n_binding_refreshes_positive_control():
    """Positive counterpart of B-14: a binding through L10n.t() DOES refresh."""
    _get_app()
    engine = QQmlApplicationEngine()
    engine.addImportPath(QML_DIR)
    engine.rootContext().setContextProperty("localization", gui_localization)
    _LIVE.append(engine)
    comp = QQmlComponent(engine)
    comp.setData(
        b'import QtQuick 2.15\nimport "i18n"\nQtObject { property string probe: L10n.t("mortality.resolved") }',
        QUrl.fromLocalFile(os.path.join(QML_DIR, "_i18n_probe_tmp.qml")),
    )
    assert not comp.isError(), comp.errorString()
    obj = comp.create()
    assert obj is not None, comp.errorString()
    _LIVE.append(obj)
    assert obj.property("probe") == "天命已执行"
    gui_localization.setLocale("en-US")
    _get_app().processEvents()
    assert obj.property("probe") == "Mortality resolved"


# --- AC-09 / FC-GI18N-07: new-copy guard --------------------------------------

_COPY_ATTRS = ("text", "label", "title", "confirmText", "cancelText")
_COPY_ATTR_RE = re.compile(r"\b(text|label|title|confirmText|cancelText)\s*:")
_CJK_RE = re.compile(r"[\u3000-\u303f\u3400-\u4dbf\u4e00-\u9fff\uf900-\ufaff\uff00-\uffef]")
_UNICODE_ESCAPE_RE = re.compile(r"\\u([0-9a-fA-F]{4})")


def _strip_comments(src):
    src = re.sub(r"/\*.*?\*/", "", src, flags=re.S)
    return re.sub(r"//[^\n]*", "", src)


def _normalize_unicode_escapes(src):
    return _UNICODE_ESCAPE_RE.sub(lambda m: chr(int(m.group(1), 16)), src)


def _copy_literals(src):
    """Extract copy-attribute string literals (``\\uXXXX`` normalized)."""
    cleaned = _normalize_unicode_escapes(_strip_comments(src))
    literals = []
    for line in cleaned.splitlines():
        if not _COPY_ATTR_RE.search(line):
            continue
        literals.extend(re.findall(r'"([^"]*)"', line))
        literals.extend(re.findall(r"'([^']*)'", line))
    return literals


def test_new_copy_guard_changed_qml_has_no_scattered_cjk():
    offenders = {}
    for path in FULLY_KEYED_QML:
        with open(path, "r", encoding="utf-8") as fh:
            src = fh.read()
        hits = [lit for lit in _copy_literals(src) if _CJK_RE.search(lit)]
        if hits:
            offenders[os.path.basename(path)] = hits
    assert offenders == {}, offenders


def test_new_copy_guard_detects_escaped_cjk():
    """The guard must normalize ``\\uXXXX`` and still flag escaped CJK."""
    snippet = 'Text { text: "\\u5929\\u547d\\u9636\\u6bb5" }'
    literals = _copy_literals(snippet)
    assert literals == ["天命阶段"], literals
    assert any(_CJK_RE.search(lit) for lit in literals)


def test_gameshell_restricted_hunks_are_keyed():
    path = os.path.join(QML_DIR, "shell", "GameShell.qml")
    with open(path, "r", encoding="utf-8") as fh:
        src = fh.read()
    # old inline copy is gone
    assert '"🃏 " + GuiText.mortalityTitle' not in src
    assert '"⚡ 执行天命" ?' not in src
    assert '? "⚡ 执行天命" : "✓ 已执行"' not in src
    assert "selectedPhaseSummary.description || GuiText.mortalityIntro" not in src
    # new keyed forms are present
    assert 'L10n.t("mortality.title")' in src
    assert 'L10n.t("mortality.action.execute")' in src
    assert 'L10n.t("mortality.action.done")' in src
    assert "selectedPhaseSummary.description_key" in src


def test_gui_text_properties_bind_catalog_and_get_removed():
    path = os.path.join(QML_DIR, "i18n", "GuiText.qml")
    with open(path, "r", encoding="utf-8") as fh:
        src = fh.read()
    assert 'treasuryPrefix: I18n.L10n.t("shell.treasury.prefix")' in src
    assert 'executeMortality: I18n.L10n.t("mortality.action.execute")' in src
    assert 'senateInfluenceLabel: I18n.L10n.t("senate.label.influence")' in src
    assert "function get(" not in src


# --- AC-05 / AC-06: proof-surface key resolution (zh + en) --------------------

_PROOF_ZH_EN = {
    "topStatusBar.stat.treasury": ("国库", "Treasury"),
    "topStatusBar.stat.faction": ("派系", "Faction"),
    "topStatusBar.stat.influence": ("影响力", "Influence"),
    "topStatusBar.stat.stability": ("稳定度", "Stability"),
    "topStatusBar.stat.war": ("战争", "War"),
    "topStatusBar.turn": ("回合 {turn}", "Turn {turn}"),
    "phase.mortality.name": ("天命", "Mortality"),
    "phase.revenue.name": ("收入", "Revenue"),
    "phase.forum.name": ("广场", "Forum"),
    "phase.population.name": ("人口", "Population"),
    "phase.senate.name": ("元老院", "Senate"),
    "phase.combat.name": ("战斗", "War"),
    "phase.resolution.name": ("决算", "Resolution"),
    "mortality.title": ("天命阶段", "Mortality Phase"),
    "mortality.resolved": ("天命已执行", "Mortality resolved"),
    "mortality.action.execute": ("执行天命", "Execute Mortality"),
    "mortality.action.done": ("已执行", "Executed"),
    "mortality.faction.none": ("无派系", "No faction"),
}


def test_proof_surface_keys_resolve_zh_and_en():
    for key, (zh, en) in _PROOF_ZH_EN.items():
        gui_localization.setLocale(DEFAULT_LOCALE)
        assert gui_localization.text(key) == zh, key
        gui_localization.setLocale("en-US")
        assert gui_localization.text(key) == en, key


def test_proof_surface_param_keys_resolve_zh_and_en():
    gui_localization.setLocale(DEFAULT_LOCALE)
    assert gui_localization.textParams("topStatusBar.turn", {"turn": 3}) == "回合 3"
    assert gui_localization.textParams("mortality.confiscate.wealth", {"amount": 100}) == "损失财富 100 T（收归国库）"
    assert gui_localization.textParams(
        "mortality.death.faction_suffix", {"faction": "Optimates"}) == "（Optimates）"
    gui_localization.setLocale("en-US")
    assert gui_localization.textParams("topStatusBar.turn", {"turn": 3}) == "Turn 3"
    assert gui_localization.textParams(
        "mortality.confiscate.wealth", {"amount": 100}) == "Wealth lost 100 T (to treasury)"
    assert gui_localization.textParams(
        "mortality.death.faction_suffix", {"faction": "Optimates"}) == " (Optimates)"


def test_dto_phase_keys_resolve_from_catalog():
    gui_localization.setLocale(DEFAULT_LOCALE)
    assert gui_localization.text("phase.mortality.description") == \
        "抽取天命事件并应用死亡、丰收、和平、猛男或灾害等年度影响。"
    assert gui_localization.text("phase.status.current") == "当前"
    assert gui_localization.text("phase.status.completed") == "已完成"
    assert gui_localization.text("phase.disabled.not_current") == "该阶段不是当前阶段，暂不可操作"
    assert gui_localization.text("phase.disabled.not_player") == "当前 viewer 不是行动玩家，暂不可操作"


def test_proof_keys_present_in_both_catalogs():
    with open(os.path.join(I18N_DIR, "zh-CN.json"), "r", encoding="utf-8-sig") as fh:
        zh = json.load(fh)
    with open(os.path.join(I18N_DIR, "en-US.json"), "r", encoding="utf-8-sig") as fh:
        en = json.load(fh)
    for key in PROOF_KEYS:
        assert key in zh, key
        assert key in en, key


def test_en_gui_keys_subset_of_zh():
    with open(os.path.join(I18N_DIR, "zh-CN.json"), "r", encoding="utf-8-sig") as fh:
        zh = set(json.load(fh))
    with open(os.path.join(I18N_DIR, "en-US.json"), "r", encoding="utf-8-sig") as fh:
        en = set(json.load(fh))
    gui_prefixes = ("feedback.", "phase.", "query.", "topStatusBar.", "mortality.",
                    "shell.", "senate.", "stage.", "unit.")
    en_gui = {k for k in en if k.startswith(gui_prefixes)}
    assert en_gui <= zh, sorted(en_gui - zh)


# --- AC-07 / OBS-2: missing / malformed catalog fallback ----------------------

def test_read_catalog_missing_returns_none():
    assert localization_module._read_catalog_file("zz-ZZ") is None


def test_read_catalog_malformed_returns_none(tmp_path, monkeypatch):
    (tmp_path / "bad.json").write_text("{ this is not json", encoding="utf-8")
    monkeypatch.setattr(localization_module, "_I18N_DIR", str(tmp_path))
    assert localization_module._read_catalog_file("bad") is None


def test_read_catalog_non_object_returns_none(tmp_path, monkeypatch):
    (tmp_path / "list.json").write_text("[1, 2, 3]", encoding="utf-8")
    monkeypatch.setattr(localization_module, "_I18N_DIR", str(tmp_path))
    assert localization_module._read_catalog_file("list") is None


def test_setlocale_with_unavailable_catalog_is_noop(monkeypatch):
    monkeypatch.setattr(localization_module, "_read_catalog_file", lambda locale: None)
    before = gui_localization.currentLocale
    gui_localization.setLocale("en-US")
    assert gui_localization.currentLocale == before
