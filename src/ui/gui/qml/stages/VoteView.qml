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
                    text: "🗳️ 公职投票"
                    color: theme.textPrimary
                    font.pixelSize: 14
                    font.bold: true
                }
                Text {
                    text: "每个官职只能投一票，重复投票将被拒绝"
                    color: theme.textMuted
                    font.pixelSize: 10
                }
                Item { Layout.fillWidth: true }
            }

            // 官职标签
            RowLayout {
                spacing: 0
                Repeater {
                    model: ["consul", "censor", "praetor", "quaestor", "tribune"]
                    delegate: Rectangle {
                        Layout.preferredWidth: 100
                        Layout.preferredHeight: 32
                        color: voteTab.currentIndex === index ? theme.accentPrimary : "transparent"
                        border.color: voteTab.currentIndex === index ? theme.accentPrimaryDark : "transparent"
                        border.width: 1
                        Text {
                            anchors.centerIn: parent
                            text: {
                                var names = {consul: "执政官", censor: "监察官", praetor: "大法官", quaestor: "财务官", tribune: "保民官"}
                                return names[modelData] || modelData
                            }
                            color: voteTab.currentIndex === index ? "white" : theme.textMuted
                            font.pixelSize: 11
                            font.bold: voteTab.currentIndex === index
                        }
                        MouseArea {
                            anchors.fill: parent
                            onClicked: voteTab.currentIndex = index
                        }
                    }
                }
            }

            // 候选人列表
            StackLayout {
                id: voteTab
                Layout.fillWidth: true
                Layout.fillHeight: true
                currentIndex: 0

                Repeater {
                    model: ["consul", "censor", "praetor", "quaestor", "tribune"]
                    delegate: Rectangle {
                        color: "transparent"
                        ColumnLayout {
                            anchors.fill: parent
                            spacing: 12

                            Text {
                                text: {
                                    var names = {consul: "执政官候选人", censor: "监察官候选人", praetor: "大法官候选人", quaestor: "财务官候选人", tribune: "保民官候选人"}
                                    return names[modelData] || modelData
                                }
                                color: theme.textSecondary
                                font.pixelSize: 12
                            }

                            ListView {
                                Layout.fillWidth: true
                                Layout.fillHeight: true
                                clip: true
                                spacing: 8
                                model: {
                                    var cands = sessionStore.populationCandidates || []
                                    return cands.filter(function(c) { return c.office === modelData })
                                }
                                delegate: Rectangle {
                                    width: parent.width
                                    height: 48
                                    color: selected ? theme.accentPrimary : theme.bgSurface2
                                    radius: theme.radius
                                    border.color: selected ? theme.accentPrimaryDark : theme.borderNormal
                                    border.width: 1
                                    property bool selected: false

                                    RowLayout {
                                        anchors.fill: parent
                                        anchors.margins: 12
                                        spacing: 12
                                        Text {
                                            text: modelData.name
                                            color: selected ? "white" : theme.textPrimary
                                            font.pixelSize: 12
                                            font.bold: true
                                            Layout.preferredWidth: 150
                                        }
                                        Text {
                                            text: modelData.faction_name
                                            color: selected ? "#EEEAE1" : theme.textSecondary
                                            font.pixelSize: 11
                                            Layout.preferredWidth: 100
                                        }
                                        Text {
                                            text: "军" + (modelData.martial || 0) + " 智" + (modelData.intelligence || 0) + " 魅" + (modelData.charisma || 0)
                                            color: selected ? "#EEEAE1" : theme.textMuted
                                            font.pixelSize: 10
                                            Layout.preferredWidth: 120
                                        }
                                        Item { Layout.fillWidth: true }
                                        AppButton {
                                            text: selected ? "已选择" : "选择"
                                            type: selected ? "primary" : "secondary"
                                            fontSize: 10
                                            onClicked: {
                                                selected = !selected
                                            }
                                        }
                                    }
                                }
                            }
                        }
                    }
                }
            }

            // 投票确认
            RowLayout {
                spacing: 12
                AppButton {
                    text: "取消选择"
                    type: "secondary"
                    onClicked: voteTab.currentIndex = 0
                }
                AppButton {
                    text: "确认投票"
                    type: "primary"
                    enabled: sessionStore.isCurrentPlayer && sessionStore.canVote
                    onClicked: {
                        // 简化：使用当前选中官职的第一个候选人
                        var office = ["consul", "censor", "praetor", "quaestor", "tribune"][voteTab.currentIndex]
                        var cands = (sessionStore.populationCandidates || []).filter(function(c) { return c.office === office })
                        if (cands.length > 0) {
                            var result = sessionStore.doVote(office, cands[0].id)
                            if (result.success) {
                                showFeedback("success", result.message)
                            } else {
                                showFeedback("error", result.message)
                            }
                        }
                    }
                }
            }
        }
    }
