import QtQuick 2.15
import QtQuick.Controls 2.15
import QtQuick.Layouts 1.15

import "../components"
import "../i18n"

/**
 * ContextPanel.qml — Right context panel
 * Design V2.0 §1.5/§1.6
 *
 * Top: faction status (resources/people/treasury/influence/seats)
 * Bottom: event log (cream/parchment style)
 * Bottom edge: flow control buttons
 */
Rectangle {
    id: root
    color: theme.bgSurface1
    border.color: theme.borderNormal
    border.width: 1

    function showFeedback(type, message) {
        // Also push to the event log
        appendLog(type, message)
        feedbackPanel.show(type, message)
    }

    // ── 日志管理 ──
    property var eventLog: []
    function appendLog(type, message) {
        var timestamp = new Date().toLocaleTimeString("zh-CN", {hour: "2-digit", minute: "2-digit", second: "2-digit"})
        var entry = { time: timestamp, type: type, message: message }
        var newLog = eventLog.slice()
        newLog.push(entry)
        // Keep last 50 entries
        if (newLog.length > 50) newLog.splice(0, newLog.length - 50)
        eventLog = newLog
    }

    ColumnLayout {
        anchors.fill: parent
        anchors.margins: 0
        spacing: 2  // Phase-4 §11.2：段间微间距

        // ════════════════════════════════════════════════════════════════
        // Top section — Phase-2 §11~§18 目标 IA 完全重建
        // ════════════════════════════════════════════════════════════════

        // ── 当前阶段摘要 ──
        Rectangle {
            Layout.fillWidth: true
            Layout.preferredHeight: currentPhaseColumn.implicitHeight + 14
            color: "transparent"

            ColumnLayout {
                id: currentPhaseColumn
                anchors.left: parent.left; anchors.right: parent.right
                anchors.margins: 8; anchors.verticalCenter: parent.verticalCenter
                spacing: 4

                RowLayout {
                    spacing: 4
                    Text {
                        text: "🎯 当前阶段"
                        color: "#8B2500"
                        font.pixelSize: 10; font.bold: true
                    }
                }

                Text {
                    text: "⚡ 一键执行天命，查看众神降下的事件。"
                    color: theme.textSecondary
                    font.pixelSize: 9
                    wrapMode: Text.Wrap
                    Layout.fillWidth: true
                }
            }
        }

        // ── 操作：推进按钮（Phase-3 §14：紧凑柔和金）──
        Rectangle {
            Layout.fillWidth: true
            Layout.preferredHeight: 26
            color: "transparent"

            Rectangle {
                anchors.horizontalCenter: parent.horizontalCenter
                width: advanceBtnLabel.implicitWidth + 16
                height: 22
                color: theme.bgSurface2
                border.color: theme.borderNormal
                border.width: 1
                radius: 4

                Text {
                    id: advanceBtnLabel
                    anchors.centerIn: parent
                    text: "⚡ 推进到下一阶段"
                    color: "#8B2500"
                    font.pixelSize: 9; font.bold: true
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

        // ── 进度 ──
        ColumnLayout {
            Layout.fillWidth: true
            Layout.leftMargin: 8; Layout.rightMargin: 8
            spacing: 2

            Text {
                text: "📋 进度"
                color: "#8B2500"
                font.pixelSize: 10; font.bold: true
            }

            RowLayout {
                Layout.fillWidth: true
                Text { text: "流程"; color: theme.textSecondary; font.pixelSize: 9 }
                Item { Layout.fillWidth: true }
                Text { text: "2/2"; color: theme.textPrimary; font.pixelSize: 9; font.bold: true }
            }

            Rectangle { Layout.fillWidth: true; height: 1; color: theme.borderNormal }

            RowLayout {
                Layout.fillWidth: true
                Text { text: "状态"; color: theme.textSecondary; font.pixelSize: 9 }
                Item { Layout.fillWidth: true }
                Text {
                    text: sessionStore.canExecuteMortality ? "可操作" : "已完成"
                    color: sessionStore.canExecuteMortality ? theme.statusSuccess : theme.textMuted
                    font.pixelSize: 9; font.bold: true
                }
            }
        }

        // ── 玩家信息 ──
        ColumnLayout {
            Layout.fillWidth: true
            Layout.leftMargin: 8; Layout.rightMargin: 8
            spacing: 2

            Text {
                text: "👤 玩家"
                color: "#8B2500"
                font.pixelSize: 10; font.bold: true
            }

            RowLayout {
                Layout.fillWidth: true
                Text { text: "派系"; color: theme.textSecondary; font.pixelSize: 9 }
                Item { Layout.fillWidth: true }
                Text {
                    text: sessionStore.viewerFactionName || "Optimates"
                    color: theme.textPrimary; font.pixelSize: 9; font.bold: true
                }
            }

            Rectangle { Layout.fillWidth: true; height: 1; color: theme.borderNormal }

            RowLayout {
                Layout.fillWidth: true
                Text { text: "人物"; color: theme.textSecondary; font.pixelSize: 9 }
                Item { Layout.fillWidth: true }
                Text {
                    text: (sessionStore.factionMemberCount || 5) + "人"
                    color: theme.textPrimary; font.pixelSize: 9; font.bold: true
                }
            }

            // Thin spacer before divider
            Item { Layout.preferredHeight: 6 }
        }

        // =====================================================================
        // Dark red divider
        // =====================================================================
        Rectangle {
            Layout.fillWidth: true
            Layout.preferredHeight: 2
            color: "#8B2500"
        }

        // =====================================================================
        // Bottom: event log (cream/parchment style)
        // =====================================================================
        Rectangle {
            Layout.fillWidth: true
            Layout.fillHeight: true
            color: theme.bgSurface1
            clip: true

            ColumnLayout {
                anchors.fill: parent
                spacing: 0

                // Log title
                Rectangle {
                    Layout.fillWidth: true
                    Layout.preferredHeight: 20
                    color: theme.bgSurface2

                    RowLayout {
                        anchors.fill: parent; anchors.margins: 6; spacing: 4
                        Text {
                            text: "📋 事件日志"
                            color: "#8B2500"
                            font.pixelSize: 9; font.bold: true
                        }
                        Item { Layout.fillWidth: true }
                        Text {
                            text: eventLog.length + " 条"
                            color: theme.textMuted
                            font.pixelSize: 8
                        }
                    }
                }

                // Divider
                Rectangle {
                    Layout.fillWidth: true
                    height: 1
                    color: theme.borderNormal
                }

                // Log content area
                // Phase-3 §17.3: 当日志为空时减少留白
                ScrollView {
                    Layout.fillWidth: true
                    Layout.fillHeight: true
                    clip: true

                    ListView {
                        id: logListView
                        model: root.eventLog
                        spacing: 1
                        anchors.fill: parent
                        anchors.margins: 4

                        delegate: Rectangle {
                            width: parent ? parent.width : 200
                            height: 16
                            color: "transparent"

                            RowLayout {
                                anchors.fill: parent
                                spacing: 4
                                Text {
                                    text: "[" + modelData.time + "]"
                                    color: theme.textMuted
                                    font.pixelSize: 8
                                    Layout.preferredWidth: 60
                                }
                                Text {
                                    text: {
                                        var t = modelData.type
                                        if (t === "success") return "✅"
                                        if (t === "error") return "❌"
                                        if (t === "warning") return "⚠️"
                                        if (t === "info") return "ℹ️"
                                        return "•"
                                    }
                                    color: {
                                        var t = modelData.type
                                        if (t === "success") return theme.statusSuccess
                                        if (t === "error") return "#FF4444"
                                        if (t === "warning") return "#E8A030"
                                        return theme.textMuted
                                    }
                                    font.pixelSize: 9
                                }
                                Text {
                                    text: modelData.message
                                    color: theme.textSecondary
                                    font.pixelSize: 9
                                    Layout.fillWidth: true
                                    elide: Text.ElideRight
                                }
                            }
                        }

                        // Empty state (Phase-3 §17.3: tight when empty)
                        Rectangle {
                            anchors.centerIn: parent
                            visible: root.eventLog.length === 0
                            color: "transparent"
                            Text {
                                text: "尚无事件日志"
                                color: theme.textMuted
                                font.pixelSize: 9
                            }
                        }
                    }
                }

                // Bottom hint removed — aligns with Design (Phase-2 §17)
            }
        }

        // =====================================================================
        // Feedback panel
        // =====================================================================
        FeedbackPanel {
            id: feedbackPanel
            objectName: "feedbackPanel"
            Layout.fillWidth: true
            Layout.preferredHeight: 28
        }

        // =====================================================================
        // Flow control — removed; aligned with Design (Phase-2 §18)
        // Phase advancement is now handled via the sidebar "推进到下一阶段" button
        // =====================================================================
        Rectangle {
            Layout.fillWidth: true
            Layout.preferredHeight: 4
            color: "transparent"
        }
    }

    // ── Init: add system events to log ──
    Component.onCompleted: {
        appendLog("info", "GUI session initialized")
        appendLog("info", "Current phase: " + (sessionStore.currentPhaseName || ""))
    }
}
