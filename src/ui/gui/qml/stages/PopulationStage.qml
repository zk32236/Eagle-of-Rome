import QtQuick 2.15
import QtQuick.Controls 2.15
import QtQuick.Layouts 1.15

import "../components"

Rectangle {
    id: root
    color: theme.bgApp

    ColumnLayout {
        anchors.fill: parent
        anchors.margins: 20
        spacing: 16

        // 标题 + 进度
        RowLayout {
            Layout.fillWidth: true
            spacing: 16
            Text {
                text: "人口阶段"
                color: theme.textPrimary
                font.pixelSize: 18
                font.family: theme.fontTitle
                font.bold: true
            }
            Text {
                text: "为候选人物举办庆典，并代表派系为共和国公职投票。"
                color: theme.textSecondary
                font.pixelSize: 12
                Layout.fillWidth: true
                wrapMode: Text.Wrap
            }
            Text {
                text: "庆典与拉票 · 2/5"
                color: theme.accentBronze
                font.pixelSize: 12
                font.bold: true
            }
        }

        // Tab 切换
        RowLayout {
            spacing: 0
            Layout.fillWidth: true

            Repeater {
                model: [
                    {text: "庆典与拉票", id: "festival"},
                    {text: "公职投票", id: "vote"},
                    {text: "选举结果", id: "result"}
                ]
                delegate: Rectangle {
                    Layout.preferredWidth: 120
                    Layout.preferredHeight: 36
                    color: tabView.currentIndex === index ? theme.bgSurface2 : "transparent"
                    border.color: tabView.currentIndex === index ? theme.borderStrong : "transparent"
                    border.width: 1

                    Text {
                        anchors.centerIn: parent
                        text: modelData.text
                        color: tabView.currentIndex === index ? theme.textPrimary : theme.textMuted
                        font.pixelSize: 12
                        font.bold: tabView.currentIndex === index
                    }

                    MouseArea {
                        anchors.fill: parent
                        onClicked: tabView.currentIndex = index
                    }
                }
            }
        }

        // 内容区
        StackLayout {
            id: tabView
            Layout.fillWidth: true
            Layout.fillHeight: true
            currentIndex: 0

            FestivalView {}
            VoteView {}
            ElectionResultView {}
        }
    }
}
