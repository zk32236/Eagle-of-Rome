import QtQuick 2.15
import QtQuick.Controls 2.15
import QtQuick.Layouts 1.15
import Qt5Compat.GraphicalEffects

import "../components"
import "../i18n"

/*!
 * \brief ContextPanel — v3.25.1 Codex v4.0 right status panel (§5 D)
 *
 * Layout contract: GUI_LAYOUT_CONTRACT_Phase1_v3.25.1.md §5
 *   x=1144, y=82, w=286, h=736
 *   bg: rgba(31,24,18,.92), border: 1px solid rgba(217,175,99,.34), radius: 10px
 *   Section order: CurrentPhase → Operation → Progress → Player → EventLog
 *   Each section has a named objectName for DA slot-identification.
 *
 * Skeleton stage: only anchors, colors, layout, named sections. No business logic.
 */
Rectangle {
    id: root
    objectName: "contextPanel"
    color: "#14110D"          // deep-ink (H0.2: fix purple-tinted → deep-ink #14110D)
    border.color: "#57D9AF63"  // rgba(217,175,99,.34)
    border.width: 1
    radius: theme.radius
    width: 286
    Layout.preferredWidth: 286
    Layout.minimumWidth: 286

    function showFeedback(type, message) {
        feedbackPanel.show(type, message)
    }

    // P6-R8-14: build compact phase chain for combat — placeholders, not hardcoded names
    function combatPhaseChain() {
        var wars = sessionStore.combatActiveWars || []
        var parts = ["公示"]
        for (var i = 0; i < wars.length; i++) {
            var name = wars[i].name || ("战争" + (i + 1))
            parts.push(name)
        }
        parts.push("战斗结果公示")
        return parts.join(" → ")
    }

    ColumnLayout {
        anchors.fill: parent
        anchors.margins: 0
        spacing: 0

        // ---- ctx-top area (sections 1-4) ----
        Item {
            id: ctxTop
            Layout.fillWidth: true
            Layout.preferredHeight: ctxTopCol.implicitHeight + 24

            ColumnLayout {
                id: ctxTopCol
                anchors.fill: parent
                anchors.margins: 14
                spacing: 8

                // ============================================================
                // §5.1 — CurrentPhaseSection
                // ============================================================
                ColumnLayout {
                    id: currentPhaseSection
                    objectName: "currentPhaseSection"
                    Layout.fillWidth: true
                    spacing: 4

                    Text {
                        text: "🎯 当前阶段"
                        color: "#FFE896"
                        font.pixelSize: theme.smallSize
                        font.bold: true
                        font.weight: Font.DemiBold
                        font.letterSpacing: 1
                    }
                    Text {
                        text: sessionStore.selectedPhaseName || ""
                        color: theme.textPrimary
                        font.pixelSize: 14
                        font.bold: true
                        Layout.fillWidth: true
                    }
                    // P6-R8-14: compact phase chain for combat; placeholder format
                    Text {
                        visible: sessionStore.selectedPhaseId === "combat"
                        text: root.combatPhaseChain()
                        color: theme.accentGoldSoft
                        font.pixelSize: theme.bodySize
                        font.bold: true
                        wrapMode: Text.Wrap
                        Layout.fillWidth: true
                        maximumLineCount: 2
                        elide: Text.ElideRight
                    }
                    // Standard subtitle/description for non-combat phases
                    Text {
                        visible: sessionStore.selectedPhaseId !== "combat"
                        text: (sessionStore.selectedPhaseSummary && sessionStore.selectedPhaseSummary.subtitle) || ""
                        color: theme.accentPrimary
                        font.pixelSize: theme.bodySize
                        font.bold: true
                        Layout.fillWidth: true
                    }
                    Text {
                        visible: sessionStore.selectedPhaseId !== "combat"
                        text: (sessionStore.selectedPhaseSummary && sessionStore.selectedPhaseSummary.description) || ""
                        color: theme.textMuted
                        font.pixelSize: theme.smallSize
                        wrapMode: Text.Wrap
                        Layout.fillWidth: true
                    }
                }

                // ============================================================
                // §5.2 — OperationSection
                // ============================================================
                ColumnLayout {
                    id: operationSection
                    objectName: "operationSection"
                    Layout.fillWidth: true
                    spacing: 4

                    Text {
                        text: "⚡ 操作"
                        color: "#FFE896"
                        font.pixelSize: theme.smallSize
                        font.bold: true
                        font.weight: Font.DemiBold
                        font.letterSpacing: 1
                    }

                    // ── Resolution phase: three-layer info structure (T5, P1-08) ──
                    // Layer 1: 红色摘要 — 阶段标题
                    Text {
                        visible: sessionStore.selectedPhaseId === "resolution"
                        text: "📋 决算阶段"
                        color: "#8B2500"
                        font.pixelSize: 14
                        font.bold: true
                    }

                    // Layer 2: 灰色两行说明文字
                    Text {
                        visible: sessionStore.selectedPhaseId === "resolution"
                        text: "年度总结与决算公示，确认后推进到下一年度。"
                        color: "#766652"
                        font.pixelSize: 12
                        wrapMode: Text.Wrap
                        Layout.fillWidth: true
                    }

                    // Spacer 6px
                    Item {
                        visible: sessionStore.selectedPhaseId === "resolution"
                        Layout.preferredHeight: 6
                        Layout.fillWidth: true
                    }

                    // Phase advance button — 当前阶段已结算/已执行后出现
                    Rectangle {
                        id: advanceBtn
                        objectName: "advancePhaseButton"
                        Layout.fillWidth: true
                        Layout.preferredHeight: 32
                        radius: 7
                        enabled: advanceBtn.canAdvance

                        property bool canAdvance: sessionStore.canAdvanceCurrentPhase

                        // P6-R8-15: normal action button appearance (not red highlight)
                        color: advanceBtn.canAdvance ? theme.bgSurface1 : "#0EFFFFFF"
                        border.color: advanceBtn.canAdvance ? "#57D9AF63" : "#33D9AF63"
                        border.width: 1

                        Text {
                            anchors.centerIn: parent
                            text: advanceBtn.canAdvance ? sessionStore.advanceCurrentPhaseText : "⏭️ 推进到下一阶段"
                            color: advanceBtn.canAdvance ? theme.headerText : theme.textMuted
                            font.pixelSize: theme.buttonSize
                            font.bold: true
                        }

                        MouseArea {
                            anchors.fill: parent
                            enabled: advanceBtn.canAdvance
                            cursorShape: Qt.PointingHandCursor
                            hoverEnabled: true
                            onEntered: {
                                if (advanceBtn.canAdvance) {
                                    advanceBtn.color = "#2C2118"
                                }
                            }
                            onExited: {
                                if (advanceBtn.canAdvance) {
                                    advanceBtn.color = theme.bgSurface1
                                }
                            }
                            onClicked: {
                                var result = sessionStore.doAdvanceCurrentPhase()
                                if (!result.success) {
                                    root.showFeedback("error", result.message || "推进失败")
                                }
                            }
                        }
                    }
                }

                // ============================================================
                // §5.3 — ProgressSection
                // ============================================================
                ColumnLayout {
                    id: progressSection
                    objectName: "progressSection"
                    Layout.fillWidth: true
                    spacing: 2

                    Text {
                        text: "📋 进度"
                        color: "#FFE896"
                        font.pixelSize: theme.smallSize
                        font.bold: true
                        font.weight: Font.DemiBold
                        font.letterSpacing: 1
                    }

                    // Step counter
                    Rectangle {
                        id: progressRow
                        Layout.fillWidth: true
                        Layout.preferredHeight: 20
                        color: "transparent"

                        RowLayout {
                            anchors.fill: parent
                            spacing: 4
                            Text {
                                text: "流程"
                                color: theme.textMuted
                                font.pixelSize: theme.smallSize
                            }
                            Item { Layout.fillWidth: true }
                            Text {
                                text: "4 / 4"
                                color: theme.accentPrimary
                                font.pixelSize: theme.bodySize
                                font.bold: true
                            }
                        }
                    }

                    // Status
                    Rectangle {
                        Layout.fillWidth: true
                        Layout.preferredHeight: 20
                        color: "transparent"

                        RowLayout {
                            anchors.fill: parent
                            spacing: 4
                            Text {
                                text: "状态"
                                color: theme.textMuted
                                font.pixelSize: theme.smallSize
                            }
                            Item { Layout.fillWidth: true }
                            Text {
                                text: GuiText.statusActionable
                                color: theme.statusSuccess
                                font.pixelSize: theme.bodySize
                                font.bold: true
                            }
                        }
                    }

                    // Divider
                    Rectangle {
                        Layout.fillWidth: true
                        height: 1
                        color: "#3DF2D590"   // rgba(242,213,144,.24)
                    }
                }

                // ============================================================
                // §5.4 — PlayerSection
                // ============================================================
                ColumnLayout {
                    id: playerSection
                    objectName: "playerSection"
                    Layout.fillWidth: true
                    spacing: 2

                    Text {
                        text: "👤 玩家"
                        color: "#FFE896"
                        font.pixelSize: theme.smallSize
                        font.bold: true
                        font.weight: Font.DemiBold
                        font.letterSpacing: 1
                    }

                    // H0.3: fix player info truncation — add wrapMode and allow height to expand
                    Rectangle {
                        Layout.fillWidth: true
                        Layout.preferredHeight: playerValue.implicitHeight + 12
                        color: "#0EFFFFFF"
                        border.color: "#3DD9AF63"
                        border.width: 1
                        radius: 7

                        RowLayout {
                            anchors.fill: parent
                            anchors.margins: 6
                            spacing: 4
                            Text {
                                text: "派系"
                                color: theme.textMuted
                                font.pixelSize: theme.smallSize
                            }
                            Item { Layout.fillWidth: true }
                            Text {
                                id: playerValue
                                text: GuiText.playerScope(sessionStore.viewerFactionName, sessionStore.viewerFactionId)
                                color: theme.accentGoldSoft
                                font.pixelSize: theme.bodySize
                                font.bold: true
                                wrapMode: Text.Wrap
                                Layout.fillWidth: true
                                Layout.maximumWidth: 220
                            }
                        }
                    }
                }
            }
        }

        // ---- Divider ----
        Rectangle {
            Layout.fillWidth: true
            height: 1
            color: "#3DF2D590"
        }

        // ============================================================
        // §5.5 — EventLogSection
        // ============================================================
        Rectangle {
            id: eventLogSection
            objectName: "eventLogSection"
            Layout.fillWidth: true
            Layout.fillHeight: true
            color: "transparent"

            ColumnLayout {
                anchors.fill: parent
                anchors.margins: 14
                spacing: 6

                // Event log header
                RowLayout {
                    Layout.fillWidth: true
                    spacing: 4

                    Text {
                        text: "📢 事件日志"
                        color: "#FFE896"
                        font.pixelSize: theme.smallSize
                        font.bold: true
                        font.weight: Font.DemiBold
                        font.letterSpacing: 1
                        Layout.fillWidth: true
                    }

                    // Clear button
                    Rectangle {
                        Layout.preferredWidth: 46
                        Layout.preferredHeight: 22
                        color: "#0EFFFFFF"
                        border.color: "#33D9AF63"
                        border.width: 1
                        radius: 5

                        Text {
                            anchors.centerIn: parent
                            text: "清空"
                            color: theme.textMuted
                            font.pixelSize: theme.smallSize
                        }

                        MouseArea {
                            anchors.fill: parent
                            cursorShape: Qt.PointingHandCursor
                            onClicked: feedbackPanel.clear()
                        }
                    }
                }

                // Feedback/event log entries
                FeedbackPanel {
                    id: feedbackPanel
                    objectName: "feedbackPanel"
                    Layout.fillWidth: true
                    Layout.fillHeight: true
                }
            }
        }
    }
}
