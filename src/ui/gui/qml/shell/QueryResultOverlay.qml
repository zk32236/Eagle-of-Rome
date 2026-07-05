import QtQuick 2.15
import QtQuick.Controls 2.15
import QtQuick.Layouts 1.15

import "../components"
import "../i18n"

Rectangle {
    id: root
    objectName: "queryResultOverlay"
    color: "#99000000"
    visible: false
    z: 80

    function open() {
        visible = true
    }

    function close() {
        visible = false
    }

    MouseArea {
        anchors.fill: parent
        onClicked: root.close()
    }

    Rectangle {
        id: dialog
        objectName: "queryResultDialog"
        width: Math.min(parent.width - 160, 720)
        height: Math.min(parent.height - 140, 520)
        anchors.centerIn: parent
        color: theme.bgSurface1
        border.color: theme.borderStrong
        border.width: 1
        radius: theme.radius

        MouseArea {
            anchors.fill: parent
        }

        ColumnLayout {
            anchors.fill: parent
            anchors.margins: 18
            spacing: 12

            RowLayout {
                Layout.fillWidth: true
                spacing: 12

                ColumnLayout {
                    Layout.fillWidth: true
                    spacing: 4
                    Text {
                        text: sessionStore.globalQueryResult.title || GuiText.queryResultTitle
                        color: theme.textPrimary
                        font.pixelSize: 18
                        font.family: theme.fontTitle
                        font.bold: true
                        Layout.fillWidth: true
                        wrapMode: Text.Wrap
                    }
                    Text {
                        text: GuiText.queryStatusText(sessionStore.globalQueryResult.status)
                        color: sessionStore.globalQueryResult.status === "placeholder" ? theme.statusWarning : theme.statusInfo
                        font.pixelSize: 11
                        font.bold: true
                    }
                }

                AppButton {
                    Layout.preferredWidth: 86
                    text: GuiText.closeQueryResult
                    type: "secondary"
                    onClicked: root.close()
                }
            }

            Rectangle {
                Layout.fillWidth: true
                height: 1
                color: theme.borderNormal
            }

            Text {
                text: sessionStore.globalQueryResult.message || GuiText.queryResultEmpty
                color: theme.textSecondary
                font.pixelSize: 12
                wrapMode: Text.Wrap
                Layout.fillWidth: true
            }

            ScrollView {
                Layout.fillWidth: true
                Layout.fillHeight: true
                clip: true

                ColumnLayout {
                    width: parent.width
                    spacing: 8

                    Repeater {
                        model: sessionStore.globalQueryResult.items || []
                        delegate: Rectangle {
                            Layout.fillWidth: true
                            height: row.implicitHeight + 18
                            color: theme.bgSurface2
                            border.color: theme.borderNormal
                            border.width: 1
                            radius: theme.radius

                            RowLayout {
                                id: row
                                anchors.left: parent.left
                                anchors.right: parent.right
                                anchors.margins: 10
                                anchors.verticalCenter: parent.verticalCenter
                                spacing: 12

                                Text {
                                    text: modelData.label
                                    color: theme.accentBronze
                                    font.pixelSize: 12
                                    font.bold: true
                                    Layout.preferredWidth: 150
                                    wrapMode: Text.Wrap
                                }
                                Text {
                                    text: modelData.value
                                    color: theme.textPrimary
                                    font.pixelSize: 12
                                    Layout.fillWidth: true
                                    wrapMode: Text.Wrap
                                }
                            }
                        }
                    }

                    Text {
                        visible: !sessionStore.globalQueryResult.items || sessionStore.globalQueryResult.items.length === 0
                        text: GuiText.queryResultEmpty
                        color: theme.textMuted
                        font.pixelSize: 12
                        wrapMode: Text.Wrap
                        Layout.fillWidth: true
                    }
                }
            }
        }
    }
}
