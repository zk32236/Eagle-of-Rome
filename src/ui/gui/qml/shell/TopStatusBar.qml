import QtQuick 2.15
import QtQuick.Controls 2.15
import QtQuick.Layouts 1.15

import "../i18n"

/*!
 * TopStatusBar — v3.25.1 Codex v4.0 (§2 A)
 *
 * Layout contract: GUI_LAYOUT_CONTRACT_Phase1_v3.25.1.md §2
 *   x=10, y=10, w=1420, h=62
 *   bg: linear-gradient(180deg, #8B2A0D, #5A1506)
 *   border: 1px solid rgba(217,175,99,.58), radius: 10px
 *   padding: 6px 14px
 *   order: Logo → 国库 → 派系 → 影响力 → 稳定度 → 战争 → round-info(right)
 *   5 stat items, flex:1 each, with pill containers
 *   round-info as standalone right element
 *
 * Skeleton stage: only anchors, colors, layout. No business logic changes.
 */
Rectangle {
    id: root
    objectName: "topStatusBar"
    height: 62
    color: "transparent"

    // Header background gradient using overlay
    Rectangle {
        anchors.fill: parent
        radius: theme.radius
        gradient: Gradient {
            orientation: Gradient.Vertical
            GradientStop { position: 0.0; color: "#8B2A0D" }
            GradientStop { position: 1.0; color: "#5A1506" }
        }
        border.color: "#94D9AF63"
        border.width: 1
    }

    RowLayout {
        anchors.fill: parent
        anchors.margins: 6
        spacing: 7

        // ---- Logo Section ----
        Rectangle {
            id: logoContainer
            height: parent.height - 12
            Layout.preferredWidth: logoRow.implicitWidth + 28
            Layout.fillHeight: true
            color: "#0DFFFFFF"
            radius: 9
            border.color: "#33F2D590"
            border.width: 1

            Row {
                id: logoRow
                anchors.centerIn: parent
                spacing: 6
                Text {
                    text: "🏛️"
                    font.pixelSize: 14
                    color: "#FFEEDD"
                    anchors.verticalCenter: parent.verticalCenter
                }
                Text {
                    text: "EAGLE OF ROME"
                    color: theme.headerText
                    font.pixelSize: theme.brandSize
                    font.bold: true
                }
                Text {
                    text: "· SPQR"
                    color: "#C7F2D590"
                    font.pixelSize: 11
                }
            }
        }

        // ---- 国库 ----
        StatPill {
            Layout.fillWidth: true
            Layout.fillHeight: true
            iconText: "💰"
            statValue: sessionStore.treasury !== undefined ? sessionStore.treasury : "--"
            statLabel: "国库"
        }

        // ---- 派系 ----
        StatPill {
            Layout.fillWidth: true
            Layout.fillHeight: true
            iconText: "👛"
            statValue: sessionStore.factionTreasury !== undefined ? sessionStore.factionTreasury : "--"
            statLabel: "派系"
        }

        // ---- 影响力 ----
        StatPill {
            Layout.fillWidth: true
            Layout.fillHeight: true
            iconText: "⚖️"
            statValue: sessionStore.factionInfluence !== undefined ? sessionStore.factionInfluence : "--"
            statLabel: "影响力"
        }

        // ---- 稳定度 — 始终显示；Store 字段或安全占位 ----
        // H0.3: fix 0-value handling — use !== undefined check instead of ||
        StatPill {
            Layout.fillWidth: true
            Layout.fillHeight: true
            iconText: "🏛️"
            statValue: sessionStore.stability !== undefined ? sessionStore.stability : "--"
            statLabel: "稳定度"
        }

        // ---- 战争 — 始终显示；缺值显示 -- ----
        // H0.3: fix 0-value handling — use !== undefined check instead of ||
        StatPill {
            Layout.fillWidth: true
            Layout.fillHeight: true
            iconText: "⚔️"
            statValue: sessionStore.warCount !== undefined ? sessionStore.warCount : "--"
            statLabel: "战争"
        }

        // ---- Round Info (rightmost standalone pill) ----
        Rectangle {
            id: roundInfo
            Layout.preferredWidth: 152
            Layout.fillHeight: true
            radius: 9
            color: "#33FFFFFF"
            border.color: "#3DF2D590"
            border.width: 1

            Row {
                anchors.centerIn: parent
                spacing: 4
                Text {
                    text: sessionStore.yearDisplay || "282 BC"
                    color: theme.headerText
                    font.pixelSize: 14
                    font.bold: true
                }
                Text {
                    text: "·"
                    color: "#59FFFFFF"
                    font.pixelSize: 14
                }
                Text {
                    text: "回合 " + (sessionStore.turnNumber || 1)
                    color: theme.headerText
                    font.pixelSize: 14
                    font.bold: true
                }
            }
        }
    }

    // ---- Inline stat pill component (Codex v4.0 style) ----
    component StatPill: Rectangle {
        property string iconText: ""
        property var statValue: "--"
        property string statLabel: ""

        radius: 9
        color: "#0DFFFFFF"
        border.color: "#2EF2D590"
        border.width: 1

        Row {
            anchors.centerIn: parent
            spacing: 7

            // Icon
            Text {
                text: iconText
                font.pixelSize: 14
                color: "#FFEEDD"
                anchors.verticalCenter: parent.verticalCenter
            }

            // Value + label stacked
            Column {
                anchors.verticalCenter: parent.verticalCenter
                spacing: 0
                Text {
                    text: statValue
                    color: theme.headerText
                    font.pixelSize: theme.statValueSize
                    font.bold: true
                    lineHeight: 1.15
                }
                Text {
                    text: statLabel
                    color: theme.statLabel
                    font.pixelSize: theme.statLabelSize
                    lineHeight: 1.12
                }
            }
        }
    }
}
