import QtQuick 2.15

/*!
 * Theme.qml — v3.25.1 Codex v4.0 visual color tokens
 * See GUI_LAYOUT_CONTRACT_Phase1_v3.25.1.md §8 Color Token Table
 */
QtObject {
    // ======================== Shell (Deep-Ink) ========================
    readonly property color bgApp: "#14110D"
    readonly property color bgSurface1: "#211812"
    readonly property color bgSurface2: "#1F1812"     // rgba(31,24,18,.92)

    // ======================== Accent / Roman Red ========================
    readonly property color accentPrimary: "#9A3417"
    readonly property color accentPrimaryDark: "#76200A"
    readonly property color accentPrimaryDeep: "#561405"
    readonly property color accentBronze: "#A8753B"
    readonly property color accentBronzeSoft: "#80D9AF63"   // rgba(217,175,99,.34)
    readonly property color accentGold: "#D9AF63"
    readonly property color accentGoldSoft: "#F7D778"      // also #F2D590

    // ======================== Text ========================
    readonly property color textPrimary: "#F3EADC"
    readonly property color textSecondary: "#756550"
    readonly property color textDark: "#2E251B"
    readonly property color textSoft: "#756550"
    readonly property color textMuted: "#B9A58C"

    // ======================== Panel / Surface ========================
    readonly property color ivoryDesk: "#F2EEE4"
    readonly property color ivoryDesk2: "#E8DFCF"
    readonly property color parchment: "#FBF1DC"
    readonly property color parchment2: "#F4E2BA"
    readonly property color paper: "#FFF9EC"
    readonly property color panelBorder: "#80D9AF63"     // rgba(217,175,99,.46-.62)
    readonly property color panelBorderStrong: "#BD8F52"

    // ======================== Header / Status Bar ========================
    readonly property color headerBgTop: "#8B2A0D"
    readonly property color headerBgBottom: "#5A1506"
    readonly property color headerBorder: "#94D9AF63"    // rgba(217,175,99,.58)
    readonly property color headerText: "#F7D778"
    readonly property color statLabel: "#9CF3EADC"       // rgba(243,234,220,.62)
    readonly property color statBorder: "#2EF2D590"     // rgba(242,213,144,.18)

    // ======================== State Colors ========================
    readonly property color statusSuccess: "#228B22"
    readonly property color statusWarning: "#FF8C00"
    readonly property color statusError: "#C45151"
    readonly property color statusInfo: "#6C8FA1"
    readonly property color statusMuted: "#877663"

    // ======================== Faction Colors ========================
    readonly property color factionOpt: "#8B0000"
    readonly property color factionPop: "#006400"
    readonly property color factionEqu: "#00008B"

    // ======================== Buttons ========================
    readonly property color btnBg: "#D7B06E"
    readonly property color btnHover: "#B87333"
    readonly property color btnPrimaryTop: "#84250A"
    readonly property color btnPrimaryBottom: "#671B07"
    readonly property color btnPrimaryText: "#F7D778"
    readonly property color btnDisabled: "#6BD7B06E"

    // ======================== Font Sizes ========================
    readonly property int brandSize: 17
    readonly property int titleSize: 20
    readonly property int bodySize: 12
    readonly property int smallSize: 10
    readonly property int statValueSize: 15
    readonly property int statLabelSize: 10
    readonly property int buttonSize: 12
    readonly property int logSize: 11

    // ======================== Font Families ========================
    readonly property string fontFamily: "Microsoft YaHei UI"
    readonly property string fontTitle: "Microsoft YaHei UI"
    readonly property int radius: 10

    // ======================== Phase Colors ========================
    function phaseColor(phaseId) {
        if (phaseId === "population") return accentPrimary
        if (phaseId === "senate") return accentGold
        return statusMuted
    }
}
