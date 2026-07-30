import QtQuick 2.15
import QtQuick.Controls 2.15
import QtQuick.Layouts 1.15

import "../i18n"
import "../components"

/*!
 * \brief ResolutionStage — Phase 7: 决算阶段 (Resolution/Settlement)
 *
 * Visual redesign per EOR_GUI_Prototype_v3.25.1 HTML prototype.
 * 5 visual sections:
 *   1. Five-step progress bar (numbered circles + arrows)
 *   2. Event cards (info-box style)
 *   3. Risk warnings (level-colored warn-box)
 *   4. Annual summary (list-item table with name-value alignment)
 *   5. "进入下一年度" button (btn primary)
 *
 * All data driven by sessionStore resolution DTO properties.
 * No backend/API/Store changes — QML-only visual redo.
 */
Rectangle {
    id: root
    color: "transparent"

    FactionStyle { id: factionStyle }

    // ── Severity color helpers (preserved from original) ──
    function warningColor(level) {
        if (level === "critical") return "#B3261E"
        if (level === "warning") return "#FF8C00"
        if (level === "info") return "#6C8FA1"
        return "#766652"
    }

    function warningBg(level) {
        if (level === "critical") return "#FFEAE5"
        if (level === "warning") return "#FFF8E1"
        if (level === "info") return "#E8F0F5"
        return "#F5F0E8"
    }

    function warningIcon(level) {
        if (level === "critical") return "🔴"
        if (level === "warning") return "🟡"
        if (level === "info") return "🔵"
        return "⚪"
    }

    // ── Step status helpers (block-style) ──
    function stepBlockColor(status) {
        if (status === "completed") return "#2E9D4D"
        return "#D4C8B8"
    }

    function stepBorderColor(status) {
        if (status === "completed") return "#228B22"
        return "#BFA88C"
    }

    function stepTextColor(status) {
        if (status === "completed") return "#FFFFFF"
        return "#766652"
    }

    // ── Content ──
    ColumnLayout {
        anchors.fill: parent
        anchors.topMargin: 14
        anchors.bottomMargin: 14
        anchors.leftMargin: 12
        anchors.rightMargin: 12
        spacing: 12

        // ══════════════════════════════════════════════════════════════════
        // Spacer: from subtitle bottom to StepBar top
        // ══════════════════════════════════════════════════════════════════
        Item {
            id: stepBarSpacer
            Layout.fillWidth: true
            Layout.preferredHeight: 34
        }

        // ══════════════════════════════════════════════════════════════════
        // Section 1: StepBar — Block style (五等分步骤块)
        // Loading(S0): gray #D4C8B8 bg, #BFA88C border, ⏳ icon + pending text
        // Resolved(S1): green #2E9D4D bg, #228B22 border, ✅ icon + completed text
        // Height: 44px, radius: 6px, border: 1px, block spacing: 4px
        // ══════════════════════════════════════════════════════════════════
        RowLayout {
            id: stepBar
            objectName: "resolutionStepBar"
            Layout.fillWidth: true
            Layout.preferredHeight: 44
            spacing: 4

            Repeater {
                model: sessionStore.resolutionStepStatuses || []

                delegate: Rectangle {
                    readonly property var stepData: modelData || {}
                    readonly property string stepStatus: stepData.status || "pending"
                    readonly property string stepName: stepData.display || stepData.name || ("步骤 " + (index + 1))

                    Layout.fillWidth: true
                    Layout.preferredHeight: 44
                    color: stepBlockColor(stepStatus)
                    border.color: stepBorderColor(stepStatus)
                    border.width: 1
                    radius: 6

                    RowLayout {
                        anchors.centerIn: parent
                        spacing: 6

                        Text {
                            text: stepStatus === "completed" ? "✅" : "⏳"
                            font.pixelSize: theme.bodySize
                        }
                        Text {
                            text: stepName
                            color: stepTextColor(stepStatus)
                            font.pixelSize: theme.bodySize
                        }
                    }
                }
            }
        }

        // ══════════════════════════════════════════════════════════════════
        // LoadingBar — 仅 S0 (loading) 态可见
        // 可见性严格绑定: !resolutionResolved && isResolutionResolving
        // 位于 StepBar 与结算面板之间，S0 时独占可见
        // ══════════════════════════════════════════════════════════════════
        Rectangle {
            id: loadingBar
            objectName: "resolutionLoadingBar"
            visible: !sessionStore.resolutionResolved && sessionStore.isResolutionResolving
            Layout.fillWidth: true
            Layout.preferredHeight: 44
            color: "#FFF6E6"
            border.color: "#E0B56C"
            border.width: 1
            radius: 6

            RowLayout {
                anchors.centerIn: parent
                spacing: 8

                Text {
                    text: "⏳"
                    font.pixelSize: theme.bodySize
                }
                Text {
                    text: "等待结算完成…"
                    color: "#766652"
                    font.pixelSize: theme.bodySize
                }
            }
        }

        // ══════════════════════════════════════════════════════════════════
        // Section 2: Event Cards — HTML info-box style
        // Background: #FFFDF5, border: 1px solid #C9A84C, radius: 6
        // 🏛️ 总督轮换 / 📜 合同到期 / 🤝 和约到期（红色）
        // ══════════════════════════════════════════════════════════════════
        Rectangle {
            id: resultsPanel
            objectName: "resolutionResultsPanel"
            visible: sessionStore.resolutionResolved && !sessionStore.isResolutionResolving
            Layout.fillWidth: true
            Layout.preferredHeight: childrenRect.height + 16
            color: "#FFFDF5"
            border.color: "#C9A84C"
            border.width: 1
            radius: 6

            ColumnLayout {
                anchors.fill: parent
                anchors.margins: 8
                spacing: 4

                // Governor transitions
                Repeater {
                    model: (sessionStore.resolutionResults.governor_transitions || [])

                    delegate: Text {
                        readonly property var gt: modelData || {}
                        text: "🏛️ 总督轮换：" + (gt.province || "")
                            + " — " + (gt.old_governor || "无") + " → " + (gt.governor || "未知")
                        color: "#3A3530"
                        font.pixelSize: 12
                        Layout.fillWidth: true
                        wrapMode: Text.WordWrap
                        lineHeight: 1.5
                    }
                }

                // Contracts expired
                Text {
                    visible: (parseInt(sessionStore.resolutionResults.contracts_expired) || 0) > 0
                    text: "📜 合同到期：" + (sessionStore.resolutionResults.contracts_expired || 0) + " 份"
                    color: "#3A3530"
                    font.pixelSize: 12
                    Layout.fillWidth: true
                    wrapMode: Text.WordWrap
                }

                // Truce expired — red color emphasis
                Repeater {
                    model: (sessionStore.resolutionResults.truce_expired || [])

                    delegate: Text {
                        readonly property var warName: modelData || ""
                        text: "🤝 和约到期：" + warName
                        color: "#C45151"
                        font.pixelSize: 12
                        Layout.fillWidth: true
                        wrapMode: Text.WordWrap
                    }
                }
            }
        }

        // ══════════════════════════════════════════════════════════════════
        // Section 3: Risk Warnings — HTML warn-box style
        // Each warning has level-colored background and text
        // critical=#FFEAE5/#B3261E, warning=#FFF8E1/#FF8C00, info=#E8F0F5/#6C8FA1
        // ══════════════════════════════════════════════════════════════════
        ColumnLayout {
            id: warningsPanel
            objectName: "resolutionWarningsPanel"
            visible: sessionStore.resolutionResolved && !sessionStore.isResolutionResolving && (sessionStore.resolutionWarnings || []).length > 0
            Layout.fillWidth: true
            spacing: 4

            Repeater {
                model: sessionStore.resolutionWarnings || []

                delegate: Rectangle {
                    readonly property var w: modelData || {}
                    Layout.fillWidth: true
                    Layout.preferredHeight: 28
                    radius: 4
                    color: warningBg(w.level || "info")

                    RowLayout {
                        anchors.fill: parent
                        anchors.leftMargin: 8
                        anchors.rightMargin: 8
                        spacing: 6

                        Text {
                            text: "⚠️"
                            font.pixelSize: 12
                            color: warningColor(w.level || "info")
                        }
                        Text {
                            text: w.message || ""
                            color: warningColor(w.level || "info")
                            font.pixelSize: 12
                            font.bold: (w.level || "") === "critical"
                            Layout.fillWidth: true
                            wrapMode: Text.WordWrap
                        }
                    }
                }
            }
        }

        // ══════════════════════════════════════════════════════════════════
        // Section 4: Annual Summary — HTML list-item table style
        // Background: #fff, border: 1px solid #D4A574, padding: 5px 10px
        // 4 rows: 主导派系, 国库年度净变化, 临时影响力衰减, 下一年度
        // ══════════════════════════════════════════════════════════════════
        ColumnLayout {
            id: summaryPanel
            objectName: "resolutionSummaryPanel"
            visible: sessionStore.resolutionResolved && !sessionStore.isResolutionResolving
            Layout.fillWidth: true
            spacing: 3

            // Phase subtitle
            Text {
                text: "📈 年度总结"
                color: "#C44A2B"
                font.pixelSize: 12
                font.bold: true
                Layout.fillWidth: true
                Layout.topMargin: 4
            }

            // Row 1: Dominant faction
            Rectangle {
                Layout.fillWidth: true
                Layout.preferredHeight: 28
                color: "#FFFFFF"
                border.color: "#D4A574"
                border.width: 1
                radius: 4

                RowLayout {
                    anchors.fill: parent
                    anchors.leftMargin: 10
                    anchors.rightMargin: 10
                    spacing: 8

                    Text {
                        text: "主导派系"
                        color: "#3A3530"
                        font.pixelSize: 12
                    }
                    Item { Layout.fillWidth: true }
                    Text {
                        text: {
                            var df = sessionStore.resolutionSummary.dominant_faction
                            if (!df) return "无"
                            var pct = Math.round((df.influence_share || 0) * 100)
                            return (df.name || "无") + " (" + pct + "%)"
                        }
                        color: factionStyle.factionColor(sessionStore.resolutionSummary.dominant_faction
                            ? sessionStore.resolutionSummary.dominant_faction.name || "" : "")
                        font.pixelSize: 12
                        font.bold: true
                    }
                }
            }

            // Row 2: Treasury annual change (delta)
            Rectangle {
                Layout.fillWidth: true
                Layout.preferredHeight: 28
                color: "#FFFFFF"
                border.color: "#D4A574"
                border.width: 1
                radius: 4

                RowLayout {
                    anchors.fill: parent
                    anchors.leftMargin: 10
                    anchors.rightMargin: 10
                    spacing: 8

                    Text {
                        text: "国库年度净变化"
                        color: "#3A3530"
                        font.pixelSize: 12
                    }
                    Item { Layout.fillWidth: true }
                    Text {
                        readonly property int prevTreasury: parseInt(sessionStore.resolutionResults.treasury) || 0
                        readonly property int currTreasury: parseInt(sessionStore.resolutionSummary.treasury) || 0
                        readonly property int treasuryDelta: currTreasury - prevTreasury
                        text: (treasuryDelta >= 0 ? "+" : "") + treasuryDelta + " T"
                        color: treasuryDelta >= 0 ? "#228B22" : "#C45151"
                        font.pixelSize: 12
                        font.bold: true
                    }
                }
            }

            // Row 3: Decay status
            Rectangle {
                Layout.fillWidth: true
                Layout.preferredHeight: 28
                color: "#FFFFFF"
                border.color: "#D4A574"
                border.width: 1
                radius: 4

                RowLayout {
                    anchors.fill: parent
                    anchors.leftMargin: 10
                    anchors.rightMargin: 10
                    spacing: 8

                    Text {
                        text: "临时影响力衰减"
                        color: "#3A3530"
                        font.pixelSize: 12
                    }
                    Item { Layout.fillWidth: true }
                    Text {
                        text: sessionStore.resolutionSummary.decay_applied
                            ? (sessionStore.resolutionSummary.decay_details || "已应用")
                            : "无"
                        color: "#FF8C00"
                        font.pixelSize: 12
                    }
                }
            }

            // Row 4: Next year
            Rectangle {
                Layout.fillWidth: true
                Layout.preferredHeight: 28
                color: "#FFFFFF"
                border.color: "#D4A574"
                border.width: 1
                radius: 4

                RowLayout {
                    anchors.fill: parent
                    anchors.leftMargin: 10
                    anchors.rightMargin: 10
                    spacing: 8

                    Text {
                        text: "下一年度"
                        color: "#3A3530"
                        font.pixelSize: 12
                    }
                    Item { Layout.fillWidth: true }
                    Text {
                        text: sessionStore.resolutionSummary.next_year || ""
                        color: "#C44A2B"
                        font.pixelSize: 12
                        font.bold: true
                    }
                }
            }

            // ══════════════════════════════════════════════════════════════
            // S2: 决算结果展示区 — 胜利条件 + 军团恢复 + 关键事件
            // 数据来源：resolutionResults.victory / legion_recovery / key_events
            // 在 summaryPanel 底部，advance 按钮上方（只读展示）
            // ══════════════════════════════════════════════════════════════

            Rectangle {
                visible: sessionStore.resolutionResults.victory !== undefined
                Layout.fillWidth: true
                Layout.preferredHeight: 28
                color: "#FFFFFF"
                border.color: "#D4A574"
                border.width: 1
                radius: 4

                RowLayout {
                    anchors.fill: parent
                    anchors.leftMargin: 10
                    anchors.rightMargin: 10
                    spacing: 8

                    Text {
                        text: "🏆 胜利条件"
                        color: "#3A3530"
                        font.pixelSize: 12
                    }
                    Item { Layout.fillWidth: true }
                    Text {
                        text: {
                            var vc = sessionStore.resolutionResults.victory || {}
                            return vc.game_over ? "🔴 游戏结束" : "🟢 未触发"
                        }
                        color: (sessionStore.resolutionResults.victory || {}).game_over ? "#B3261E" : "#228B22"
                        font.pixelSize: 12
                        font.bold: true
                    }
                }
            }

            Rectangle {
                visible: sessionStore.resolutionResults.legion_recovery !== undefined
                Layout.fillWidth: true
                Layout.preferredHeight: 28
                color: "#FFFFFF"
                border.color: "#D4A574"
                border.width: 1
                radius: 4

                RowLayout {
                    anchors.fill: parent
                    anchors.leftMargin: 10
                    anchors.rightMargin: 10
                    spacing: 8

                    Text {
                        text: "🛡️ 军团恢复"
                        color: "#3A3530"
                        font.pixelSize: 12
                    }
                    Item { Layout.fillWidth: true }
                    Text {
                        text: {
                            var lr = sessionStore.resolutionResults.legion_recovery || {}
                            return lr.details || (lr.recovered > 0 ? "已恢复 " + lr.recovered + " 支" : "无")
                        }
                        color: (sessionStore.resolutionResults.legion_recovery || {}).recovered > 0 ? "#228B22" : "#766652"
                        font.pixelSize: 12
                    }
                }
            }

            Rectangle {
                visible: (sessionStore.resolutionResults.key_events || []).length > 0
                Layout.fillWidth: true
                Layout.preferredHeight: 28
                color: "#FFFFFF"
                border.color: "#D4A574"
                border.width: 1
                radius: 4

                RowLayout {
                    anchors.fill: parent
                    anchors.leftMargin: 10
                    anchors.rightMargin: 10
                    spacing: 8

                    Text {
                        text: "📋 关键事件"
                        color: "#3A3530"
                        font.pixelSize: 12
                    }
                    Item { Layout.fillWidth: true }
                    Text {
                        text: {
                            var evts = sessionStore.resolutionResults.key_events || []
                            return evts.length > 0 ? evts.length + " 项" : "无"
                        }
                        color: (sessionStore.resolutionResults.key_events || []).length > 0 ? "#C44A2B" : "#766652"
                        font.pixelSize: 12
                    }
                }
            }

            // ══════════════════════════════════════════════════════════════
            // Section 5: "进入下一年度" Button — REMOVED
            // Phase advance button is now in ContextPanel.OperationSection
            // (advancePhaseButton) as the single unified control.
            // ══════════════════════════════════════════════════════════════
        }


    }
}
