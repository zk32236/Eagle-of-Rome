"""GUI test bootstrap — GUI-I18N Foundation (slice S2).

Every GUI test harness in this package instantiates the *production* QML tree
directly (``QQmlApplicationEngine`` + ``setContextProperty``). From slice S2 the
shell resolves player-visible copy through the single GUI locale authority,
which is exposed to QML as the ``localization`` context property
(``app.py`` sets it once at startup — FC-GI18N-01). Each production engine
therefore always has ``localization`` available.

This bootstrap mirrors that production wiring for every engine created under
``src/tests/test_gui`` so the shared production QML renders the authoritative
copy (from ``data/i18n/*.json``) instead of unresolved key literals. It only
*adds* the same context property ``app.py`` installs; it does not filter,
suppress or alter any QML / Qt message.
"""
import os
import sys

import pytest

_PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
if _PROJECT_ROOT not in sys.path:
    sys.path.insert(0, _PROJECT_ROOT)

try:
    from PySide6.QtQml import QQmlApplicationEngine

    from src.ui.gui.localization import gui_localization
except Exception:  # pragma: no cover - keep collection resilient
    QQmlApplicationEngine = None
    gui_localization = None

if QQmlApplicationEngine is not None and gui_localization is not None:
    if not getattr(QQmlApplicationEngine, "_gui_i18n_context_patched", False):
        _orig_init = QQmlApplicationEngine.__init__

        def _init_with_gui_localization(self, *args, **kwargs):
            _orig_init(self, *args, **kwargs)
            try:
                self.rootContext().setContextProperty("localization", gui_localization)
            except Exception:  # pragma: no cover - defensive
                pass

        QQmlApplicationEngine.__init__ = _init_with_gui_localization
        QQmlApplicationEngine._gui_i18n_context_patched = True


@pytest.fixture(autouse=True)
def _gui_i18n_reset_locale():
    """Reset the shared GUI locale singleton to the default before/after each test.

    ``gui_localization`` is a process-wide singleton shared by every engine; a
    test that switches it to a non-default locale would otherwise leak that
    state into later tests (order-dependent failures). Restoring the default
    locale keeps every ``test_gui`` test starting from a deterministic zh-CN
    state (SA ruling R1).
    """
    from src.ui.gui.localization import DEFAULT_LOCALE, gui_localization

    gui_localization.setLocale(DEFAULT_LOCALE)
    yield
    gui_localization.setLocale(DEFAULT_LOCALE)
