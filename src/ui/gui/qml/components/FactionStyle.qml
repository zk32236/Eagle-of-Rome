import QtQuick 2.15

/*!
 * \brief FactionStyle — Shared faction style lookup for all QML stages.
 *
 * Reads from sessionStore.factionStyleMap (populated by faction_api.get_faction_style_map()).
 * Provides factionColor(factionId) and factionName(factionId) for all stages.
 *
 * Usage (in any QML file that imports "../components"):
 *   FactionStyle.factionColor("optimates") → "#C62828"
 *   FactionStyle.factionName("optimates")  → "Optimates"
 *
 * Fallback: unknown faction_id → "#3A3530" / "未知派系"
 */
QtObject {
    id: factionStyle

    /*!
     * Returns the hex color for a faction_id, or fallback color if unknown.
     * Accepts either faction_id ("optimates") or faction name ("Optimates").
     */
    function factionColor(factionIdOrName) {
        if (!factionIdOrName) return _fallbackColor()

        var map = _styleMap()
        var key = _resolveKey(factionIdOrName, map)
        if (key && map[key] && map[key].color) {
            return map[key].color
        }
        return _fallbackColor()
    }

    /*!
     * Returns the display name for a faction_id, or fallback name if unknown.
     * Accepts either faction_id ("opt") or faction name ("Optimates").
     */
    function factionName(factionIdOrName) {
        if (!factionIdOrName) return _fallbackName()

        var map = _styleMap()
        var key = _resolveKey(factionIdOrName, map)
        if (key && map[key] && map[key].name) {
            return map[key].name
        }
        // If it's already a name, return as-is
        return factionIdOrName
    }

    /*!
     * Returns the short id_display for a faction_id.
     */
    function factionShort(factionIdOrName) {
        if (!factionIdOrName) return "?"

        var map = _styleMap()
        var key = _resolveKey(factionIdOrName, map)
        if (key && map[key] && map[key].id_display) {
            return map[key].id_display
        }
        // Fallback: truncate to 3 chars
        var s = String(factionIdOrName)
        return s.length > 3 ? s.substring(0, 3) : s
    }

    // ── Internal helpers ──

    function _styleMap() {
        var data = sessionStore ? sessionStore.factionStyleMap : null
        if (!data || !data.map) return {}
        return data.map
    }

    function _fallbackColor() {
        var data = sessionStore ? sessionStore.factionStyleMap : null
        if (data && data.fallback && data.fallback.color) {
            return data.fallback.color
        }
        return "#3A3530"
    }

    function _fallbackName() {
        var data = sessionStore ? sessionStore.factionStyleMap : null
        if (data && data.fallback && data.fallback.name) {
            return data.fallback.name
        }
        return "未知派系"
    }

    /*!
     * Resolve a faction_id or name to a map key.
     * Tries exact match first, then name match.
     */
    function _resolveKey(factionIdOrName, map) {
        // Direct key match (e.g. "opt")
        if (map[factionIdOrName]) return factionIdOrName

        // Try case-insensitive name match
        var lower = String(factionIdOrName).toLowerCase()
        for (var key in map) {
            if (!map.hasOwnProperty(key)) continue
            var entry = map[key]
            if (entry.name && String(entry.name).toLowerCase() === lower) {
                return key
            }
            // Also try partial match for "Optimates" in "Opt" etc.
            if (entry.id_display && String(entry.id_display).toLowerCase() === lower) {
                return key
            }
        }

        // Try substring matching for legacy compatibility
        // e.g. "Optimates" matches "opt", "Populares" matches "pop"
        for (var key2 in map) {
            if (!map.hasOwnProperty(key2)) continue
            var entry2 = map[key2]
            if (entry2.name && lower.indexOf(String(entry2.name).toLowerCase()) >= 0) {
                return key2
            }
            if (entry2.id_display && lower.indexOf(String(entry2.id_display).toLowerCase()) >= 0) {
                return key2
            }
        }

        return null
    }
}
