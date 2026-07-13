import QtQuick 2.15
import QtQuick.Controls 2.15
import QtQuick.Layouts 1.15

import "../components"
import "../i18n"

/*!
 * \brief PhaseRail — v3.25.1 Codex v4.0 (§3 B)
 *
 * Layout contract: GUI_LAYOUT_CONTRACT_Phase1_v3.25.1.md §3
 *   x=10, y=82, w=92, h=736
 *   bg: rgba(31,24,18,.92), border: 1px solid rgba(217,175,99,.34), radius: 10px
 *   7 pill-shaped steps (74×54, radius 10px)
 *   Labels always visible below icons
 *   No title text, no bottom buttons.
 *
 * Skeleton stage: only anchors, colors, layout. No business logic.
 */
Rectangle {
    id: root
    objectName: "phaseRail"
    color: "#14110D"          // deep-ink (H0.2: fix purple-tinted → deep-ink #14110D)
    border.color: "#57D9AF63"  // rgba(217,175,99,.34)
    border.width: 1
    radius: 10
    width: 92
    Layout.preferredWidth: 92
    Layout.minimumWidth: 92

    // H0.3: top-anchored with consistent padding (was anchors.centerIn)
    ColumnLayout {
        anchors.top: parent.top
        anchors.topMargin: 10
        anchors.horizontalCenter: parent.horizontalCenter
        spacing: 6

        PhaseRailIcon {
            objectName: "phaseRailIcon_mortality"
            iconText: "🎴"; label: "天命"
            state: sessionStore.selectedPhaseId === "mortality" ? "current" : (sessionStore.currentPhaseIndex > 0 ? "done" : "todo")
            onClicked: sessionStore.selectPhase("mortality")
        }
        PhaseRailIcon {
            objectName: "phaseRailIcon_revenue"
            iconText: "💰"; label: "收入"
            state: sessionStore.selectedPhaseId === "revenue" ? "current" : (sessionStore.currentPhaseIndex > 1 ? "done" : "todo")
            onClicked: sessionStore.selectPhase("revenue")
        }
        PhaseRailIcon {
            objectName: "phaseRailIcon_forum"
            iconText: "🏛️"; label: "广场"
            state: sessionStore.selectedPhaseId === "forum" ? "current" : (sessionStore.currentPhaseIndex > 2 ? "done" : "todo")
            onClicked: sessionStore.selectPhase("forum")
        }
        PhaseRailIcon {
            objectName: "phaseRailIcon_population"
            iconText: "⚖️"; label: "人口"
            state: sessionStore.selectedPhaseId === "population" ? "current" : (sessionStore.currentPhaseIndex > 3 ? "done" : "todo")
            onClicked: sessionStore.selectPhase("population")
        }
        PhaseRailIcon {
            objectName: "phaseRailIcon_senate"
            iconText: "🏺"; label: "元老院"
            state: sessionStore.selectedPhaseId === "senate" ? "current" : (sessionStore.currentPhaseIndex > 4 ? "done" : "todo")
            onClicked: sessionStore.selectPhase("senate")
        }
        PhaseRailIcon {
            objectName: "phaseRailIcon_war"
            iconText: "⚔️"; label: "战斗"
            state: sessionStore.selectedPhaseId === "war" ? "current" : (sessionStore.currentPhaseIndex > 5 ? "done" : "todo")
            onClicked: sessionStore.selectPhase("war")
        }
        PhaseRailIcon {
            objectName: "phaseRailIcon_resolution"
            iconText: "📊"; label: "决算"
            state: sessionStore.selectedPhaseId === "resolution" ? "current" : (sessionStore.currentPhaseIndex > 6 ? "done" : "todo")
            onClicked: sessionStore.selectPhase("resolution")
        }

        Item { Layout.fillHeight: true }
    }
}
