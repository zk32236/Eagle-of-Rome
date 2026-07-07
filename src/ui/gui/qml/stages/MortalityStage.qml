import QtQuick 2.15
import QtQuick.Controls 2.15
import QtQuick.Layouts 1.15

import "../components"
import "../i18n"

/**
 * MortalityStage.qml — 天命阶段 GUI
 * 对齐 V3.23 原型 + V2.0 设计规范 §3.1
 *
 * 布局：
 *   顶部：阶段徽标(1/7) + 标题 + 描述
 *   步骤指示条：①执行天命 → ②查看事件结果
 *   中央：事件展示区（初始为提示信息，执行后替换为事件结果）
 *   底部：圆形金色按钮「⚡ 执行天命」→ 执行后灰化→「进入收入」按钮
 *
 * 关键交互：
 *   - 居中金色圆形按钮「神的旨意」
 *   - 点击后按钮灰化 + 文案改为「✅ 已执行」
 *   - 事件结果在主界面直接展示（非弹窗）
 *   - 死亡事件显示：死者名称/派系/损失土地/损失财富
 */
Rectangle {
    id: root
    color: theme.bgApp

    ColumnLayout {
        anchors.fill: parent
        anchors.margins: 6
        spacing: 3

        // ── 顶部：徽标 + 标题 + 描述（Phase-4 §6：边框降重，集成感）──
        Rectangle {
            Layout.fillWidth: true
            Layout.preferredHeight: 38
            color: theme.bgSurface1
            border.color: Qt.rgba(0,0,0,0.08)
            border.width: 1
            radius: theme.radius

            RowLayout {
                anchors.fill: parent
                anchors.margins: 8
                spacing: 6

                // 阶段编号徽标（Phase-3 §6.3：缩小）
                Rectangle {
                    width: 24; height: 24; radius: 12
                    color: "#8B2500"
                    border.color: "#FFD700"
                    border.width: 2
                    Text {
                        anchors.centerIn: parent
                        text: GuiText.mortalityBadge
                        color: "#FFD700"
                        font.pixelSize: 9
                        font.bold: true
                    }
                }

                ColumnLayout {
                    Layout.fillWidth: true
                    spacing: 1
                    Text {
                        text: "🎴 " + GuiText.mortalityTitle
                        color: theme.textPrimary
                        font.pixelSize: 13
                        font.family: theme.fontTitle
                        font.bold: true
                    }
                    Text {
                        text: "众神降下命运——触发一个随机事件。无玩家操作。"
                        color: theme.textSecondary
                        font.pixelSize: 8
                        wrapMode: Text.Wrap
                        Layout.fillWidth: true
                    }
                }

                // Phase-3 §6.3：移除「就绪」状态标签 — Design 原型中不存在
            }
        }

        // ── 步骤指示条（左对齐紧凑，Phase-4 §7：外边框移除）──
        Rectangle {
            Layout.fillWidth: true
            Layout.preferredHeight: 26
            color: theme.bgSurface2
            border.width: 0
            radius: theme.radius

            RowLayout {
                anchors.left: parent.left
                anchors.leftMargin: 10
                anchors.verticalCenter: parent.verticalCenter
                spacing: 6

                // 步骤1：执行天命
                RowLayout {
                    spacing: 4
                    Rectangle {
                        width: 14; height: 14; radius: 7
                        color: sessionStore.canAdvanceMortality ? "#E8A030" : theme.accentBronze
                        Text {
                            anchors.centerIn: parent
                            text: "1"
                            color: "white"
                            font.pixelSize: 8; font.bold: true
                        }
                    }
                    Text {
                        text: "⚡ " + GuiText.mortalityStepExecute
                        color: sessionStore.canAdvanceMortality ? theme.textMuted : theme.textPrimary
                        font.pixelSize: 10
                        font.bold: !sessionStore.canAdvanceMortality
                    }
                }

                Text { text: "→"; color: theme.textMuted; font.pixelSize: 10 }

                // 步骤2：查看事件结果
                RowLayout {
                    spacing: 4
                    Rectangle {
                        width: 14; height: 14; radius: 7
                        color: sessionStore.canAdvanceMortality ? "#FFD700" : "#E8D5C4"
                        Text {
                            anchors.centerIn: parent
                            text: "2"
                            color: "white"
                            font.pixelSize: 8; font.bold: true
                        }
                    }
                    Text {
                        text: "📜 " + GuiText.mortalityStepView
                        color: sessionStore.canAdvanceMortality ? theme.textPrimary : theme.textMuted
                        font.pixelSize: 10
                    }
                }
            }
        }

        // ── 指令面板（Phase-4 §8：去卡片化，暖色分隔线代替全卡片边框）──
        Rectangle {
            Layout.fillWidth: true
            Layout.preferredHeight: 34  // 额外 2px 用于顶部暖色线
            color: "transparent"
            visible: !sessionStore.canAdvanceMortality  // 执行前显示

            // 顶部暖色分隔线
            Rectangle {
                anchors.top: parent.top
                anchors.left: parent.left
                anchors.right: parent.right
                height: 1
                color: "#E8D5C4"
            }

            ColumnLayout {
                anchors.fill: parent
                anchors.topMargin: 6
                anchors.leftMargin: 2
                anchors.rightMargin: 2
                spacing: 2
                Text {
                    text: "📕 点击下方「执行天命」按钮，触发一个随机事件。"
                    color: theme.textSecondary
                    font.pixelSize: 9
                }
                Text {
                    text: "事件类型：猝死 / 丰收 / 英雄 / 灾害 / 和平"
                    color: theme.textMuted
                    font.pixelSize: 8
                }
            }
        }

        // ── 中央：事件展示区（Phase-3 §10：去除内层面板，透明背景）──
        Rectangle {
            Layout.fillWidth: true
            Layout.fillHeight: true
            color: "transparent"

            // 初始提示（执行前）
            ColumnLayout {
                anchors.centerIn: parent
                spacing: 6
                visible: !sessionStore.mortalityEvent || !sessionStore.mortalityEvent.name

                Text {
                    Layout.alignment: Qt.AlignHCenter
                    text: "🎴"
                    font.pixelSize: 28
                }
                Text {
                    Layout.alignment: Qt.AlignHCenter
                    text: GuiText.mortalityHintInitial
                    color: theme.textSecondary
                    font.pixelSize: 11
                }
                Text {
                    Layout.alignment: Qt.AlignHCenter
                    text: "事件类型：猝死 / 丰收 / 英雄 / 灾害 / 和平"
                    color: theme.textMuted
                    font.pixelSize: 10
                }
            }

            // 事件结果卡片（执行后，单事件）
            ColumnLayout {
                anchors.fill: parent
                anchors.margins: 8
                spacing: 6
                visible: sessionStore.mortalityEvent && sessionStore.mortalityEvent.name

                // 结果标题（Phase-3 §9：紧凑奶油色，非全宽深红）
                Rectangle {
                    Layout.alignment: Qt.AlignHCenter
                    implicitWidth: resultLabel.implicitWidth + 16
                    Layout.preferredHeight: 24
                    color: theme.bgSurface2
                    border.color: theme.borderNormal
                    radius: 4
                    Text {
                        id: resultLabel
                        anchors.centerIn: parent
                        text: "🎴 天命已执行"
                        color: "#8B2500"
                        font.pixelSize: 10
                        font.bold: true
                    }
                }

                // 事件名称 + 摘要（所有事件类型共有）
                Rectangle {
                    Layout.fillWidth: true
                    Layout.preferredHeight: eventInfoColumn.implicitHeight + 14
                    color: "transparent"
                    border.width: 0

                    ColumnLayout {
                        id: eventInfoColumn
                        anchors.fill: parent
                        anchors.margins: 8
                        spacing: 4

                        Text {
                            text: sessionStore.mortalityEvent.name || ""
                            color: theme.accentBronze
                            font.pixelSize: 14
                            font.bold: true
                            Layout.fillWidth: true
                        }
                        Text {
                            text: sessionStore.mortalityEvent.summary || ""
                            color: theme.textSecondary
                            font.pixelSize: 11
                            wrapMode: Text.Wrap
                            Layout.fillWidth: true
                            visible: (sessionStore.mortalityEvent.summary || "") !== ""
                        }
                    }
                }

                // ── 死亡事件详情卡片 ──
                Rectangle {
                    Layout.fillWidth: true
                    Layout.fillHeight: true
                    color: "transparent"
                    visible: sessionStore.mortalityEvent.effect === "death"

                    // 死亡事件 impacts 列表
                    Flickable {
                        anchors.fill: parent
                        clip: true
                        contentHeight: deathDelegatesColumn.implicitHeight

                        ColumnLayout {
                            id: deathDelegatesColumn
                            width: parent.width
                            spacing: 4

                            Repeater {
                                model: (sessionStore.mortalityEvent.impacts || []).filter(function(imp) { return imp.type === "figure_death" })
                                delegate: Rectangle {
                                    Layout.fillWidth: true
                                    Layout.preferredHeight: deathCardColumn.implicitHeight + 12
                                    color: theme.bgSurface2
                                    border.color: "#E8A030"
                                    radius: 4

                                    ColumnLayout {
                                        id: deathCardColumn
                                        anchors.fill: parent
                                        anchors.margins: 8
                                        spacing: 3

                                        Text {
                                            text: "💀 " + (modelData.figure_name || "") + " 阵亡"
                                            color: "#8B2500"
                                            font.pixelSize: 13
                                            font.bold: true
                                        }

                                        // 四项字段网格
                                        GridLayout {
                                            columns: 2
                                            columnSpacing: 8
                                            rowSpacing: 3
                                            Layout.fillWidth: true

                                            Text { text: "🏛️ 所属派系："; color: theme.textSecondary; font.pixelSize: 11 }
                                            Text { text: modelData.faction_name || "无派系"; color: theme.textPrimary; font.pixelSize: 11; font.bold: true }

                                            Text { text: "🏞️ 土地损失："; color: theme.textSecondary; font.pixelSize: 11 }
                                            Text { text: (modelData.lost_land || 0) + " C（收归国库）"; color: "#FFD700"; font.pixelSize: 11; font.bold: true }

                                            Text { text: "💰 财富损失："; color: theme.textSecondary; font.pixelSize: 11 }
                                            Text { text: (modelData.lost_wealth || 0) + " Talents（收归国库）"; color: "#FFD700"; font.pixelSize: 11; font.bold: true }
                                        }

                                        // 终止合同
                                        Repeater {
                                            model: modelData.terminated_contracts || []
                                            delegate: Text {
                                                text: "📜 合同已终止：" + modelData.contract_name
                                                color: theme.textMuted
                                                font.pixelSize: 9
                                                Layout.fillWidth: true
                                            }
                                        }
                                    }
                                }
                            }
                        }
                    }
                }

                // ── 非死亡事件摘要（丰收/和平/英雄等） ──
                Rectangle {
                    Layout.fillWidth: true
                    Layout.fillHeight: true
                    color: "transparent"
                    border.width: 0
                    visible: sessionStore.mortalityEvent.effect !== "death"

                    ColumnLayout {
                        anchors.fill: parent
                        anchors.margins: 8
                        spacing: 4

                        Repeater {
                            model: sessionStore.mortalityEvent.impacts || []
                            delegate: ImpactDetail {
                                Layout.fillWidth: true
                                impactData: modelData
                            }
                        }
                    }
                }
            }
        }

        // ── 底部：操作按钮区（Phase-3 §11.3：更紧凑，柔和金边）──
        Rectangle {
            Layout.fillWidth: true
            Layout.preferredHeight: 34
            color: "transparent"

            // 执行按钮（紧凑，柔和金边）
            Rectangle {
                anchors.centerIn: parent
                width: 100
                height: 26
                radius: theme.radius
                color: sessionStore.canExecuteMortality ? "#8B2500" : theme.bgSurface2
                border.color: sessionStore.canExecuteMortality ? "#E8A030" : theme.borderNormal
                border.width: 1
                visible: !sessionStore.canAdvanceMortality
                enabled: sessionStore.canExecuteMortality

                Text {
                    anchors.centerIn: parent
                    text: sessionStore.canExecuteMortality ? "⚡ 执行天命" : "✅ 已完成"
                    color: sessionStore.canExecuteMortality ? "#FFD700" : theme.textMuted
                    font.pixelSize: 10
                    font.bold: true
                }

                MouseArea {
                    anchors.fill: parent
                    enabled: parent.enabled
                    cursorShape: Qt.PointingHandCursor
                    onClicked: {
                        var result = sessionStore.doExecuteMortality()
                        if (!result.success) {
                            root.showFeedback("error", result.message)
                        }
                    }
                }
            }

            // 推进按钮（紧凑，同一位置切换）
            Rectangle {
                anchors.centerIn: parent
                width: 100
                height: 26
                radius: theme.radius
                color: "#8B2500"
                border.color: "#E8A030"
                border.width: 1
                visible: sessionStore.canAdvanceMortality

                Text {
                    anchors.centerIn: parent
                    text: "⏭️ " + GuiText.mortalityAdvanceBtn
                    color: "#FFD700"
                    font.pixelSize: 10
                    font.bold: true
                }

                MouseArea {
                    anchors.fill: parent
                    cursorShape: Qt.PointingHandCursor
                    onClicked: {
                        var result = sessionStore.doAdvanceMortality()
                        if (!result.success) {
                            root.showFeedback("error", result.message)
                        }
                    }
                }
            }
        }
    }

    // ── 反馈 ──
    function showFeedback(type, message) {
        sessionStore.logUiEvent("[Feedback:" + type + "] " + message)
    }
}
