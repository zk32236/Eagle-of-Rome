import QtQuick 2.15
import QtQuick.Controls 2.15
import QtQuick.Layouts 1.15

import "../components"

Rectangle {
    id: root
    color: theme.bgSurface1
    border.color: theme.borderNormal
    border.width: 1

    // 暴露方法
    function show(type, message) {
        feedbackList.append(type, message)
    }

    ColumnLayout {
        anchors.fill: parent
        anchors.margins: 12
        spacing: 8

        // 标题栏
        RowLayout {
            Layout.fillWidth: true
            Text {
                text: "📢 结构化反馈与最近事件"
                color: theme.textMuted
                font.pixelSize: 11
                font.bold: true
            }
            Item { Layout.fillWidth: true }
            AppButton {
                text: "清空"
                type: "ghost"
                fontSize: 10
                onClicked: feedbackList.clear()
            }
        }

        // 事件列表
        ListView {
            id: feedbackList
            Layout.fillWidth: true
            Layout.fillHeight: true
            clip: true
            spacing: 4

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
                height: 28
                color: "transparent"
                RowLayout {
                    anchors.fill: parent
                    spacing: 8
                    Text {
                        text: timestamp
                        color: theme.textMuted
                        font.pixelSize: 10
                        font.family: "Consolas, monospace"
                        Layout.preferredWidth: 50
                    }
                    Text {
                        text: type.toUpperCase()
                        color: typeColor
                        font.pixelSize: 10
                        font.bold: true
                        Layout.preferredWidth: 60
                    }
                    Text {
                        text: message
                        color: theme.textSecondary
                        font.pixelSize: 11
                        Layout.fillWidth: true
                        elide: Text.ElideRight
                    }
                }
            }

            // 初始欢迎消息
            Component.onCompleted: {
                append("info", "GUI 会话已启动")
                append("info", "当前阶段：人口阶段")
            }
        }
    }
}
