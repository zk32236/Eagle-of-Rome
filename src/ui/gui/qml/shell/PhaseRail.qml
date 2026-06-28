import QtQuick 2.15
import QtQuick.Controls 2.15
import QtQuick.Layouts 1.15

import "../components"

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
            text: "年度阶段"
            color: theme.textMuted
            font.pixelSize: 11
            font.bold: true
            Layout.bottomMargin: 8
        }

        Repeater {
            model: sessionStore.phaseNavigation || []
            delegate: Rectangle {
                Layout.fillWidth: true
                height: 36
                radius: theme.radius
                color: {
                    if (modelData.current) return theme.accentPrimary
                    if (modelData.executed) return theme.bgSurface2
                    return "transparent"
                }
                border.color: modelData.current ? theme.accentPrimaryDark : "transparent"
                border.width: 1

                RowLayout {
                    anchors.fill: parent
                    anchors.leftMargin: 10
                    anchors.rightMargin: 10
                    spacing: 8

                    Text {
                        text: modelData.index
                        color: modelData.current ? "white" : theme.textMuted
                        font.pixelSize: 10
                        font.bold: true
                        Layout.preferredWidth: 16
                    }
                    Text {
                        text: modelData.name
                        color: modelData.current ? "white" : (modelData.executed ? theme.textSecondary : theme.textMuted)
                        font.pixelSize: 12
                        Layout.fillWidth: true
                    }
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
                text: "💾 保存进度"
                type: "secondary"
                onClicked: sessionStore.logUiEvent("Save requested")
            }
            AppButton {
                Layout.fillWidth: true
                text: "📖 规则帮助"
                type: "secondary"
                onClicked: sessionStore.logUiEvent("Help requested")
            }
        }
    }
}
