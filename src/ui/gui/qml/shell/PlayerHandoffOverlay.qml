import QtQuick 2.15
import QtQuick.Controls 2.15
import QtQuick.Layouts 1.15

import "../components"

Rectangle {
    id: root
    color: "#CC000000"
    visible: false

    property string nextPlayerId: ""

    function show(playerId) {
        nextPlayerId = playerId
        visible = true
    }

    ColumnLayout {
        anchors.centerIn: parent
        width: 400
        spacing: 24

        Text {
            Layout.alignment: Qt.AlignHCenter
            text: "🔒 玩家交接"
            color: theme.textPrimary
            font.pixelSize: 24
            font.family: theme.fontTitle
            font.bold: true
        }

        Text {
            Layout.alignment: Qt.AlignHCenter
            text: "当前玩家操作已完成。\n\n下一玩家：" + nextPlayerId
            color: theme.textSecondary
            font.pixelSize: 14
            horizontalAlignment: Text.AlignHCenter
            wrapMode: Text.Wrap
        }

        Rectangle {
            Layout.alignment: Qt.AlignHCenter
            width: 80; height: 80
            radius: 40
            color: theme.accentPrimary
            Text {
                anchors.centerIn: parent
                text: nextPlayerId.substring(0, 2).toUpperCase()
                color: "white"
                font.pixelSize: 24
                font.bold: true
            }
        }

        AppButton {
            Layout.alignment: Qt.AlignHCenter
            Layout.preferredWidth: 200
            text: "确认交接"
            type: "primary"
            onClicked: {
                if (guiApp.confirmHandoff(nextPlayerId)) {
                    root.visible = false
                }
            }
        }
    }
}
