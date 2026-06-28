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

        // 标题
        RowLayout {
            Layout.fillWidth: true
            Text {
                text: "👥 本派系人物"
                color: theme.textPrimary
                font.pixelSize: 14
                font.bold: true
            }
            Text {
                text: "仅显示当前玩家有权操作的人物"
                color: theme.textMuted
                font.pixelSize: 10
            }
            Item { Layout.fillWidth: true }
        }

        // 人物表格
        DataTable {
            id: figureTable
            Layout.fillWidth: true
            Layout.fillHeight: true
            columns: [
                {title: "人物", width: 180, role: "name"},
                {title: "财富", width: 80, role: "wealth"},
                {title: "人气", width: 80, role: "popularity"},
                {title: "影响力", width: 80, role: "influence"},
                {title: "资格", width: 100, role: "office"}
            ]
            modelData: sessionStore.myFigures || []
        }

        // 庆典决策区
        Rectangle {
            Layout.fillWidth: true
            Layout.preferredHeight: 160
            color: theme.bgSurface2
            radius: theme.radius
            border.color: theme.borderNormal
            border.width: 1

            ColumnLayout {
                anchors.fill: parent
                anchors.margins: 16
                spacing: 12

                Text {
                    text: "🎉 庆典决策"
                    color: theme.textPrimary
                    font.pixelSize: 13
                    font.bold: true
                }

                RowLayout {
                    spacing: 16
                    Text {
                        text: "选择人物："
                        color: theme.textSecondary
                        font.pixelSize: 12
                    }
                    Text {
                        text: figureTable.selectedRow >= 0 ? (sessionStore.myFigures[figureTable.selectedRow]?.name || "") : "从人物列表中选择一名人物"
                        color: figureTable.selectedRow >= 0 ? theme.accentBronzeHighlight : theme.textMuted
                        font.pixelSize: 12
                        font.bold: figureTable.selectedRow >= 0
                    }
                }

                RowLayout {
                    spacing: 16
                    Text {
                        text: "投入金额："
                        color: theme.textSecondary
                        font.pixelSize: 12
                    }
                    NumberStepper {
                        id: amountStepper
                        value: 10
                        minValue: 1
                        maxValue: 100
                    }
                }

                RowLayout {
                    spacing: 12
                    AppButton {
                        text: "取消"
                        type: "secondary"
                        onClicked: {
                            figureTable.selectedRow = -1
                            amountStepper.value = 10
                        }
                    }
                    AppButton {
                        text: "确认举办庆典"
                        type: "primary"
                        enabled: figureTable.selectedRow >= 0 && sessionStore.isCurrentPlayer && sessionStore.canCampaign
                        onClicked: {
                            if (figureTable.selectedRow < 0) return
                            var fig = sessionStore.myFigures[figureTable.selectedRow]
                            var result = sessionStore.doCampaign(fig.id, amountStepper.value)
                            if (result.success) {
                                showFeedback("success", result.message)
                                figureTable.selectedRow = -1
                            } else {
                                showFeedback("error", result.message)
                            }
                        }
                    }
                }
            }
        }
    }
}
