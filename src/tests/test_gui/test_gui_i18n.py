"""
GUI-I18N S1 — localization authority tests.

Covers the frozen contract slice S1 (Python side only):
  * locale discovery / valid initial locale   (FC-GI18N-01, AC-01/02)
  * legal locale switching in a single session (FC-GI18N-05, AC-03)
  * unsupported locale is a no-op              (FC-GI18N-04, AC-07)
  * missing-key deterministic fallback         (FC-GI18N-04, AC-07)
  * parameter substitution / missing / extra   (FC-GI18N-04, AC-06/07)
  * localeChanged emission + idempotency       (FC-GI18N-01/05, AC-03/13)
  * catalog is the single source of truth       (FC-GI18N-02/09, AC-08)
  * state neutrality (no GameState mutation)   (FC-GI18N-06, AC-04)
"""
import os
import sys

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
os.environ.setdefault("PYTHONUTF8", "1")
os.environ.setdefault("PYTHONDONTWRITEBYTECODE", "1")

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(__file__))))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

import pytest

from src.ui.gui import localization as localization_module
from src.ui.gui.localization import (
    DEFAULT_LOCALE,
    GuiLocalization,
    get_gui_localization,
    gui_localization,
    gui_text,
)

_PHASE_ORDER = [
    "mortality",
    "revenue",
    "forum",
    "population",
    "senate",
    "combat",
    "resolution",
]


@pytest.fixture(autouse=True)
def _reset_locale():
    """Keep the singleton at the default locale before/after every test."""
    gui_localization.setLocale(DEFAULT_LOCALE)
    yield
    gui_localization.setLocale(DEFAULT_LOCALE)


# --- FC-GI18N-01: locale discovery + valid initial locale ---------------------

def test_available_locales_discovered_from_catalog():
    available = gui_localization.availableLocales
    assert "zh-CN" in available
    assert "en-US" in available
    assert available == sorted(available)


def test_initial_locale_is_valid_default():
    # data/config/game_config.json -> "language": "zh-CN"
    assert gui_localization.currentLocale == DEFAULT_LOCALE
    assert gui_localization.currentLocale in gui_localization.availableLocales


def test_constructor_reads_shipped_game_config():
    """FC-GI18N-01: startup locale follows the shipped game_config."language".

    Reality link: a freshly constructed authority (offscreen) starts in the
    locale declared by ``data/config/game_config.json`` when that value is a
    supported locale, else ``zh-CN``.
    """
    import json as _json

    with open(localization_module._CONFIG_PATH, "r", encoding="utf-8-sig") as fh:
        configured = _json.load(fh).get("language")

    fresh = GuiLocalization()

    if configured in fresh.availableLocales:
        assert fresh.currentLocale == configured
    else:
        assert fresh.currentLocale == DEFAULT_LOCALE
    assert fresh.currentLocale in fresh.availableLocales


def test_constructor_wires_configured_language(monkeypatch, tmp_path):
    """FC-GI18N-01: the constructor honours game_config."language" (not hard-coded).

    With a config declaring a supported locale, a fresh authority starts in
    that locale and resolves copy from it.
    """
    cfg = tmp_path / "game_config.json"
    cfg.write_text('{"language": "en-US"}', encoding="utf-8")
    monkeypatch.setattr(localization_module, "_CONFIG_PATH", str(cfg))

    fresh = GuiLocalization()

    assert fresh.currentLocale == "en-US"
    assert fresh.text("error_no_state") == "Please load a scenario first"


def test_constructor_falls_back_when_configured_language_unsupported(monkeypatch, tmp_path):
    """FC-GI18N-01: an unsupported config language falls back to zh-CN."""
    cfg = tmp_path / "game_config.json"
    cfg.write_text('{"language": "xx-XX"}', encoding="utf-8")
    monkeypatch.setattr(localization_module, "_CONFIG_PATH", str(cfg))

    fresh = GuiLocalization()

    assert fresh.currentLocale == DEFAULT_LOCALE


# --- FC-GI18N-05: single-session zh-CN -> en-US -> zh-CN ----------------------

def test_switch_locale_changes_resolution_and_back():
    assert gui_localization.text("error_no_state") == "请先加载场景"

    gui_localization.setLocale("en-US")
    assert gui_localization.currentLocale == "en-US"
    assert gui_localization.text("error_no_state") == "Please load a scenario first"

    gui_localization.setLocale(DEFAULT_LOCALE)
    assert gui_localization.currentLocale == DEFAULT_LOCALE
    assert gui_localization.text("error_no_state") == "请先加载场景"


# --- FC-GI18N-04: unsupported locale no-op ------------------------------------

def test_unsupported_locale_is_noop():
    before = gui_localization.currentLocale
    gui_localization.setLocale("xx-XX")
    assert gui_localization.currentLocale == before


def test_same_locale_is_idempotent_noop():
    gui_localization.setLocale("en-US")
    assert gui_localization.currentLocale == "en-US"
    gui_localization.setLocale("en-US")
    assert gui_localization.currentLocale == "en-US"


# --- FC-GI18N-04: missing key fallback ----------------------------------------

def test_missing_key_falls_back_to_key_literal():
    assert gui_localization.text("no.such.key.exists") == "no.such.key.exists"


def test_migrated_gui_key_resolves_and_en_falls_back_to_zh():
    # C2 migrated key resolves from the catalog in zh-CN.
    assert gui_localization.text("feedback.snapshot.refreshed") == "状态已刷新"
    # Non-proof GUI keys have no en value -> deterministic fallback to zh-CN.
    gui_localization.setLocale("en-US")
    assert gui_localization.text("feedback.snapshot.refreshed") == "状态已刷新"
    # ... while the core key does resolve in en.
    assert gui_localization.text("error_no_state") == "Please load a scenario first"


# --- FC-GI18N-04: parameter substitution --------------------------------------

def test_text_params_substitution_zh_and_en():
    assert gui_localization.textParams("error_phase_invalid", {"phase": "forum"}) == "未知阶段: forum"
    gui_localization.setLocale("en-US")
    assert gui_localization.textParams("error_phase_invalid", {"phase": "forum"}) == "Unknown phase: forum"


def test_text_params_missing_param_preserved():
    message = gui_localization.textParams("error_phase_invalid", {})
    assert message == "未知阶段: {phase}"
    assert "{phase}" in message


def test_text_params_extra_param_ignored():
    assert gui_localization.textParams("error_no_state", {"unused": 1}) == "请先加载场景"


# --- FC-GI18N-01/05: localeChanged emission -----------------------------------

def test_locale_changed_emitted_only_on_real_switch():
    events = []

    def _on_changed():
        events.append(gui_localization.currentLocale)

    gui_localization.localeChanged.connect(_on_changed)
    try:
        gui_localization.setLocale("en-US")
        assert events == ["en-US"]
        gui_localization.setLocale("en-US")  # idempotent -> no emit
        assert events == ["en-US"]
        gui_localization.setLocale("xx-XX")  # unsupported -> no emit
        assert events == ["en-US"]
    finally:
        gui_localization.localeChanged.disconnect(_on_changed)


# --- FC-GI18N-02/09: catalog is the single source of truth --------------------

def test_catalog_is_single_source_of_truth():
    assert not hasattr(localization_module, "_TEXT")
    assert not hasattr(gui_localization, "_TEXT")
    # compatibility shell resolves from the catalog
    assert gui_text("feedback.snapshot.refreshed") == "状态已刷新"
    assert gui_text("feedback.phase.selected", name="天命") == "已切换到天命阶段。"
    assert gui_text("missing.shell.key") == "missing.shell.key"


def test_factory_returns_singleton():
    assert isinstance(gui_localization, GuiLocalization)
    assert get_gui_localization() is gui_localization


# --- FC-GI18N-06: state neutrality --------------------------------------------

def test_locale_switch_is_state_neutral():
    from src.api import session_api

    result = session_api.create_gui_prototype_session()
    assert result["success"], result.get("message")
    state = result["data"]["state"]

    def fingerprint():
        current = state.get_current_player()
        return (
            state.turn.turn_number if state.turn else None,
            state.treasury,
            current.player_id if current else None,
            tuple(sorted(p.player_id for p in state.get_all_players())),
            len(state.get_living_members()),
            tuple(state.is_phase_executed(phase_id) for phase_id in _PHASE_ORDER),
        )

    before = fingerprint()
    gui_localization.setLocale("en-US")
    gui_localization.setLocale(DEFAULT_LOCALE)
    gui_localization.setLocale("xx-XX")
    after = fingerprint()

    assert after == before
