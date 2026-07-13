import QtQuick 2.15
import QtQuick.Controls 2.15
import QtQuick.Layouts 1.15

import "../components"
import "../i18n"

/*!
 * \brief QueryResultOverlay — v3.25.1 visual alignment
 *
 * Matches HTML prototype modal:
 *   overlay: rgba(28,18,12,.45) + backdrop-filter blur(2px)
 *   dialog: #FFF7E8, bronze border, 12px radius
 *   header: dark-red with gold text
 *   content: parchment background, label-value items
 */
Rectangle {
    id: root
    objectName: "queryResultOverlay"
    color: "#720C1207"
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
        width: Math.min(parent.width - 160, 560)
        height: Math.min(parent.height - 140, 520)
        anchors.centerIn: parent
        color: "#FFF7E8"
        border.color: "#B8D9AF63"
        border.width: 2
        radius: 12

        MouseArea {
            anchors.fill: parent
        }

        ColumnLayout {
            anchors.fill: parent
            anchors.margins: 0
            spacing: 0

            // Header bar
            Rectangle {
                Layout.fillWidth: true
                Layout.preferredHeight: 40
                color: "#8B2500"
                radius: 10

                RowLayout {
                    anchors.fill: parent
                    anchors.margins: 12
                    spacing: 8

                    Text {
                        text: sessionStore.globalQueryResult.title || GuiText.queryResultTitle
                        color: "#FFD700"
                        font.pixelSize: 14
                        font.bold: true
                        Layout.fillWidth: true
                        elide: Text.ElideRight
                    }

                    // Status badge
                    Text {
                        text: {
                            var s = sessionStore.globalQueryResult.status
                            if (s === "connected") return GuiText.queryStatusConnected
                            if (s === "readonly") return GuiText.queryStatusReadonly
                            return GuiText.queryStatusPlaceholder
                        }
                        color: {
                            var s = sessionStore.globalQueryResult.status
                            if (s === "connected") return "#70A17C"
                            if (s === "readonly") return "#6C8FA1"
                            return "#C4933D"
                        }
                        font.pixelSize: 10
                        font.bold: true
                    }

                    // Close button
                    Rectangle {
                        Layout.preferredWidth: 60
                        Layout.preferredHeight: 24
                        color: "#DAB77F"
                        border.color: "#C9A84C"
                        border.width: 1
                        radius: 4

                        Text {
                            anchors.centerIn: parent
                            text: GuiText.closeQueryResult
                            color: "#3A3530"
                            font.pixelSize: 10
                            font.bold: true
                        }

                        MouseArea {
                            anchors.fill: parent
                            cursorShape: Qt.PointingHandCursor
                            onClicked: root.close()
                        }
                    }
                }
            }

            // Divider
            Rectangle {
                Layout.fillWidth: true
                height: 1
                color: "#D4A574"
            }

            // Content area
            Rectangle {
                Layout.fillWidth: true
                Layout.fillHeight: true
                color: "#FFF7E8"

                ColumnLayout {
                    anchors.fill: parent
                    anchors.margins: 14
                    spacing: 8

                    // Status message
                    Text {
                        text: sessionStore.globalQueryResult.message || GuiText.queryResultEmpty
                        color: "#8B7355"
                        font.pixelSize: 12
                        wrapMode: Text.Wrap
                        Layout.fillWidth: true
                    }

                    // Divider
                    Rectangle {
                        Layout.fillWidth: true
                        height: 1
                        color: "#40C9A84C"
                    }

                    // Data items list
                    ScrollView {
                        Layout.fillWidth: true
                        Layout.fillHeight: true
                        clip: true

                        ColumnLayout {
                            width: parent.width
                            spacing: 6

                            Repeater {
                                model: sessionStore.globalQueryResult.items || []
                                delegate: Rectangle {
                                    Layout.fillWidth: true
                                    height: Math.max(28, itemRow.implicitHeight + 12)
                                    color: "#FFFDF5"
                                    border.color: "#6BC9A84C"
                                    border.width: 1
                                    radius: 6

                                    RowLayout {
                                        id: itemRow
                                        anchors.left: parent.left
                                        anchors.right: parent.right
                                        anchors.margins: 10
                                        anchors.verticalCenter: parent.verticalCenter
                                        spacing: 10

                                        Text {
                                            text: modelData.label
                                            color: "#8B2500"
                                            font.pixelSize: 12
                                            font.bold: true
                                            Layout.preferredWidth: 140
                                            wrapMode: Text.Wrap
                                        }
                                        Text {
                                            text: modelData.value
                                            color: "#3A3530"
                                            font.pixelSize: 12
                                            Layout.fillWidth: true
                                            wrapMode: Text.Wrap
                                        }
                                    }
                                }
                            }

                            // Empty state
                            Text {
                                visible: !sessionStore.globalQueryResult.items || sessionStore.globalQueryResult.items.length === 0
                                text: GuiText.queryResultEmpty
                                color: "#9B856B"
                                font.pixelSize: 12
                                wrapMode: Text.Wrap
                                Layout.fillWidth: true
                                Layout.topMargin: 8
                            }
                        }
                    }
                }
            }
        }
    }
}
