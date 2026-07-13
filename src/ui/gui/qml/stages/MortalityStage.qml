import QtQuick 2.15
import QtQuick.Controls 2.15
import QtQuick.Layouts 1.15

import "../components"
import "../i18n"

/*!
 * \brief MortalityStage — H0 streamlined: event content area only.
 *
 * H0 change: removed self-contained parallel slot structure
 * (header / instruction / action). Header, instruction bar, and
 * execute button are now distributed to StageDesktop's 4 slots
 * by GameShell. This component fills only StageDesktop.stageContentSlot.
 *
 * Layout contract: GUI_LAYOUT_CONTRACT_Phase1_v3.25.1.md §4
 *   StageContentSlot: event area with info-box style
 */
Rectangle {
    id: root
    objectName: "mortalityStage"
    color: "transparent"

    ColumnLayout {
        anchors.fill: parent
        spacing: 10

        // Before execution: instruction card.
        Rectangle {
            visible: (sessionStore.mortalityEvents || []).length === 0
            Layout.fillWidth: true
            Layout.preferredHeight: promptText.implicitHeight + 26
            color: "#B8FFF9EC"
            border.color: "#85A8753B"
            border.width: 1
            radius: theme.radius

            Text {
                id: promptText
                anchors.fill: parent
                anchors.margins: 13
                text: "🎴 点击下方「执行天命」按钮，触发一个随机事件。\n事件类型：猝死"
                color: "#2E251B"
                font.pixelSize: theme.bodySize
                wrapMode: Text.Wrap
            }
        }

        // After execution: resolved status strip.
        Rectangle {
            visible: (sessionStore.mortalityEvents || []).length > 0
            Layout.fillWidth: true
            Layout.preferredHeight: 42
            color: "#EFFFF2"
            border.color: "#2FA03A"
            border.width: 1
            radius: 5

            Row {
                anchors.left: parent.left
                anchors.leftMargin: 14
                anchors.verticalCenter: parent.verticalCenter
                spacing: 7

                Text {
                    text: "✅"
                    font.pixelSize: 13
                    anchors.verticalCenter: parent.verticalCenter
                }
                Text {
                    text: GuiText.mortalityResolved
                    color: "#2E251B"
                    font.pixelSize: theme.bodySize
                    anchors.verticalCenter: parent.verticalCenter
                }
            }
        }

        Row {
            visible: (sessionStore.mortalityEvents || []).length > 0
            Layout.fillWidth: true
            spacing: 6

            Text {
                text: "🎴"
                font.pixelSize: 13
                anchors.verticalCenter: parent.verticalCenter
            }
            Text {
                text: GuiText.mortalityEventsTitle
                color: "#681B07"
                font.pixelSize: 13
                font.bold: true
                anchors.verticalCenter: parent.verticalCenter
            }
        }

        // Event items.
        Repeater {
            model: sessionStore.mortalityEvents || []
            delegate: Rectangle {
                Layout.fillWidth: true
                height: 34
                color: "#B8FFF9EC"
                border.color: "#85A8753B"
                border.width: 1
                radius: 4

                RowLayout {
                    anchors.fill: parent
                    anchors.leftMargin: 12
                    anchors.rightMargin: 12
                    spacing: 7

                    Text {
                        text: modelData.effect === "death" ? "💀" : "⚡"
                        font.pixelSize: 13
                        anchors.verticalCenter: parent.verticalCenter
                    }
                    Text {
                        text: (modelData.name || "") + (modelData.summary ? "  " + modelData.summary : "")
                        color: "#2E251B"
                        font.pixelSize: theme.bodySize
                        elide: Text.ElideRight
                        Layout.fillWidth: true
                        anchors.verticalCenter: parent.verticalCenter
                    }
                    Text {
                        text: modelData.summary || ""
                        color: "#C45151"
                        font.pixelSize: theme.bodySize
                        visible: !!modelData.summary
                        elide: Text.ElideRight
                        Layout.maximumWidth: 360
                        anchors.verticalCenter: parent.verticalCenter
                    }
                }
            }
        }

        Item {
            Layout.fillWidth: true
            Layout.fillHeight: true
        }
    }

    // Forward feedback to parent context panel
    function showFeedback(type, message) {
        var cp = root.parent
        while (cp && cp.objectName !== "contextPanel") {
            cp = cp.parent
        }
        if (cp && cp.showFeedback) {
            cp.showFeedback(type, message)
        }
    }
}
