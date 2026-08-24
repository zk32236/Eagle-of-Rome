import QtQuick 2.15
import QtQuick.Controls 2.15
import QtQuick.Layouts 1.15

import "../i18n"
import "../components"

/*!
 * \brief ResolutionStage — Phase 7: 决算阶段 (Resolution/Settlement)
 *
 * WP-E-G7R（D4 §0 目标结构）——四信息类目 + 独立风险区 + 年度总结：
 *   A. 年度结算预览（将来时 E-03）——四信息类目（非顺序工作流，无 StepBar）：
 *      1. 总督返回  2. 合同到期  3. 和约到期  4. 年度衰减（派系聚合，decay-only）
 *   B. 风险检查（当前状态 / 现在时）——独立区
 *   C. 年度总结（现状 + next_year；国库行 = 现状值 ODR-C2）
 *
 * 数据驱动：sessionStore.resolutionView.preview.*（只读投影，直连 _plan_*）。
 * 无 StepBar / 无「决算完成」第五块 / 无 x/4 进度隐喻（E-02）。
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

    // ── Content ──
    ColumnLayout {
        anchors.fill: parent
        anchors.topMargin: 14
        anchors.bottomMargin: 14
        anchors.leftMargin: 12
        anchors.rightMargin: 12
        spacing: 12

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
        // A 区：四信息类目（将来时 E-03，preview 只读投影；非顺序工作流 E-02）
        // 1. 🏛️ 总督返回  2. 📜 合同到期（身份行） 3. 🤝 和约到期 4. 📉 年度衰减（派系聚合）
        // 门控 = resolutionResolved && !isResolutionResolving（G7R：预结算即可见）
        // ══════════════════════════════════════════════════════════════════
        ColumnLayout {
            id: resultsPanel
            objectName: "resolutionResultsPanel"
            visible: sessionStore.resolutionResolved && !sessionStore.isResolutionResolving
            Layout.fillWidth: true
            spacing: 4

            // ── 分节 1：🏛️ 总督返回（preview.governor_returns，E-03 将来时）──
            ColumnLayout {
                id: governorReturnSection
                objectName: "resolutionGovernorReturnSection"
                Layout.fillWidth: true
                spacing: 4
                Rectangle {
                    Layout.fillWidth: true
                    Layout.preferredHeight: 28
                    color: "#FFFDF5"
                    border.color: "#C9A84C"
                    border.width: 1
                    radius: 6
                    RowLayout {
                        anchors.fill: parent
                        anchors.leftMargin: 8
                        anchors.rightMargin: 8
                        spacing: 6
                        Text {
                            text: "🏛️ 总督返回"
                            color: "#3A3530"
                            font.pixelSize: 12
                            font.bold: true
                        }
                    }
                }
                Repeater {
                    model: (sessionStore.resolutionView.preview.governor_returns || [])
                    delegate: ColumnLayout {
                        readonly property var gt: modelData || {}
                        Layout.fillWidth: true
                        spacing: 1
                        Text {
                            text: (gt.province_name || "") + "总督" + (gt.governor_name || "") + "将返回罗马"
                            color: "#3A3530"
                            font.pixelSize: 12
                            Layout.fillWidth: true
                            wrapMode: Text.WordWrap
                            lineHeight: 1.5
                        }
                        Text {
                            visible: gt.successor_name !== undefined && gt.successor_name !== null && gt.successor_name !== ""
                            text: (gt.province_name || "") + "总督将由" + gt.successor_name + "接任"
                            color: "#6C8FA1"
                            font.pixelSize: 12
                            Layout.fillWidth: true
                            wrapMode: Text.WordWrap
                            lineHeight: 1.5
                        }
                    }
                }
                Text {
                    id: governorReturnEmpty
                    objectName: "resolutionGovernorReturnEmpty"
                    visible: (sessionStore.resolutionView.preview.governor_returns || []).length === 0
                    text: "本年度结束时无总督返回"
                    color: "#766652"
                    font.pixelSize: 12
                    Layout.fillWidth: true
                }
            }

            // ── 分节 2：📜 合同到期（身份行，preview.contract_expiries，E-03 将来时）──
            ColumnLayout {
                id: contractExpirySection
                objectName: "resolutionContractExpirySection"
                Layout.fillWidth: true
                spacing: 4
                Rectangle {
                    Layout.fillWidth: true
                    Layout.preferredHeight: 28
                    color: "#FFFDF5"
                    border.color: "#C9A84C"
                    border.width: 1
                    radius: 6
                    RowLayout {
                        anchors.fill: parent
                        anchors.leftMargin: 8
                        anchors.rightMargin: 8
                        spacing: 6
                        Text {
                            text: "📜 合同到期"
                            color: "#3A3530"
                            font.pixelSize: 12
                            font.bold: true
                        }
                    }
                }
                Repeater {
                    model: (sessionStore.resolutionView.preview.contract_expiries || [])
                    delegate: Text {
                        readonly property var ce: modelData || {}
                        text: (ce.name || ("#" + ce.contract_id)) + " → 将于本年度结束时到期"
                        color: "#3A3530"
                        font.pixelSize: 12
                        Layout.fillWidth: true
                        wrapMode: Text.WordWrap
                        lineHeight: 1.5
                    }
                }
                Text {
                    id: contractExpiryEmpty
                    objectName: "resolutionContractExpiryEmpty"
                    visible: (sessionStore.resolutionView.preview.contract_expiries || []).length === 0
                    text: "本年度结束时无合同到期"
                    color: "#766652"
                    font.pixelSize: 12
                    Layout.fillWidth: true
                }
            }

            // ── 分节 3：🤝 和约到期（preview.truce_expiries，E-03 将来时）──
            ColumnLayout {
                id: truceExpirySection
                objectName: "resolutionTruceExpirySection"
                Layout.fillWidth: true
                spacing: 4
                Rectangle {
                    Layout.fillWidth: true
                    Layout.preferredHeight: 28
                    color: "#FFFDF5"
                    border.color: "#C9A84C"
                    border.width: 1
                    radius: 6
                    RowLayout {
                        anchors.fill: parent
                        anchors.leftMargin: 8
                        anchors.rightMargin: 8
                        spacing: 6
                        Text {
                            text: "🤝 和约到期"
                            color: "#3A3530"
                            font.pixelSize: 12
                            font.bold: true
                        }
                    }
                }
                Repeater {
                    model: (sessionStore.resolutionView.preview.truce_expiries || [])
                    delegate: Text {
                        readonly property var tw: modelData || {}
                        text: (tw.war_name || "") + " → 和约将在本年度结束时到期"
                        color: "#C45151"
                        font.pixelSize: 12
                        Layout.fillWidth: true
                        wrapMode: Text.WordWrap
                        lineHeight: 1.5
                    }
                }
                Text {
                    id: truceExpiryEmpty
                    objectName: "resolutionTruceExpiryEmpty"
                    visible: (sessionStore.resolutionView.preview.truce_expiries || []).length === 0
                    text: "本年度结束时无和约到期"
                    color: "#C45151"
                    font.pixelSize: 12
                    Layout.fillWidth: true
                }
            }

            // ── 分节 4：📉 年度衰减（派系聚合 preview.faction_influence，decay-only ODR-C1）──
            // 禁 per-figure age/veterans/popularity dump（R-21）
            ColumnLayout {
                id: annualDecaySection
                objectName: "resolutionAnnualDecaySection"
                Layout.fillWidth: true
                spacing: 4
                Rectangle {
                    Layout.fillWidth: true
                    Layout.preferredHeight: 28
                    color: "#FFFDF5"
                    border.color: "#C9A84C"
                    border.width: 1
                    radius: 6
                    RowLayout {
                        anchors.fill: parent
                        anchors.leftMargin: 8
                        anchors.rightMargin: 8
                        spacing: 6
                        Text {
                            text: "📉 年度衰减"
                            color: "#3A3530"
                            font.pixelSize: 12
                            font.bold: true
                        }
                    }
                }
                Repeater {
                    model: (sessionStore.resolutionView.preview.faction_influence || [])
                    delegate: Text {
                        readonly property var fi: modelData || {}
                        readonly property int delta: parseInt(fi.influence_delta) || 0
                        readonly property string factionName: fi.faction_name || ""
                        text: {
                            if (delta < 0) {
                                return factionName + " → 将减少 " + (-delta) + " 点影响力，降至 " + fi.influence_after
                            }
                            if (delta === 0) {
                                return factionName + " → 影响力无变化，仍为 " + fi.influence_after
                            }
                            return factionName + " → 将增加 " + delta + " 点影响力，升至 " + fi.influence_after
                        }
                        color: "#3A3530"
                        font.pixelSize: 12
                        Layout.fillWidth: true
                        wrapMode: Text.WordWrap
                        lineHeight: 1.5
                    }
                }
                Text {
                    id: annualDecayEmpty
                    objectName: "resolutionAnnualDecayEmpty"
                    visible: (sessionStore.resolutionView.preview.faction_influence || []).length === 0
                    text: "本年度结束时无派系影响力衰减"
                    color: "#766652"
                    font.pixelSize: 12
                    Layout.fillWidth: true
                }
            }
        }

        // ══════════════════════════════════════════════════════════════════
        // B 区：风险检查（独立区，现在时；F4 权威现状扫描，不并入四类目）
        // ══════════════════════════════════════════════════════════════════
        ColumnLayout {
            id: riskCheckSection
            objectName: "resolutionRiskCheckSection"
            visible: sessionStore.resolutionResolved && !sessionStore.isResolutionResolving
            Layout.fillWidth: true
            spacing: 4
            Rectangle {
                Layout.fillWidth: true
                Layout.preferredHeight: 28
                color: "#FFFDF5"
                border.color: "#C9A84C"
                border.width: 1
                radius: 6
                RowLayout {
                    anchors.fill: parent
                    anchors.leftMargin: 8
                    anchors.rightMargin: 8
                    spacing: 6
                    Text {
                        text: "⚠️ 风险检查"
                        color: "#3A3530"
                        font.pixelSize: 12
                        font.bold: true
                    }
                }
            }
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
            Text {
                id: riskCheckEmpty
                objectName: "resolutionRiskCheckEmpty"
                visible: (sessionStore.resolutionWarnings || []).length === 0
                text: "当前无重大年度风险"
                color: "#766652"
                font.pixelSize: 12
                Layout.fillWidth: true
            }
        }

        // ══════════════════════════════════════════════════════════════════
        // C 区：年度总结 — HTML list-item table style
        // 4 rows: 主导派系, 国库（现状值 ODR-C2）, 临时影响力衰减, 下一年度
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

            // Row 2: Treasury — 现状值（ODR-C2：保留国库现状 + 删「年度净变化」delta 行）
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
                        text: "国库"
                        color: "#3A3530"
                        font.pixelSize: 12
                    }
                    Item { Layout.fillWidth: true }
                    Text {
                        text: (parseInt(sessionStore.resolutionSummary.treasury) || 0) + " C"
                        color: "#3A3530"
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
