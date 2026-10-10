"""
GUI localization authority for shell-level copy.

Single runtime authority for GUI locale state and localized copy resolution.
The catalog source of truth is ``data/i18n/*.json`` (the same files consumed by
the core/CLI i18n loader, loaded independently here -- no second catalog).

This module replaces the previous in-module ``_TEXT`` dictionary (GUI-P0-02A).
``gui_text`` is retained as a compatibility shell over
``GuiLocalization.textParams`` so existing Store call sites keep working.
"""
import json
import logging
import os
from typing import Any, Dict, List, Optional

from PySide6.QtCore import QObject, Property, Signal, Slot

logger = logging.getLogger("EOR-GUI")

DEFAULT_LOCALE = "zh-CN"

# `src/ui/gui/localization.py` -> repo root (4 levels up).
_REPO_ROOT = os.path.dirname(
    os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
)
_I18N_DIR = os.path.join(_REPO_ROOT, "data", "i18n")
_CONFIG_PATH = os.path.join(_REPO_ROOT, "data", "config", "game_config.json")


def _read_catalog_file(locale: str) -> Optional[Dict[str, str]]:
    """Load a catalog JSON file.

    Returns ``None`` when the file is missing, malformed, or not a JSON object
    (``FC-GI18N-04``: such a locale is treated as unavailable; never raise).
    """
    path = os.path.join(_I18N_DIR, f"{locale}.json")
    try:
        with open(path, "r", encoding="utf-8-sig") as fh:
            data = json.load(fh)
    except FileNotFoundError:
        logger.warning("i18n catalog missing: %s", path)
        return None
    except (ValueError, OSError) as exc:
        logger.warning("i18n catalog malformed: %s (%s)", path, exc)
        return None
    if not isinstance(data, dict):
        logger.warning("i18n catalog is not a JSON object: %s", path)
        return None
    return {str(key): str(value) for key, value in data.items()}


def _discover_locales() -> List[str]:
    """Discover available locales from ``data/i18n/*.json`` (sorted)."""
    try:
        names = os.listdir(_I18N_DIR)
    except OSError as exc:
        logger.warning("i18n directory unavailable: %s (%s)", _I18N_DIR, exc)
        return []
    locales = [os.path.splitext(name)[0] for name in names if name.endswith(".json")]
    return sorted(set(locales))


def _detect_initial_locale(available: List[str]) -> str:
    """Initial locale = ``game_config.language`` when supported, else default."""
    try:
        with open(_CONFIG_PATH, "r", encoding="utf-8-sig") as fh:
            config = json.load(fh)
        configured = config.get("language")
    except (FileNotFoundError, ValueError, OSError) as exc:
        logger.warning("game_config language unavailable (%s); using default", exc)
        configured = None
    if configured in available:
        return configured
    return DEFAULT_LOCALE


class GuiLocalization(QObject):
    """Single runtime authority for GUI locale state and copy resolution.

    Deterministic fallback (``FC-GI18N-04``):
    ``current locale -> default locale (zh-CN) -> key literal``.
    """

    localeChanged = Signal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self._available: List[str] = _discover_locales()
        self._default_catalog: Dict[str, str] = _read_catalog_file(DEFAULT_LOCALE) or {}
        if DEFAULT_LOCALE not in self._available or not self._default_catalog:
            # FC-GI18N-04: a missing/broken zh-CN catalog is fail-closed.
            raise RuntimeError(
                f"Missing default locale catalog '{DEFAULT_LOCALE}' in {_I18N_DIR}"
            )
        # FC-GI18N-01: initial locale = game_config.json."language" when it is a
        # supported locale, else DEFAULT_LOCALE (deterministic fallback). The
        # configured value is read here (not hard-coded) so editing the config
        # and restarting takes effect.
        initial_locale: str = _detect_initial_locale(self._available)
        self._current: str = initial_locale
        self._current_catalog: Dict[str, str] = self._default_catalog
        self._catalog: Dict[str, str] = dict(self._default_catalog)
        self._load(initial_locale)

    # -- internals ---------------------------------------------------------
    def _load(self, locale: str) -> None:
        catalog = (
            self._default_catalog if locale == DEFAULT_LOCALE
            else _read_catalog_file(locale)
        )
        if catalog is None:
            # Unavailable target -> fall back to default deterministically.
            locale = DEFAULT_LOCALE
            catalog = self._default_catalog
        self._current = locale
        self._current_catalog = catalog
        merged = dict(self._default_catalog)
        merged.update(catalog)
        self._catalog = merged

    # -- properties (notify=localeChanged) ---------------------------------
    def _get_current_locale(self) -> str:
        return self._current

    def _get_available_locales(self) -> List[str]:
        return list(self._available)

    def _get_catalog(self) -> Dict[str, str]:
        return dict(self._catalog)

    currentLocale = Property(str, _get_current_locale, notify=localeChanged)
    availableLocales = Property(list, _get_available_locales, notify=localeChanged)
    catalog = Property(dict, _get_catalog, notify=localeChanged)

    # -- slots -------------------------------------------------------------
    @Slot(str)
    def setLocale(self, locale: str) -> None:
        """Switch locale. Unsupported locale / same locale -> no-op (idempotent)."""
        if locale not in self._available:
            logger.warning("setLocale ignored (unsupported locale): %s", locale)
            return
        if locale == self._current:
            return
        catalog = (
            self._default_catalog if locale == DEFAULT_LOCALE
            else _read_catalog_file(locale)
        )
        if catalog is None:
            logger.warning("setLocale ignored (catalog unavailable): %s", locale)
            return
        self._current = locale
        self._current_catalog = catalog
        merged = dict(self._default_catalog)
        merged.update(catalog)
        self._catalog = merged
        self.localeChanged.emit()

    @Slot(str, result=str)
    def text(self, key: str) -> str:
        """Resolve a key; missing key -> key literal (never raises)."""
        return self._catalog.get(key, key)

    @Slot(str, dict, result=str)
    def textParams(self, key: str, params: Dict[str, Any]) -> str:
        """Resolve a key and substitute ``{param}`` placeholders.

        Missing parameters keep their ``{param}`` literal; extra parameters are
        ignored; never raises (``FC-GI18N-04``).
        """
        template = self._catalog.get(key, key)
        if not params:
            return template
        try:
            return template.format(**params)
        except (KeyError, IndexError):
            return template


gui_localization = GuiLocalization()


def get_gui_localization() -> GuiLocalization:
    """Return the process-wide GUI localization singleton."""
    return gui_localization


def gui_text(key: str, locale: str = DEFAULT_LOCALE, **kwargs: Any) -> str:
    """Compatibility shell over :meth:`GuiLocalization.textParams`.

    The ``locale`` parameter is retained for call-site compatibility only and is
    deprecated / ignored -- resolution always follows the active GUI locale.
    """
    return gui_localization.textParams(key, kwargs)
