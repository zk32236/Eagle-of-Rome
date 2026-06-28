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
        anchors.margins: 16
        spacing: 12

        // 标题
        Text {
            text: "📋 派系资源"
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
                label: "已投官职"
                value: Object.keys(sessionStore.myVotes || {}).length + " / 5"
                icon: "🗳️"
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
            text: "🎯 当前目标"
            color: theme.textMuted
            font.pixelSize: 11
            font.bold: true
        }

        ColumnLayout {
            spacing: 6
            Text {
                text: "• 选择本派系候选人物举办庆典"
                color: theme.textSecondary
                font.pixelSize: 11
                wrapMode: Text.Wrap
                Layout.fillWidth: true
            }
            Text {
                text: "• 投入不得超过人物当前财富"
                color: theme.textSecondary
                font.pixelSize: 11
                wrapMode: Text.Wrap
                Layout.fillWidth: true
            }
            Text {
                text: "• 为每个共和国公职投出一票"
                color: theme.textSecondary
                font.pixelSize: 11
                wrapMode: Text.Wrap
                Layout.fillWidth: true
            }
            Text {
                text: "• 完成后切换玩家，隐藏上一派系信息"
                color: theme.textSecondary
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
                text: "当前权限：可操作 " + (sessionStore.viewerFactionId || "Optimates") + " 派系人物；其他派系人物和金库详情不可见。"
                color: theme.textMuted
                font.pixelSize: 10
                wrapMode: Text.Wrap
                verticalAlignment: Text.AlignVCenter
            }
        }

        Item { Layout.fillHeight: true }

        // 流程控制
        ColumnLayout {
            Layout.fillWidth: true
            spacing: 8

            AppButton {
                Layout.fillWidth: true
                text: "✅ 完成当前玩家操作"
                type: "primary"
                enabled: sessionStore.isCurrentPlayer && sessionStore.canComplete
                onClicked: {
                    var result = sessionStore.doCompletePlayer()
                    if (!result.success) {
                        showFeedback("error", result.message)
                    }
                }
            }
            AppButton {
                Layout.fillWidth: true
                text: "⏭ 跳过剩余操作"
                type: "secondary"
                onClicked: sessionStore.logUiEvent("Skip requested")
            }
        }
    }
}
