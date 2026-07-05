import QtQuick 2.15
import QtQuick.Controls 2.15
import QtQuick.Layouts 1.15

import "../i18n"

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
                text: GuiText.appMark
                color: theme.accentBronze
                font.family: theme.fontTitle
                font.pixelSize: 14
                font.bold: true
            }
            Text {
                text: GuiText.appName
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
                text: GuiText.calendarIcon + " " + (sessionStore.yearDisplay || GuiText.defaultYearDisplay)
                color: theme.textSecondary
                font.pixelSize: 12
            }
            Text {
                text: GuiText.turnIcon + " " + GuiText.turnText(sessionStore.turnNumber)
                color: theme.textSecondary
                font.pixelSize: 12
            }
            Text {
                text: GuiText.phaseLabelPrefix + (sessionStore.selectedPhaseName || sessionStore.currentPhaseName || GuiText.populationFallbackName)
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
                text: GuiText.treasuryIcon
                font.pixelSize: 12
            }
            Text {
                text: GuiText.treasuryPrefix + (sessionStore.treasury || 0) + " T"
                color: theme.accentBronzeHighlight
                font.pixelSize: 13
                font.bold: true
            }
            Text {
                text: GuiText.factionTreasuryPrefix + (sessionStore.factionTreasury || 0) + " T"
                color: theme.textSecondary
                font.pixelSize: 12
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
                    text: GuiText.defaultPlayerAvatar
                    color: "white"
                    font.pixelSize: 10
                    font.bold: true
                }
            }
            Text {
                text: GuiText.currentPlayerText(sessionStore.currentPlayerId, sessionStore.viewerFactionName, sessionStore.viewerFactionId)
                color: theme.textPrimary
                font.pixelSize: 12
                elide: Text.ElideRight
            }
        }
    }
}
