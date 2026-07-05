import QtQuick 2.15
import QtQuick.Controls 2.15
import QtQuick.Layouts 1.15

import "../components"
import "../i18n"

Rectangle {
    id: root
    objectName: "bottomQueryBar"
    color: theme.bgSurface1
    border.color: theme.borderNormal
    border.width: 1

    property var queryButtons: [
        { "id": "game_status", "label": GuiText.queryGameStatus, "status": "connected" },
        { "id": "faction_info", "label": GuiText.queryFactionInfo, "status": "readonly" },
        { "id": "war_list", "label": GuiText.queryWarList, "status": "readonly" },
        { "id": "legion_status", "label": GuiText.queryLegionStatus, "status": "placeholder" },
        { "id": "figure_search", "label": GuiText.queryFigureSearch, "status": "placeholder" },
        { "id": "faction_treasury", "label": GuiText.queryFactionTreasury, "status": "placeholder" },
        { "id": "public_land", "label": GuiText.queryPublicLand, "status": "placeholder" },
        { "id": "private_land", "label": GuiText.queryPrivateLand, "status": "placeholder" },
        { "id": "contract_status", "label": GuiText.queryContractStatus, "status": "placeholder" },
        { "id": "province_info", "label": GuiText.queryProvinceInfo, "status": "placeholder" },
        { "id": "fleet_status", "label": GuiText.queryFleetStatus, "status": "placeholder" },
        { "id": "help", "label": GuiText.queryHelp, "status": "placeholder" }
    ]
    readonly property int queryButtonCount: queryButtons.length
    readonly property string queryButtonIds: queryButtons.map(function(item) { return item.id }).join(",")
    signal queryRequested(string queryId)

    RowLayout {
        anchors.fill: parent
        anchors.margins: 10
        spacing: 10

        Text {
            text: GuiText.bottomQueryBarTitle
            color: theme.textMuted
            font.pixelSize: 11
            font.bold: true
            Layout.preferredWidth: 64
            horizontalAlignment: Text.AlignHCenter
            verticalAlignment: Text.AlignVCenter
        }

        Repeater {
            model: root.queryButtons
            delegate: AppButton {
                objectName: "bottomQueryButton_" + modelData.id
                Layout.fillWidth: true
                Layout.preferredHeight: 44
                text: modelData.label + "\n" + GuiText.queryStatusText(modelData.status)
                type: modelData.status === "connected" ? "primary" : "secondary"
                fontSize: 10
                onClicked: root.queryRequested(modelData.id)
            }
        }
    }
}
