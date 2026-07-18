import QtQuick 2.15
import QtQuick.Controls 2.15
import QtQuick.Layouts 1.15
import Qt5Compat.GraphicalEffects

import "../stages"
import "../components"
import "../i18n"

/*!
 * \brief GameShell - v3.25.1 Codex v4.0 main shell skeleton.
 *
 * Layout contract: GUI_LAYOUT_CONTRACT_Phase1_v3.25.1.md
 *
 *   A - TopStatusBar:  x=10, y=10, w=1420, h=62
 *   B - PhaseRail:     x=10, y=82, w=92, h=736   (inside main-wrapper: padding=10)
 *   C - StageDesktop:  x=112, y=82, w=1022, h=736 (center, gap=10 each side)
 *   D - ContextPanel:  x=1144, y=82, w=286, h=736
 *   E - BottomQueryBar: x=10, y=828, w=1420, h=62
 *   F - MainAction:    inside StageDesktop.StageActionSlot
 *
 * Viewport: 1440x900. main-wrapper replaces anchors with direct positioning
 * to match exact contract coordinates.
 */
Rectangle {
    id: root
    objectName: "gameShellRoot"
    color: theme.bgApp

    // 暴露给外部的反馈方法
    function showFeedback(type, message) {
        contextPanel.showFeedback(type, message)
    }
    function showHandoff(nextPlayerId) {
        handoffOverlay.show(nextPlayerId)
    }

    // ============================================================
    // A - TopStatusBar
    // x=10, y=10, w=1420, h=62
    // ============================================================
    TopStatusBar {
        id: topBar
        objectName: "topStatusBar"
        anchors.top: parent.top
        anchors.topMargin: 14
        anchors.left: parent.left
        anchors.leftMargin: 14
        anchors.right: parent.right
        anchors.rightMargin: 14
        height: 62
    }

    // ============================================================
    // main-wrapper inner padding = 14px all sides
    // Content area: y = 10(header margin) + 62(header h) + 10(padding) = 82
    // Content area left: 10(padding)
    // ============================================================

    // ============================================================
    // B - PhaseRail
    // x=10, y=82, w=92, h=736
    // ============================================================
    PhaseRail {
        id: phaseRail
        objectName: "phaseRail"
        anchors.top: topBar.bottom
        anchors.topMargin: 14     // main-wrapper padding top
        anchors.left: parent.left
        anchors.leftMargin: 14    // main-wrapper padding left
        anchors.bottom: bottomQueryBar.top
        anchors.bottomMargin: 14  // main-wrapper padding bottom
        width: 92
    }

    // ============================================================
    // D - ContextPanel
    // x=1144, y=82, w=286, h=736
    // ============================================================
    ContextPanel {
        id: contextPanel
        objectName: "contextPanel"
        anchors.top: topBar.bottom
        anchors.topMargin: 14
        anchors.right: parent.right
        anchors.rightMargin: 14
        anchors.bottom: bottomQueryBar.top
        anchors.bottomMargin: 14
        width: 286
    }

    // ============================================================
    // E - BottomQueryBar
    // x=10, y=828, w=1420, h=62
    // ============================================================
    BottomQueryBar {
        id: bottomQueryBar
        objectName: "bottomQueryBar"
        anchors.left: parent.left
        anchors.leftMargin: 14
        anchors.right: parent.right
        anchors.rightMargin: 14
        anchors.bottom: parent.bottom
        anchors.bottomMargin: 14
        height: 62
        onQueryRequested: function(queryId) {
            var result = sessionStore.doGlobalQuery(queryId)
            if (result.success) {
                queryResultOverlay.open()
            } else {
                showFeedback("error", result.message)
            }
        }

    }

    // ============================================================
    // C - StageDesktop: H0 slots populated per phase
    // x=112, y=82, w=1022, h=736
    // Gap B->C = 10, gap C->D = 10
    //
    // StageHeaderSlot: mortality badge+title+desc / other phases generic
    // StageInstructionSlot: mortality step bar / other phases visible but empty
    // StageContentSlot: phase-specific component (MortalityStage slimmed)
    // StageActionSlot: mortality execute button / other phases visible but empty
    // ============================================================
    StageDesktop {
        id: centerPanel
        objectName: "centerPanel"
        anchors.top: topBar.bottom
        anchors.topMargin: 14
        anchors.left: phaseRail.right
        anchors.leftMargin: 14   // gap B->C
        anchors.right: contextPanel.left
        anchors.rightMargin: 14  // gap C->D
        anchors.bottom: bottomQueryBar.top
        anchors.bottomMargin: 14
        compactActionSlot: sessionStore.selectedPhaseId === "population" || sessionStore.selectedPhaseId === "forum"

        // ---- StageHeaderSlot: phase badge, title, and description ----
        Rectangle {
            objectName: "stageAnnouncement"
            parent: centerPanel.stageHeader
            anchors.fill: parent
            color: "transparent"

            // Mortality phase: badge + title + description
            ColumnLayout {
                visible: sessionStore.selectedPhaseId === "mortality"
                anchors.fill: parent
                spacing: 6

                // Phase badge pill style
                Rectangle {
                    Layout.preferredWidth: badgeText.implicitWidth + 24
                    Layout.preferredHeight: 22
                    radius: 999
                    border.color: "#52D9AF63"
                    border.width: 1

                    gradient: Gradient {
                        orientation: Gradient.Vertical
                        GradientStop { position: 0.0; color: "#8B2500" }
                        GradientStop { position: 1.0; color: "#671B07" }
                    }

                    Text {
                        id: badgeText
                        anchors.centerIn: parent
                        text: "1 / 7"
                        color: theme.headerText
                        font.pixelSize: theme.statLabelSize
                        font.bold: true
                    }
                }

                // Phase title
                Text {
                    text: "🃏 " + GuiText.mortalityTitle
                    color: "#681B07"
                    font.pixelSize: 20
                    font.bold: true
                    font.letterSpacing: 0.3
                }

                // Phase description
                Text {
                    text: sessionStore.selectedPhaseSummary.description || GuiText.mortalityIntro
                    color: "#766652"
                    font.pixelSize: 13
                    font.italic: true
                    wrapMode: Text.Wrap
                    Layout.fillWidth: true
                    Layout.maximumWidth: 980
                }
            }

            // Revenue phase: badge "2/7" + title + description
            ColumnLayout {
                visible: sessionStore.selectedPhaseId === "revenue"
                anchors.fill: parent
                spacing: 6

                // Phase badge (999px pill style)
                Rectangle {
                    Layout.preferredWidth: revenueBadgeText.implicitWidth + 24
                    Layout.preferredHeight: 22
                    radius: 999
                    border.color: "#52D9AF63"
                    border.width: 1

                    gradient: Gradient {
                        orientation: Gradient.Vertical
                        GradientStop { position: 0.0; color: "#8B2500" }
                        GradientStop { position: 1.0; color: "#671B07" }
                    }

                    Text {
                        id: revenueBadgeText
                        anchors.centerIn: parent
                        text: "2 / 7"
                        color: theme.headerText
                        font.pixelSize: theme.statLabelSize
                        font.bold: true
                    }
                }

                // Phase title
                Text {
                    text: "💰 收入结算"
                    color: "#681B07"
                    font.pixelSize: 20
                    font.bold: true
                    font.letterSpacing: 0.3
                }

                // Phase description
                Text {
                    text: "结算国家收入与支出，整理派系财政，确认国库变动。"
                    color: "#766652"
                    font.pixelSize: 13
                    font.italic: true
                    wrapMode: Text.Wrap
                    Layout.fillWidth: true
                    Layout.maximumWidth: 980
                }
            }

            // Population phase: v3.25.1 title + description
            ColumnLayout {
                visible: sessionStore.selectedPhaseId === "population"
                anchors.fill: parent
                spacing: 6

                Rectangle {
                    Layout.preferredWidth: populationBadgeText.implicitWidth + 24
                    Layout.preferredHeight: 22
                    radius: 999
                    border.color: "#52D9AF63"
                    border.width: 1

                    gradient: Gradient {
                        orientation: Gradient.Vertical
                        GradientStop { position: 0.0; color: "#8B2500" }
                        GradientStop { position: 1.0; color: "#671B07" }
                    }

                    Text {
                        id: populationBadgeText
                        anchors.centerIn: parent
                        text: "4 / 7"
                        color: theme.headerText
                        font.pixelSize: theme.statLabelSize
                        font.bold: true
                    }
                }

                Text {
                    text: "⚖️ 人口阶段 — 选举"
                    color: "#681B07"
                    font.pixelSize: 20
                    font.bold: true
                    font.letterSpacing: 0.3
                }

                Text {
                    text: "庆典赞助 → 投票选举 → 结果公示"
                    color: "#766652"
                    font.pixelSize: 13
                    font.italic: true
                    wrapMode: Text.Wrap
                    Layout.fillWidth: true
                    Layout.maximumWidth: 980
                }
            }

            // Senate phase: badge "5/7" + title + description
            ColumnLayout {
                visible: sessionStore.selectedPhaseId === "senate"
                anchors.fill: parent
                spacing: 6

                Rectangle {
                    Layout.preferredWidth: senateBadgeText.implicitWidth + 24
                    Layout.preferredHeight: 22
                    radius: 999
                    border.color: "#52D9AF63"
                    border.width: 1

                    gradient: Gradient {
                        orientation: Gradient.Vertical
                        GradientStop { position: 0.0; color: "#8B2500" }
                        GradientStop { position: 1.0; color: "#671B07" }
                    }

                    Text {
                        id: senateBadgeText
                        anchors.centerIn: parent
                        text: "5 / 7"
                        color: theme.headerText
                        font.pixelSize: theme.statLabelSize
                        font.bold: true
                    }
                }

                Text {
                    text: "🏺 元老院阶段"
                    color: "#681B07"
                    font.pixelSize: 20
                    font.bold: true
                    font.letterSpacing: 0.3
                }

                Text {
                    text: "执政官提案 → 元老院表决 → 保民官否决 → 法案公示与政府运作"
                    color: "#766652"
                    font.pixelSize: 13
                    font.italic: true
                    wrapMode: Text.Wrap
                    Layout.fillWidth: true
                    Layout.maximumWidth: 980
                }
            }

            // Combat phase: badge "6/7" + title + description
            ColumnLayout {
                visible: sessionStore.selectedPhaseId === "combat"
                anchors.fill: parent
                spacing: 6

                Rectangle {
                    Layout.preferredWidth: combatBadgeText.implicitWidth + 24
                    Layout.preferredHeight: 22
                    radius: 999
                    border.color: "#52D9AF63"
                    border.width: 1

                    gradient: Gradient {
                        orientation: Gradient.Vertical
                        GradientStop { position: 0.0; color: "#8B2500" }
                        GradientStop { position: 1.0; color: "#671B07" }
                    }

                    Text {
                        id: combatBadgeText
                        anchors.centerIn: parent
                        text: "6 / 7"
                        color: theme.headerText
                        font.pixelSize: theme.statLabelSize
                        font.bold: true
                    }
                }

                Text {
                    text: "⚔️ 战斗阶段"
                    color: "#681B07"
                    font.pixelSize: 20
                    font.bold: true
                    font.letterSpacing: 0.3
                }

                Text {
                    text: "多场战争独立裁定。每场战争每回合仅一次进攻机会。"
                    color: "#766652"
                    font.pixelSize: 13
                    font.italic: true
                    wrapMode: Text.Wrap
                    Layout.fillWidth: true
                    Layout.maximumWidth: 980
                }
            }

            // Other phases: generic header (original stageAnnouncement style)
            ColumnLayout {
                visible: sessionStore.selectedPhaseId !== "mortality"
                    && sessionStore.selectedPhaseId !== "revenue"
                    && sessionStore.selectedPhaseId !== "forum"
                    && sessionStore.selectedPhaseId !== "population"
                    && sessionStore.selectedPhaseId !== "senate"
                    && sessionStore.selectedPhaseId !== "combat"
                anchors.fill: parent
                spacing: 6

                RowLayout {
                    Layout.fillWidth: true
                    Text {
                        text: GuiText.stageAnnouncementTitle
                        color: theme.textMuted
                        font.pixelSize: theme.bodySize
                        font.bold: true
                    }
                    Item { Layout.fillWidth: true }
                    Text {
                        text: GuiText.stageModeText(sessionStore.selectedPhaseSummary)
                        color: sessionStore.selectedPhaseSummary.actionable ? theme.statusSuccess : theme.statusWarning
                        font.pixelSize: theme.bodySize
                        font.bold: true
                    }
                }
                Text {
                    text: sessionStore.selectedPhaseName || sessionStore.currentPhaseName || GuiText.populationFallbackName
                    color: theme.textDark
                    font.pixelSize: theme.titleSize
                    font.family: theme.fontTitle
                    font.bold: true
                    Layout.fillWidth: true
                }
                Text {
                    text: sessionStore.selectedPhaseSummary.description || GuiText.placeholderFallbackDescription
                    color: theme.textSoft
                    font.pixelSize: theme.bodySize
                    wrapMode: Text.Wrap
                    Layout.fillWidth: true
                }
            }

            // Forum phase: badge "3/7" + title + description
            ColumnLayout {
                visible: sessionStore.selectedPhaseId === "forum"
                anchors.fill: parent
                spacing: 6

                Rectangle {
                    Layout.preferredWidth: forumBadgeText.implicitWidth + 24
                    Layout.preferredHeight: 22
                    radius: 999
                    border.color: "#52D9AF63"
                    border.width: 1

                    gradient: Gradient {
                        orientation: Gradient.Vertical
                        GradientStop { position: 0.0; color: "#8B2500" }
                        GradientStop { position: 1.0; color: "#671B07" }
                    }

                    Text {
                        id: forumBadgeText
                        anchors.centerIn: parent
                        text: "3 / 7"
                        color: theme.headerText
                        font.pixelSize: theme.statLabelSize
                        font.bold: true
                    }
                }

                Text {
                    text: "🏛️ 广场阶段"
                    color: "#681B07"
                    font.pixelSize: 20
                    font.bold: true
                    font.letterSpacing: 0.3
                }

                Text {
                    text: "解雇 → 人才市场（招募/竞标/公地凯旋）→ 公示"
                    color: "#766652"
                    font.pixelSize: 13
                    font.italic: true
                    wrapMode: Text.Wrap
                    Layout.fillWidth: true
                    Layout.maximumWidth: 980
                }
            }
        }

        // ---- StageInstructionSlot: phase step bar ----
        Rectangle {
            parent: centerPanel.stageInstruction
            anchors.fill: parent
            color: "transparent"
            visible: true

            // Mortality step bar (only visible in mortality phase)
            Rectangle {
                visible: sessionStore.selectedPhaseId === "mortality"
                anchors.fill: parent
                color: "#D1FFF9EC"
                border.color: "#85A8753B"
                border.width: 1
                radius: 10

                Row {
                    anchors.verticalCenter: parent.verticalCenter
                    anchors.left: parent.left
                    anchors.leftMargin: 12
                    spacing: 7

                    // Step 1: current
                    Row {
                        spacing: 4
                        anchors.verticalCenter: parent.verticalCenter
                        Rectangle {
                            width: 20; height: 20; radius: 10
                            color: "#E8B84B"
                            Text {
                                anchors.centerIn: parent
                                text: "1"
                                color: "#2C1E12"
                                font.pixelSize: theme.smallSize; font.bold: true
                            }
                        }
                        Text {
                            text: "⚡ 执行天命"
                            color: "#2C1E12"
                            font.pixelSize: theme.bodySize
                            anchors.verticalCenter: parent.verticalCenter
                        }
                    }

                    // Arrow
                    Text {
                        text: "→"
                        color: "#B8A080"
                        font.pixelSize: theme.bodySize
                        anchors.verticalCenter: parent.verticalCenter
                    }

                    // Step 2: todo
                    Row {
                        spacing: 4
                        anchors.verticalCenter: parent.verticalCenter
                        Rectangle {
                            width: 20; height: 20; radius: 10
                            color: "#E8D5C4"
                            Text {
                                anchors.centerIn: parent
                                text: "2"
                                color: "#999999"
                                font.pixelSize: theme.smallSize; font.bold: true
                            }
                        }
                        Text {
                            text: "📜 查看事件结果"
                            color: "#999999"
                            font.pixelSize: theme.bodySize
                            anchors.verticalCenter: parent.verticalCenter
                        }
                    }
                }
            }

            // Revenue step bar (only visible in revenue phase)
            Rectangle {
                visible: sessionStore.selectedPhaseId === "revenue"
                anchors.fill: parent
                color: "#D1FFF9EC"
                border.color: "#85A8753B"
                border.width: 1
                radius: 10

                Row {
                    anchors.verticalCenter: parent.verticalCenter
                    anchors.left: parent.left
                    anchors.leftMargin: 12
                    spacing: 7

                    // Step 1: current
                    Row {
                        spacing: 4
                        anchors.verticalCenter: parent.verticalCenter
                        Rectangle {
                            width: 20; height: 20; radius: 10
                            color: "#E8B84B"
                            Text {
                                anchors.centerIn: parent
                                text: "1"
                                color: "#2C1E12"
                                font.pixelSize: theme.smallSize; font.bold: true
                            }
                        }
                        Text {
                            text: "💰 查看/确认收入结算"
                            color: "#2C1E12"
                            font.pixelSize: theme.bodySize
                            anchors.verticalCenter: parent.verticalCenter
                        }
                    }
                }
            }

            // Forum step bar
            Rectangle {
                visible: sessionStore.selectedPhaseId === "forum"
                anchors.fill: parent
                color: "#D1FFF9EC"
                border.color: "#85A8753B"
                border.width: 1
                radius: 10

                Row {
                    anchors.verticalCenter: parent.verticalCenter
                    anchors.left: parent.left
                    anchors.leftMargin: 12
                    spacing: 7

                    Row {
                        spacing: 4
                        anchors.verticalCenter: parent.verticalCenter
                        Rectangle { width: 20; height: 20; radius: 10; color: "#2EA44F"; Text { anchors.centerIn: parent; text: "✓"; color: "#FFFFFF"; font.pixelSize: theme.smallSize; font.bold: true } }
                        Text { text: "公示区"; color: "#2C1E12"; font.pixelSize: theme.bodySize; anchors.verticalCenter: parent.verticalCenter }
                    }
                    Text { text: "→"; color: "#B8A080"; font.pixelSize: theme.bodySize; anchors.verticalCenter: parent.verticalCenter }
                    Row {
                        spacing: 4
                        anchors.verticalCenter: parent.verticalCenter
                        Rectangle {
                            width: 20; height: 20; radius: 10
                            color: sessionStore.forumCurrentStep === "retirement" ? "#E8B84B" : "#E8D5C4"
                            Text { anchors.centerIn: parent; text: "1"; color: "#2C1E12"; font.pixelSize: theme.smallSize; font.bold: true }
                        }
                        Text {
                            text: "解雇成员"
                            color: sessionStore.forumCurrentStep === "retirement" ? "#2C1E12" : "#766652"
                            font.pixelSize: theme.bodySize
                            anchors.verticalCenter: parent.verticalCenter
                        }
                    }
                    Text { text: "→"; color: "#B8A080"; font.pixelSize: theme.bodySize; anchors.verticalCenter: parent.verticalCenter }
                    Row {
                        spacing: 4
                        anchors.verticalCenter: parent.verticalCenter
                        Rectangle {
                            width: 20; height: 20; radius: 10
                            color: sessionStore.forumCurrentStep !== "retirement" ? "#E8B84B" : "#E8D5C4"
                            Text { anchors.centerIn: parent; text: "2"; color: "#2C1E12"; font.pixelSize: theme.smallSize; font.bold: true }
                        }
                        Text {
                            text: "市场（招募·竞标·认购·凯旋）"
                            color: sessionStore.forumCurrentStep !== "retirement" ? "#2C1E12" : "#999999"
                            font.pixelSize: theme.bodySize
                            anchors.verticalCenter: parent.verticalCenter
                        }
                    }
                }
            }

            // Population step bar
            Rectangle {
                visible: sessionStore.selectedPhaseId === "population"
                anchors.fill: parent
                color: "#D1FFF9EC"
                border.color: "#85A8753B"
                border.width: 1
                radius: 10

                Row {
                    anchors.verticalCenter: parent.verticalCenter
                    anchors.left: parent.left
                    anchors.leftMargin: 12
                    spacing: 7

                    Row {
                        spacing: 4
                        anchors.verticalCenter: parent.verticalCenter
                        Rectangle { width: 20; height: 20; radius: 10; color: "#2EA44F"; Text { anchors.centerIn: parent; text: "✓"; color: "#FFFFFF"; font.pixelSize: theme.smallSize; font.bold: true } }
                        Text { text: "📢 公示区"; color: "#2C1E12"; font.pixelSize: theme.bodySize; anchors.verticalCenter: parent.verticalCenter }
                    }
                    Text { text: "→"; color: "#B8A080"; font.pixelSize: theme.bodySize; anchors.verticalCenter: parent.verticalCenter }
                    Row {
                        spacing: 4
                        anchors.verticalCenter: parent.verticalCenter
                        Rectangle {
                            width: 20; height: 20; radius: 10
                            color: root.populationCampaignDone ? "#2EA44F" : "#E8B84B"
                            Text {
                                anchors.centerIn: parent
                                text: root.populationCampaignDone ? "✓" : "1"
                                color: root.populationCampaignDone ? "#FFFFFF" : "#2C1E12"
                                font.pixelSize: theme.smallSize
                                font.bold: true
                            }
                        }
                        Text {
                            text: "🎉 庆典赞助"
                            color: "#2C1E12"
                            font.pixelSize: theme.bodySize
                            anchors.verticalCenter: parent.verticalCenter
                        }
                    }
                    Text { text: "→"; color: "#B8A080"; font.pixelSize: theme.bodySize; anchors.verticalCenter: parent.verticalCenter }
                    Row {
                        spacing: 4
                        anchors.verticalCenter: parent.verticalCenter
                        Rectangle {
                            width: 20; height: 20; radius: 10
                            color: root.populationCampaignDone ? "#E8B84B" : "#E8D5C4"
                            Text { anchors.centerIn: parent; text: "2"; color: "#2C1E12"; font.pixelSize: theme.smallSize; font.bold: true }
                        }
                        Text {
                            text: "🗳️ 投票选举"
                            color: root.populationCampaignDone ? "#2C1E12" : "#999999"
                            font.pixelSize: theme.bodySize
                            anchors.verticalCenter: parent.verticalCenter
                        }
                    }
                }
            }

            // Senate step bar
            Rectangle {
                visible: sessionStore.selectedPhaseId === "senate"
                anchors.fill: parent
                color: "#D1FFF9EC"
                border.color: "#85A8753B"
                border.width: 1
                radius: 10

                Row {
                    anchors.verticalCenter: parent.verticalCenter
                    anchors.left: parent.left
                    anchors.leftMargin: 12
                    spacing: 7

                    Row {
                        spacing: 4
                        anchors.verticalCenter: parent.verticalCenter
                        Rectangle { width: 20; height: 20; radius: 10; color: "#2EA44F"; Text { anchors.centerIn: parent; text: "✓"; color: "#FFFFFF"; font.pixelSize: theme.smallSize; font.bold: true } }
                        Text { text: "公示"; color: "#2C1E12"; font.pixelSize: theme.bodySize; anchors.verticalCenter: parent.verticalCenter }
                    }
                    Text { text: "→"; color: "#B8A080"; font.pixelSize: theme.bodySize; anchors.verticalCenter: parent.verticalCenter }
                    Row {
                        spacing: 4
                        anchors.verticalCenter: parent.verticalCenter
                        Rectangle {
                            width: 20; height: 20; radius: 10
                            color: sessionStore.senateCurrentStep === "proposal" ? "#E8B84B" : "#2EA44F"
                            Text { anchors.centerIn: parent; text: sessionStore.senateCurrentStep === "proposal" ? "1" : "✓"; color: sessionStore.senateCurrentStep === "proposal" ? "#2C1E12" : "#FFFFFF"; font.pixelSize: theme.smallSize; font.bold: true }
                        }
                        Text { text: "执政官提案"; color: "#2C1E12"; font.pixelSize: theme.bodySize; anchors.verticalCenter: parent.verticalCenter; font.bold: sessionStore.senateCurrentStep === "proposal" }
                    }
                    Text { text: "→"; color: "#B8A080"; font.pixelSize: theme.bodySize; anchors.verticalCenter: parent.verticalCenter }
                    Row {
                        spacing: 4
                        anchors.verticalCenter: parent.verticalCenter
                        Rectangle {
                            width: 20; height: 20; radius: 10
                            color: sessionStore.senateCurrentStep === "senate_vote" ? "#E8B84B" : "#E8D5C4"
                            Text { anchors.centerIn: parent; text: "2"; color: "#2C1E12"; font.pixelSize: theme.smallSize; font.bold: true }
                        }
                        Text { text: "元老表决"; color: sessionStore.senateCurrentStep === "senate_vote" ? "#2C1E12" : "#766652"; font.pixelSize: theme.bodySize; anchors.verticalCenter: parent.verticalCenter; font.bold: sessionStore.senateCurrentStep === "senate_vote" }
                    }
                    Text { text: "→"; color: "#B8A080"; font.pixelSize: theme.bodySize; anchors.verticalCenter: parent.verticalCenter }
                    Row {
                        spacing: 4
                        anchors.verticalCenter: parent.verticalCenter
                        Rectangle { width: 20; height: 20; radius: 10; color: "#E8D5C4"; Text { anchors.centerIn: parent; text: "3"; color: "#2C1E12"; font.pixelSize: theme.smallSize; font.bold: true } }
                        Text { text: "保民官否决"; color: "#766652"; font.pixelSize: theme.bodySize; anchors.verticalCenter: parent.verticalCenter }
                    }
                }
            }

            // Combat step bar
            Rectangle {
                visible: sessionStore.selectedPhaseId === "combat"
                anchors.fill: parent
                color: "#D1FFF9EC"
                border.color: "#85A8753B"
                border.width: 1
                radius: 10

                Row {
                    anchors.verticalCenter: parent.verticalCenter
                    anchors.left: parent.left
                    anchors.leftMargin: 12
                    spacing: 7

                    Row {
                        spacing: 4
                        anchors.verticalCenter: parent.verticalCenter
                        Rectangle { width: 20; height: 20; radius: 10; color: "#2EA44F"; Text { anchors.centerIn: parent; text: "✓"; color: "#FFFFFF"; font.pixelSize: theme.smallSize; font.bold: true } }
                        Text { text: "公示"; color: "#2C1E12"; font.pixelSize: theme.bodySize; anchors.verticalCenter: parent.verticalCenter }
                    }
                    Text { text: "→"; color: "#B8A080"; font.pixelSize: theme.bodySize; anchors.verticalCenter: parent.verticalCenter }
                    Row {
                        spacing: 4
                        anchors.verticalCenter: parent.verticalCenter
                        Rectangle {
                            width: 20; height: 20; radius: 10
                            color: sessionStore.combatCurrentStep === "select" ? "#E8B84B" : "#2EA44F"
                            Text { anchors.centerIn: parent; text: sessionStore.combatCurrentStep === "select" ? "1" : "✓"; color: sessionStore.combatCurrentStep === "select" ? "#2C1E12" : "#FFFFFF"; font.pixelSize: theme.smallSize; font.bold: true }
                        }
                        Text { text: "选择战争"; color: "#2C1E12"; font.pixelSize: theme.bodySize; anchors.verticalCenter: parent.verticalCenter; font.bold: sessionStore.combatCurrentStep === "select" }
                    }
                    Text { text: "→"; color: "#B8A080"; font.pixelSize: theme.bodySize; anchors.verticalCenter: parent.verticalCenter }
                    Row {
                        spacing: 4
                        anchors.verticalCenter: parent.verticalCenter
                        Rectangle {
                            width: 20; height: 20; radius: 10
                            color: sessionStore.combatCurrentStep === "action" ? "#E8B84B" : "#E8D5C4"
                            Text { anchors.centerIn: parent; text: "2"; color: "#2C1E12"; font.pixelSize: theme.smallSize; font.bold: true }
                        }
                        Text { text: "进攻/防御"; color: sessionStore.combatCurrentStep === "action" ? "#2C1E12" : "#766652"; font.pixelSize: theme.bodySize; anchors.verticalCenter: parent.verticalCenter; font.bold: sessionStore.combatCurrentStep === "action" }
                    }
                    Text { text: "→"; color: "#B8A080"; font.pixelSize: theme.bodySize; anchors.verticalCenter: parent.verticalCenter }
                    Row {
                        spacing: 4
                        anchors.verticalCenter: parent.verticalCenter
                        Rectangle {
                            width: 20; height: 20; radius: 10
                            color: sessionStore.combatCurrentStep === "result" ? "#E8B84B" : "#E8D5C4"
                            Text { anchors.centerIn: parent; text: "3"; color: "#2C1E12"; font.pixelSize: theme.smallSize; font.bold: true }
                        }
                        Text { text: "查看战果"; color: sessionStore.combatCurrentStep === "result" ? "#2C1E12" : "#766652"; font.pixelSize: theme.bodySize; anchors.verticalCenter: parent.verticalCenter }
                    }
                    Text { text: "→"; color: "#B8A080"; font.pixelSize: theme.bodySize; anchors.verticalCenter: parent.verticalCenter }
                    Row {
                        spacing: 4
                        anchors.verticalCenter: parent.verticalCenter
                        Rectangle { width: 20; height: 20; radius: 10; color: "#E8D5C4"; Text { anchors.centerIn: parent; text: "4"; color: "#2C1E12"; font.pixelSize: theme.smallSize; font.bold: true } }
                        Text { text: "推进决算"; color: "#766652"; font.pixelSize: theme.bodySize; anchors.verticalCenter: parent.verticalCenter }
                    }
                }
            }

        }

        // ---- StageContentSlot: phase stage components ----
        Rectangle {
            id: stageContainer
            objectName: "stageContainer"
            parent: centerPanel.stageContent
            anchors.fill: parent
            color: "transparent"

            MortalityStage {
                id: mortalityStage
                objectName: "mortalityStage"
                anchors.fill: parent
                visible: sessionStore.selectedPhaseId === "mortality"
            }

            PopulationStage {
                id: populationStage
                objectName: "populationStage"
                anchors.fill: parent
                visible: sessionStore.selectedPhaseId === "population"
            }

            SenateStage {
                id: senateStage
                objectName: "senateStage"
                anchors.fill: parent
                visible: sessionStore.selectedPhaseId === "senate"
            }

            RevenueStage {
                id: revenueStage
                objectName: "revenueStage"
                anchors.fill: parent
                visible: sessionStore.selectedPhaseId === "revenue"
            }

            ForumStage {
                id: forumStage
                objectName: "forumStage"
                anchors.fill: parent
                visible: sessionStore.selectedPhaseId === "forum"
            }

            CombatStage {
                id: combatStage
                objectName: "combatStage"
                anchors.fill: parent
                visible: sessionStore.selectedPhaseId === "combat"
            }

            LockedStagePlaceholder {
                id: lockedPlaceholder
                objectName: "lockedStagePlaceholder"
                anchors.fill: parent
                visible: sessionStore.selectedPhaseId !== "mortality"
                    && sessionStore.selectedPhaseId !== "revenue"
                    && sessionStore.selectedPhaseId !== "forum"
                    && sessionStore.selectedPhaseId !== "population"
                    && sessionStore.selectedPhaseId !== "senate"
                    && sessionStore.selectedPhaseId !== "combat"
            }
        }

        // ---- StageActionSlot: phase action buttons ----
        Rectangle {
            id: mortalityActionLayer
            objectName: "mortalityActionLayer"
            parent: centerPanel
            anchors.left: parent.left
            anchors.right: parent.right
            anchors.bottom: parent.bottom
            anchors.bottomMargin: 20
            height: 34
            color: "transparent"
            visible: true
            z: 50

            // Execute button (only visible in mortality phase)
            // Two-state: execute -> done (advance button is in ContextPanel)
            Rectangle {
                id: executeBtn
                objectName: "mortalityPrimaryActionButton"
                anchors.horizontalCenter: parent.horizontalCenter
                anchors.verticalCenter: parent.verticalCenter
                width: sessionStore.canExecuteMortality ? 180 : 88
                height: 30
                radius: 4
                visible: sessionStore.selectedPhaseId === "mortality"
                z: 10
                opacity: 1.0
                border.color: sessionStore.canExecuteMortality ? "transparent" : "#D9AF63"
                border.width: sessionStore.canExecuteMortality ? 0 : 1

                // Use hover property to toggle gradient
                property bool hovered: false

                // Drop shadow is active when button is usable.
                layer.enabled: sessionStore.canExecuteMortality
                layer.effect: DropShadow {
                    transparentBorder: true
                    horizontalOffset: 0
                    verticalOffset: 3
                    radius: 8
                    samples: 16
                    color: "#B0000000"
                }

                gradient: Gradient {
                    orientation: Gradient.Vertical
                    GradientStop {
                        position: 0.0
                        color: sessionStore.canExecuteMortality
                            ? (executeBtn.hovered ? "#A33A17" : "#84250A")
                            : "#C89A80"
                    }
                    GradientStop {
                        position: 1.0
                        color: sessionStore.canExecuteMortality
                            ? (executeBtn.hovered ? "#7A210B" : "#671B07")
                            : "#A97962"
                    }
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
                    text: sessionStore.canExecuteMortality ? "⚡ 执行天命" : "✓ 已执行"
                    color: theme.headerText
                    font.pixelSize: 13; font.bold: true
                }

                MouseArea {
                    anchors.fill: parent
                    enabled: sessionStore.canExecuteMortality
                    hoverEnabled: true
                    cursorShape: Qt.PointingHandCursor
                    onEntered: executeBtn.hovered = true
                    onExited: executeBtn.hovered = false
                    onClicked: {
                        var result = sessionStore.doExecuteMortality()
                        if (!result.success) {
                            mortalityStage.showFeedback("error", result.message)
                        }
                    }
                }
            }
        }

        // Revenue action layer: only settlement button
        // Advance button is in ContextPanel.OperationSection
        Rectangle {
            id: revenueActionLayer
            objectName: "revenueActionLayer"
            parent: centerPanel
            anchors.left: parent.left
            anchors.right: parent.right
            anchors.bottom: parent.bottom
            anchors.bottomMargin: 20
            height: 34
            color: "transparent"
            visible: sessionStore.selectedPhaseId === "revenue"
            z: 50

            // Revenue primary action button: settle -> done
            Rectangle {
                id: revenueExecuteBtn
                objectName: "revenuePrimaryActionButton"
                anchors.horizontalCenter: parent.horizontalCenter
                anchors.verticalCenter: parent.verticalCenter
                width: sessionStore.canExecuteRevenue ? 180 : 88
                height: 30
                radius: 4
                z: 10

                property bool hovered: false

                // Drop shadow
                layer.enabled: sessionStore.canExecuteRevenue
                layer.effect: DropShadow {
                    transparentBorder: true
                    horizontalOffset: 0
                    verticalOffset: 3
                    radius: 8
                    samples: 16
                    color: "#B0000000"
                }

                gradient: Gradient {
                    orientation: Gradient.Vertical
                    GradientStop {
                        position: 0.0
                        color: sessionStore.canExecuteRevenue
                            ? (revenueExecuteBtn.hovered ? "#A33A17" : "#84250A")
                            : "#C89A80"
                    }
                    GradientStop {
                        position: 1.0
                        color: sessionStore.canExecuteRevenue
                            ? (revenueExecuteBtn.hovered ? "#7A210B" : "#671B07")
                            : "#A97962"
                    }
                }

                // Top highlight edge
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
                    text: sessionStore.canExecuteRevenue
                        ? "💰 确认收入结算"
                        : "✓ 不可操作"
                    color: theme.headerText
                    font.pixelSize: 13; font.bold: true
                }

                MouseArea {
                    anchors.fill: parent
                    enabled: sessionStore.canExecuteRevenue
                    hoverEnabled: true
                    cursorShape: Qt.PointingHandCursor
                    onEntered: revenueExecuteBtn.hovered = true
                    onExited: revenueExecuteBtn.hovered = false
                    onClicked: {
                        var result = sessionStore.doExecuteRevenue()
                        if (!result.success) {
                            revenueStage.showFeedback("error", result.message)
                        }
                    }
                }
            }
        }
    }

    readonly property bool populationCampaignDone: sessionStore.populationResolved
        || sessionStore.populationCurrentStep !== "campaign"
        || (sessionStore.populationCampaigns || []).length > 0

    // 玩家交接遮罩
    PlayerHandoffOverlay {
        id: handoffOverlay
        objectName: "playerHandoffOverlay"
        anchors.fill: parent
        visible: false
        z: 100
    }

    QueryResultOverlay {
        id: queryResultOverlay
        objectName: "queryResultOverlay"
        anchors.fill: parent
    }
}
