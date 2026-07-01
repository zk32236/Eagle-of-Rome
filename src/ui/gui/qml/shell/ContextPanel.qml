import QtQuick 2.15
import QtQuick.Controls 2.15
import QtQuick.Layouts 1.15

import "../components"
import "../i18n"

Rectangle {
    id: root
    color: theme.bgSurface1
    border.color: theme.borderNormal
    border.width: 1

    ColumnLayout {
        anchors.fill: parent
        anchors.margins: 16
        spacing: 12

        // 标题
        Text {
            text: GuiText.factionResources
            color: theme.textMuted
            font.pixelSize: 11
            font.bold: true
        }

        // 资源瓦片
        GridLayout {
            Layout.fillWidth: true
            columns: 2
            rowSpacing: 8
            columnSpacing: 8

            StatusTile {
                Layout.fillWidth: true
                label: "派系金库"
                value: (sessionStore.factionTreasury || 0) + " T"
                icon: "💰"
            }
            StatusTile {
                Layout.fillWidth: true
                label: "总影响力"
                value: sessionStore.factionInfluence || 0
                icon: "⚖️"
            }
            StatusTile {
                Layout.fillWidth: true
                label: "派系人物"
                value: (sessionStore.factionMemberCount || 0) + " 人"
                icon: "👥"
            }
            StatusTile {
                Layout.fillWidth: true
                label: GuiText.votedOffices
                value: Object.keys(sessionStore.myVotes || {}).length + " / 5"
                icon: "V"
            }
        }

        // 分隔线
        Rectangle {
            Layout.fillWidth: true
            height: 1
            color: theme.borderNormal
        }

        // 当前目标
        Text {
            text: GuiText.currentPhase
            color: theme.textMuted
            font.pixelSize: 11
            font.bold: true
        }

        ColumnLayout {
            spacing: 6
            Text {
                text: sessionStore.selectedPhaseName || GuiText.populationFallbackName
                color: theme.textPrimary
                font.pixelSize: 14
                font.bold: true
                Layout.fillWidth: true
            }
            Text {
                text: (sessionStore.selectedPhaseSummary.subtitle || "")
                color: theme.accentBronze
                font.pixelSize: 11
                wrapMode: Text.Wrap
                Layout.fillWidth: true
            }
            Text {
                text: (sessionStore.selectedPhaseSummary.description || "")
                color: theme.textSecondary
                font.pixelSize: 11
                wrapMode: Text.Wrap
                Layout.fillWidth: true
            }
            Text {
                text: sessionStore.selectedPhaseSummary.implemented ? GuiText.statusActionable : GuiText.statusPlaceholder
                color: sessionStore.selectedPhaseSummary.implemented ? theme.statusSuccess : theme.statusWarning
                font.pixelSize: 11
                wrapMode: Text.Wrap
                Layout.fillWidth: true
            }
        }

        // 权限提示
        Rectangle {
            Layout.fillWidth: true
            height: 48
            color: theme.bgSurface2
            radius: theme.radius
            border.color: theme.borderNormal
            border.width: 1

            Text {
                anchors.fill: parent
                anchors.margins: 8
                text: GuiText.playerScope(sessionStore.viewerFactionName, sessionStore.viewerFactionId)
                color: theme.textMuted
                font.pixelSize: 10
                wrapMode: Text.Wrap
                verticalAlignment: Text.AlignVCenter
            }
        }

        Repeater {
            model: sessionStore.globalWarnings || []
            delegate: Rectangle {
                Layout.fillWidth: true
                height: warningText.implicitHeight + 16
                color: theme.bgSurface2
                radius: theme.radius
                border.color: modelData.type === "warning" ? theme.statusWarning : theme.borderNormal
                border.width: 1
                Text {
                    id: warningText
                    anchors.fill: parent
                    anchors.margins: 8
                    text: modelData.message
                    color: modelData.type === "warning" ? theme.statusWarning : theme.textMuted
                    font.pixelSize: 10
                    wrapMode: Text.Wrap
                }
            }
        }

        Item { Layout.fillHeight: true }

        // 流程控制
        ColumnLayout {
            Layout.fillWidth: true
            spacing: 8

            AppButton {
                Layout.fillWidth: true
                text: GuiText.completeCurrentPlayer
                type: "primary"
                enabled: sessionStore.selectedPhaseId === "population" && sessionStore.isCurrentPlayer && sessionStore.canComplete
                onClicked: {
                    var result = sessionStore.doCompletePlayer()
                    if (!result.success) {
                        showFeedback("error", result.message)
                    }
                }
            }
            AppButton {
                Layout.fillWidth: true
                text: GuiText.refreshAuthoritativeState
                type: "secondary"
                onClicked: sessionStore.refreshSnapshot()
            }
        }
    }
}
