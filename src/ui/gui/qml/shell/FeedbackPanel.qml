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

    // 暴露方法
    function show(type, message) {
        feedbackList.append(type, message)
    }

    // H0.3: EventLog compression — reduced margins and spacing for tighter layout
    ColumnLayout {
        anchors.fill: parent
        anchors.margins: 8
        spacing: 4

        // 标题栏 — compressed
        RowLayout {
            Layout.fillWidth: true
            Text {
                text: GuiText.feedbackLogTitle
                color: theme.textMuted
                font.pixelSize: 10
                font.bold: true
            }
            Item { Layout.fillWidth: true }
            AppButton {
                text: GuiText.clearFeedback
                type: "ghost"
                fontSize: 9
                onClicked: feedbackList.clear()
            }
        }

        // 事件列表 — compressed
        ListView {
            id: feedbackList
            Layout.fillWidth: true
            Layout.fillHeight: true
            clip: true
            spacing: 2

            function append(type, message) {
                var color = theme.textSecondary
                if (type === "success") color = theme.statusSuccess
                if (type === "error") color = theme.statusError
                if (type === "warning") color = theme.statusWarning
                if (type === "info") color = theme.statusInfo
                model.append({timestamp: Qt.formatTime(new Date(), "hh:mm:ss"), type: type, message: message, typeColor: color})
            }

            function clear() {
                model.clear()
            }

            model: ListModel {}

            delegate: Rectangle {
                width: feedbackList.width
                height: 22
                color: "transparent"
                RowLayout {
                    anchors.fill: parent
                    spacing: 4
                    Text {
                        text: timestamp
                        color: theme.textMuted
                        font.pixelSize: 9
                        font.family: "Consolas, monospace"
                        Layout.preferredWidth: 46
                    }
                    Text {
                        text: type.toUpperCase()
                        color: typeColor
                        font.pixelSize: 9
                        font.bold: true
                        Layout.preferredWidth: 48
                    }
                    Text {
                        text: message
                        color: theme.textSecondary
                        font.pixelSize: 10
                        Layout.fillWidth: true
                        elide: Text.ElideRight
                    }
                }
            }

            // 初始欢迎消息
            Component.onCompleted: {
                append("info", GuiText.guiSessionStarted)
                append("info", GuiText.currentPhaseLogPrefix + (sessionStore.currentPhaseName || ""))
            }
        }
    }
}
