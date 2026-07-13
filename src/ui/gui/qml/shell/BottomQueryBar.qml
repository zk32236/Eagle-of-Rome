import QtQuick 2.15
import QtQuick.Controls 2.15
import QtQuick.Layouts 1.15

import "../components"
import "../i18n"

/*!
 * \brief BottomQueryBar — v3.25.1 Codex v4.0 (§6 E)
 *
 * Layout contract: GUI_LAYOUT_CONTRACT_Phase1_v3.25.1.md §6
 *   x=10, y=828, w=1420, h=62
 *   bg: linear-gradient(180deg, rgba(105,30,8,.98), rgba(47,24,13,.98))
 *   border: 1px solid rgba(217,175,99,.32), radius: 10px
 *   12 query buttons with icon+TEXT format
 *   Buttons fill bar height, flex:1
 *
 * Skeleton stage: only anchors, colors, layout, button definitions. No business logic.
 */
Rectangle {
    id: root
    objectName: "bottomQueryBar"
    height: 62
    color: "transparent"

    // Op-bar background gradient
    Rectangle {
        anchors.fill: parent
        radius: theme.radius
        gradient: Gradient {
            orientation: Gradient.Vertical
            GradientStop { position: 0.0; color: "#FA691E08" }   // rgba(105,30,8,.98)
            GradientStop { position: 1.0; color: "#FA2F180D" }   // rgba(47,24,13,.98)
        }
        border.color: "#52D9AF63"  // rgba(217,175,99,.32)
        border.width: 1
    }

    property var queryButtons: [
        { "id": "game_status", "icon": "📊", "label": GuiText.queryGameStatus, "status": "connected" },
        { "id": "faction_info", "icon": "📋", "label": GuiText.queryFactionInfo, "status": "readonly" },
        { "id": "war_list", "icon": "⚔️", "label": GuiText.queryWarList, "status": "readonly" },
        { "id": "legion_status", "icon": "🗡️", "label": GuiText.queryLegionStatus, "status": "readonly" },
        { "id": "figure_search", "icon": "👤", "label": GuiText.queryFigureSearch, "status": "placeholder" },
        { "id": "faction_treasury", "icon": "💰", "label": GuiText.queryFactionTreasury, "status": "placeholder" },
        { "id": "public_land", "icon": "🌾", "label": GuiText.queryPublicLand, "status": "placeholder" },
        { "id": "private_land", "icon": "🏡", "label": GuiText.queryPrivateLand, "status": "placeholder" },
        { "id": "contract_status", "icon": "📦", "label": GuiText.queryContractStatus, "status": "placeholder" },
        { "id": "province_info", "icon": "🏛️", "label": GuiText.queryProvinceInfo, "status": "placeholder" },
        { "id": "fleet_status", "icon": "⚓", "label": GuiText.queryFleetStatus, "status": "placeholder" },
        { "id": "help", "icon": "❓", "label": GuiText.queryHelp, "status": "placeholder" }
    ]
    readonly property int queryButtonCount: queryButtons.length
    readonly property string queryButtonIds: queryButtons.map(function(item) { return item.id }).join(",")
    signal queryRequested(string queryId)

    RowLayout {
        anchors.fill: parent
        anchors.margins: 6
        spacing: 6

        // Query buttons in icon+TEXT format
        Repeater {
            model: root.queryButtons
            delegate: Rectangle {
                id: btn
                Layout.fillWidth: true
                Layout.fillHeight: true
                radius: 8
                color: mouseArea.containsMouse ? "#2ED9AF63" : "#0FFFFFFF"
                border.color: mouseArea.containsMouse ? "#C7D9AF63" : "#33D9AF63"
                border.width: 1

                property string btnIcon: modelData.icon
                property string btnText: modelData.label
                property string btnStatus: modelData.status

                RowLayout {
                    anchors.centerIn: parent
                    spacing: 5

                    // Icon
                    Text {
                        text: parent.parent.btnIcon
                        font.pixelSize: 13
                    }
                    // Text
                    Text {
                        text: parent.parent.btnText
                        color: "#DBF3EADC"
                        font.pixelSize: theme.buttonSize
                    }
                }

                // Status opacity
                opacity: btn.btnStatus === "connected" ? 1.0 : (btn.btnStatus === "readonly" ? 0.8 : 0.55)

                // Hover translateY effect
                transform: Translate {
                    y: mouseArea.containsMouse ? -1 : 0
                }

                Behavior on transform {
                    NumberAnimation { duration: 140; easing.type: Easing.OutQuad }
                }

                MouseArea {
                    id: mouseArea
                    anchors.fill: parent
                    hoverEnabled: true
                    cursorShape: Qt.PointingHandCursor
                    onClicked: root.queryRequested(modelData.id)
                }
            }
        }
    }
}
