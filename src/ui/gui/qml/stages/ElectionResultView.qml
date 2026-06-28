import QtQuick 2.15
import QtQuick.Controls 2.15
import QtQuick.Layouts 1.15

import "../components"

Rectangle {
    id: root
    color: theme.bgSurface1
    radius: theme.radius
    border.color: theme.borderNormal
    border.width: 1

    ColumnLayout {
        anchors.fill: parent
        anchors.margins: 16
        spacing: 16

        Text {
            text: "🏆 选举结果"
            color: theme.textPrimary
            font.pixelSize: 14
            font.bold: true
        }

        Text {
            text: "所有玩家投票完成后，点击结算按钮查看选举结果。"
            color: theme.textSecondary
            font.pixelSize: 11
        }

        AppButton {
            text: "🗳️ 结算选举"
            type: "primary"
            Layout.preferredWidth: 200
            onClicked: {
                var result = sessionStore.doResolveElection()
                if (result.success) {
                    showFeedback("success", "选举已结算")
                } else {
                    showFeedback("error", result.message)
                }
            }
        }

        // 结果列表占位
        Rectangle {
            Layout.fillWidth: true
            Layout.fillHeight: true
            color: theme.bgSurface2
            radius: theme.radius
            border.color: theme.borderNormal

            EmptyState {
                anchors.centerIn: parent
                icon: "🏛️"
                title: "等待结算"
                subtitle: "请先完成所有玩家的投票操作"
            }
        }
    }
}
