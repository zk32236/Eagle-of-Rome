import QtQuick 2.15
import QtQuick.Controls 2.15
import QtQuick.Layouts 1.15


Rectangle {
    id: root
    color: theme.bgSurface1
    border.color: theme.borderNormal
    border.width: 1

    RowLayout {
        anchors.fill: parent
        anchors.margins: 12
        spacing: 20

        // Logo
        Row {
            Layout.alignment: Qt.AlignVCenter
            spacing: 8
            Text {
                text: "SPQR"
                color: theme.accentBronze
                font.family: theme.fontTitle
                font.pixelSize: 14
                font.bold: true
            }
            Text {
                text: "Eagle of Rome"
                color: theme.textPrimary
                font.family: theme.fontFamily
                font.pixelSize: 13
            }
        }

        // 年份 / 回合
        Row {
            Layout.alignment: Qt.AlignVCenter
            spacing: 16
            Text {
                text: "📅 " + (sessionStore.yearDisplay || "282 BC")
                color: theme.textSecondary
                font.pixelSize: 12
            }
            Text {
                text: "🔄 回合 " + (sessionStore.turnNumber || 1)
                color: theme.textSecondary
                font.pixelSize: 12
            }
            Text {
                text: "⚔️ 阶段：人口"
                color: theme.accentPrimary
                font.pixelSize: 12
                font.bold: true
            }
        }

        Item { Layout.fillWidth: true }

        // 国库
        Row {
            Layout.alignment: Qt.AlignVCenter
            spacing: 8
            Text {
                text: "💰"
                font.pixelSize: 12
            }
            Text {
                text: (sessionStore.treasury || 0) + " T"
                color: theme.accentBronzeHighlight
                font.pixelSize: 13
                font.bold: true
            }
        }

        // 当前玩家
        Row {
            Layout.alignment: Qt.AlignVCenter
            spacing: 8
            Rectangle {
                width: 24; height: 24
                radius: 12
                color: theme.accentPrimary
                Text {
                    anchors.centerIn: parent
                    text: "OP"
                    color: "white"
                    font.pixelSize: 10
                    font.bold: true
                }
            }
            Text {
                text: "Player " + (sessionStore.viewerFactionId || "Optimates")
                color: theme.textPrimary
                font.pixelSize: 12
            }
        }
    }
}
