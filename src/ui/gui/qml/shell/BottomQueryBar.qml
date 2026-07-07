import QtQuick 2.15
import QtQuick.Controls 2.15
import QtQuick.Layouts 1.15

import "../components"
import "../i18n"

/**
 * BottomQueryBar.qml — Global query bar
 * Design V2.0 §1.7
 *
 * Deep red bottom bar with 12 always-available query buttons
 */
Rectangle {
    id: root
    objectName: "bottomQueryBar"
    color: "#8B2500"  // 深红底色
    height: 36

    property var queryButtons: [
        { "id": "faction_info", "icon": "📋", "label": GuiText.queryFactionInfo, "status": "readonly" },
        { "id": "figure_search", "icon": "👤", "label": GuiText.queryFigureSearch, "status": "placeholder" },
        { "id": "game_status", "icon": "📊", "label": GuiText.queryGameStatus, "status": "connected" },
        { "id": "faction_treasury", "icon": "💰", "label": GuiText.queryFactionTreasury, "status": "placeholder" },
        { "id": "public_land", "icon": "🌾", "label": GuiText.queryPublicLand, "status": "placeholder" },
        { "id": "private_land", "icon": "🏡", "label": GuiText.queryPrivateLand, "status": "placeholder" },
        { "id": "contract_status", "icon": "📦", "label": GuiText.queryContractStatus, "status": "placeholder" },
        { "id": "province_info", "icon": "🏛️", "label": GuiText.queryProvinceInfo, "status": "placeholder" },
        { "id": "war_list", "icon": "⚔️", "label": GuiText.queryWarList, "status": "readonly" },
        { "id": "legion_status", "icon": "🗡️", "label": GuiText.queryLegionStatus, "status": "readonly" },
        { "id": "fleet_status", "icon": "⚓", "label": GuiText.queryFleetStatus, "status": "placeholder" },
        { "id": "help", "icon": "❓", "label": GuiText.queryHelp, "status": "placeholder" }
    ]
    readonly property int queryButtonCount: queryButtons.length
    readonly property string queryButtonIds: queryButtons.map(function(item) { return item.id }).join(",")
    signal queryRequested(string queryId)

    RowLayout {
        anchors.fill: parent
        anchors.margins: 4
        spacing: 2

        Repeater {
            model: root.queryButtons
            delegate: Rectangle {
                id: btnBg
                objectName: "bottomQueryButton_" + modelData.id
                Layout.fillWidth: true
                Layout.preferredHeight: 28
                color: modelData.status === "connected" ? "#55C8942E" :
                       modelData.status === "readonly" ? "#33FFFFFF" :
                       "#1AFFFFFF"
                radius: 4
                border.color: modelData.status === "connected" ? "#C8942E" : "#55FFFFFF"
                border.width: modelData.status === "connected" ? 1 : 0

                property bool hovered: false

                Text {
                    anchors.centerIn: parent
                    text: modelData.icon + " " + modelData.label
                    color: modelData.status === "connected" ? "#C8942E" :
                           modelData.status === "readonly" ? "#FFD9A0" :
                           "#AAFFD9A0"
                    font.pixelSize: 9
                    font.bold: modelData.status === "connected"
                    horizontalAlignment: Text.AlignHCenter
                    verticalAlignment: Text.AlignVCenter
                }

                MouseArea {
                    anchors.fill: parent
                    hoverEnabled: true
                    onEntered: btnBg.color = "#55FFFFFF"
                    onExited: btnBg.color = modelData.status === "connected" ? "#55C8942E" :
                                                modelData.status === "readonly" ? "#33FFFFFF" : "#1AFFFFFF"
                    onClicked: root.queryRequested(modelData.id)
                    cursorShape: Qt.PointingHandCursor
                }
            }
        }
    }
}
