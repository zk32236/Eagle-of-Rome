pragma Singleton
import QtQuick 2.15

/*!
 * \brief L10n — GUI localization access layer (GUI-I18N Foundation, slice S2).
 *
 * Reads the merged catalog from the single GUI locale authority exposed to QML
 * as the ``localization`` context property (``GuiLocalization.catalog``; see
 * FC-GI18N-01). ``t(key, params)`` resolves a key against the catalog:
 *   * hit        -> the catalog value (with ``{param}`` placeholders substituted)
 *   * miss       -> the key literal (deterministic fallback, FC-GI18N-04)
 *
 * The ``catalog`` property is the reactive dependency anchor (FC-GI18N-05):
 * every binding that reads it (directly or via ``t()``) is invalidated when
 * ``GuiLocalization.setLocale`` emits ``localeChanged`` -> ``catalog`` notify,
 * so the shell re-resolves its copy in place without a restart.
 */
QtObject {
    readonly property var catalog: localization.catalog

    function t(key, params) {
        var cat = catalog
        var template = (cat && cat[key] !== undefined && cat[key] !== null) ? cat[key] : key
        if (template === undefined || template === null) {
            return key
        }
        var out = String(template)
        if (!params) {
            return out
        }
        for (var name in params) {
            if (params.hasOwnProperty(name)) {
                out = out.split("{" + name + "}").join(String(params[name]))
            }
        }
        return out
    }
}
