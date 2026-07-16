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
                    Text {
                        text: (sessionStore.selectedPhaseSummary && sessionStore.selectedPhaseSummary.subtitle) || ""
                        color: theme.accentPrimary
                        font.pixelSize: theme.bodySize
                        font.bold: true
                        Layout.fillWidth: true
                    }
                    Text {
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

                    // Phase advance button — 当前阶段已结算/已执行后出现
                    Rectangle {
                        id: advanceBtn
                        objectName: "advancePhaseButton"
                        Layout.fillWidth: true
                        Layout.preferredHeight: 32
                        radius: 7
                        enabled: canAdvance

                        property bool canAdvance: sessionStore.canAdvanceMortality
                            || sessionStore.canAdvanceRevenue
                            || sessionStore.canAdvanceForum
                            || sessionStore.canAdvanceSenate
                            || sessionStore.canAdvancePopulation

                        function advanceText() {
                            if (sessionStore.canAdvanceMortality) return "⏭️ 推进到收入阶段"
                            if (sessionStore.canAdvanceRevenue) return "⏭️ 推进到广场"
                            if (sessionStore.canAdvanceForum) return "⏭️ 推进到人口阶段"
                            if (sessionStore.canAdvanceSenate) return "⏭️ 推进到战斗阶段"
                            if (sessionStore.canAdvancePopulation) return "⏭️ 进入元老院阶段"
                            return "⏭️ 推进到下一阶段"
                        }

                        // 激活态: 深红底 + 金色字；禁用态: 半透明底 + 灰色字
                        color: canAdvance ? "#84250A" : "#0EFFFFFF"
                        border.color: canAdvance ? "transparent" : "#33D9AF63"
                        border.width: 1

                        // Drop shadow for active state (D-06 风格)
                        layer.enabled: canAdvance
                        layer.effect: DropShadow {
                            transparentBorder: true
                            horizontalOffset: 0
                            verticalOffset: 3
                            radius: 8
                            samples: 16
                            color: "#B0000000"
                        }

                        // Top highlight edge (D-06)
                        Rectangle {
                            anchors.top: parent.top
                            anchors.left: parent.left
                            anchors.right: parent.right
                            anchors.leftMargin: 4
                            anchors.rightMargin: 4
                            height: 1
                            radius: 2
                            gradient: Gradient {
                                orientation: Gradient.Vertical
                                GradientStop { position: 0.0; color: "#66FFFFFF" }
                                GradientStop { position: 1.0; color: "transparent" }
                            }
                        }

                        Text {
                            anchors.centerIn: parent
                            text: advanceBtn.advanceText()
                            color: canAdvance ? theme.headerText : theme.textMuted
                            font.pixelSize: theme.buttonSize
                            font.bold: true
                        }

                        MouseArea {
                            anchors.fill: parent
                            enabled: canAdvance
                            cursorShape: Qt.PointingHandCursor
                            hoverEnabled: true
                            onEntered: {
                                if (canAdvance) {
                                    advanceBtn.color = "#A33A17"
                                }
                            }
                            onExited: {
                                if (canAdvance) {
                                    advanceBtn.color = "#84250A"
                                }
                            }
                            onClicked: {
                                if (sessionStore.canAdvanceMortality) {
                                    var advResult = sessionStore.doAdvanceMortality()
                                    if (!advResult.success) {
                                        root.showFeedback("error", advResult.message || "推进失败")
                                    }
                                } else if (sessionStore.canAdvanceRevenue) {
                                    var revResult = sessionStore.doAdvanceRevenue()
                                    if (!revResult.success) {
                                        root.showFeedback("error", revResult.message || "推进失败")
                                    }
                                } else if (sessionStore.canAdvanceSenate) {
                                    var senateResult = sessionStore.doAdvanceSenate()
                                    if (!senateResult.success) {
                                        root.showFeedback("error", senateResult.message || "推进失败")
                                    }
                                } else if (sessionStore.canAdvancePopulation) {
                                    var popResult = sessionStore.doAdvancePopulation()
                                    if (!popResult.success) {
                                        root.showFeedback("error", popResult.message || "推进失败")
                                    }
                                } else if (sessionStore.canAdvanceForum) {
                                    var forumResult = sessionStore.doAdvanceForum()
                                    if (!forumResult.success) {
                                        root.showFeedback("error", forumResult.message || "推进失败")
                                    }
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
