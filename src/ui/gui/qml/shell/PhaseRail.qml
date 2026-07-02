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
        anchors.margins: 12
        spacing: 4

        Text {
            text: GuiText.shellPhaseTitle
            color: theme.textMuted
            font.pixelSize: 11
            font.bold: true
            Layout.bottomMargin: 8
        }

        Repeater {
            model: sessionStore.phaseNavigation || []
            delegate: Rectangle {
                objectName: "phaseNavItem_" + modelData.id
                Layout.fillWidth: true
                height: 48
                radius: theme.radius
                color: {
                    if (sessionStore.selectedPhaseId === modelData.id) return theme.accentPrimary
                    if (modelData.current) return theme.bgSurface3
                    if (modelData.executed) return theme.bgSurface2
                    return "transparent"
                }
                border.color: sessionStore.selectedPhaseId === modelData.id ? theme.accentPrimaryDark : theme.borderNormal
                border.width: 1

                RowLayout {
                    anchors.fill: parent
                    anchors.leftMargin: 10
                    anchors.rightMargin: 10
                    spacing: 8

                    Text {
                        text: modelData.index
                        color: sessionStore.selectedPhaseId === modelData.id ? "white" : theme.textMuted
                        font.pixelSize: 10
                        font.bold: true
                        Layout.preferredWidth: 16
                    }
                    ColumnLayout {
                        spacing: 1
                        Layout.fillWidth: true
                        Text {
                            text: modelData.name
                            color: sessionStore.selectedPhaseId === modelData.id ? "white" : (modelData.implemented ? theme.textPrimary : theme.textMuted)
                            font.pixelSize: 12
                            font.bold: modelData.current
                            Layout.fillWidth: true
                            elide: Text.ElideRight
                        }
                        Text {
                            text: modelData.actionable ? GuiText.actionableShort : (modelData.implemented ? GuiText.connectedShort : modelData.handoff_task)
                            color: sessionStore.selectedPhaseId === modelData.id ? theme.textPrimary : theme.textMuted
                            font.pixelSize: 9
                            Layout.fillWidth: true
                            elide: Text.ElideRight
                        }
                    }
                }

                MouseArea {
                    anchors.fill: parent
                    hoverEnabled: true
                    onClicked: sessionStore.selectPhase(modelData.id)
                    cursorShape: Qt.PointingHandCursor
                }
            }
        }

        Item { Layout.fillHeight: true }

        // 底部快捷操作
        ColumnLayout {
            spacing: 6
            Layout.bottomMargin: 8

            AppButton {
                Layout.fillWidth: true
                text: GuiText.refreshStatus
                type: "secondary"
                onClicked: sessionStore.refreshSnapshot()
            }
            AppButton {
                Layout.fillWidth: true
                text: GuiText.phaseHelp
                type: "secondary"
                onClicked: sessionStore.logUiEvent(GuiText.phaseHelpRequested)
            }
        }
    }
}
