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
 *   A - TopStatusBar:  x=14, y=14, w=1412, h=62
 *   B - PhaseRail:     x=14, y=90, w=92, h=736   (inside main-wrapper: padding=14)
 *   C - StageDesktop:  x=120, y=90, w=1022, h=736 (center, gap=14 each side)
 *   D - ContextPanel:  x=1156, y=90, w=286, h=736
 *   E - BottomQueryBar: x=14, y=840, w=1412, h=46
 *   F - MainAction:    inside StageDesktop.StageActionSlot
 *
 * Viewport: 1440x900 (fixed baseline). main-wrapper inner padding = 14px all sides.
 * All coordinates match the SA GUI Layout Contract §6.2.
 * See workspace/dev-tasks/EOR-Phase7-R1-SA-Development-Task.md §6 for reference.
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
    // x=10, y=828, w=1420, h=46 (P2-05: 62→46 per SA Layout Contract §6.2)
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
        height: 46
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
        // R8（SA §4.1 `U_S` 唯一化，FC-UI-06，AC-06；G2-delta-3/4）：Senate 相位不预留空
        // StageActionSlot（46→0，走既有 compactActionSlot 机制）；折叠后 Content→Action 槽间隔随
        // 不可见项消除（10→0）；另有 absorbBottomPadding 让渡 StageDesktop 底内边距 18。
        // 仅 Senate 相位受影响；population/forum 既有行为不变。
        compactActionSlot: sessionStore.selectedPhaseId === "population"
                           || sessionStore.selectedPhaseId === "forum"
                           || sessionStore.selectedPhaseId === "senate"
        absorbBottomPadding: sessionStore.selectedPhaseId === "senate"

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
                    text: "🃏 " + L10n.t("mortality.title")
                    color: "#681B07"
                    font.pixelSize: 20
                    font.bold: true
                    font.letterSpacing: 0.3
                }

                // Phase description
                Text {
                    text: {
                        var _descKey = sessionStore.selectedPhaseSummary.description_key
                        var _desc = _descKey ? L10n.t(_descKey) : ""
                        return (_desc && _desc !== _descKey) ? _desc : GuiText.mortalityIntro
                    }
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

            // Resolution phase: badge "7/7" + title + description
            ColumnLayout {
                visible: sessionStore.selectedPhaseId === "resolution"
                anchors.fill: parent
                spacing: 6

                Rectangle {
                    Layout.preferredWidth: resolutionBadgeText.implicitWidth + 24
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
                        id: resolutionBadgeText
                        anchors.centerIn: parent
                        text: "7 / 7"
                        color: theme.headerText
                        font.pixelSize: theme.statLabelSize
                        font.bold: true
                    }
                }

                Text {
                    text: "📋 决算阶段"
                    color: "#681B07"
                    font.pixelSize: 20
                    font.bold: true
                    font.letterSpacing: 0.3
                }

                Text {
                    text: "年度总结与决算公示，确认后推进到下一年度。"
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
                    && sessionStore.selectedPhaseId !== "resolution"
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

        // ---- StageInstructionSlot: phase step bar (WP-J J-AC-10) ----
        // StepBar = 唯一渲染 owner：逐字渲染 sessionStore.phaseSteps（各阶段 get_*_view().steps
        // 权威读模型）。内联六阶段步骤条已退役（含公示区伪节点、「查看事件结果」伪步骤、
        // 以及 QML 业务重建 root.populationCampaignDone）。公示区不进步骤条（FC-06）。
        Rectangle {
            id: phaseStepBarFrame
            objectName: "phaseStepBarFrame"
            parent: centerPanel.stageInstruction
            anchors.fill: parent
            color: "#D1FFF9EC"
            border.color: "#85A8753B"
            border.width: 1
            radius: 10
            visible: (sessionStore.phaseSteps || []).length > 0

            StepBar {
                id: phaseStepBar
                objectName: "phaseStepBar"
                anchors.fill: parent
                anchors.leftMargin: 12
                anchors.rightMargin: 12
                steps: sessionStore.phaseSteps || []
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

            ResolutionStage {
                id: resolutionStage
                objectName: "resolutionStage"
                anchors.fill: parent
                visible: sessionStore.selectedPhaseId === "resolution"
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
                    && sessionStore.selectedPhaseId !== "resolution"
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
                    text: sessionStore.canExecuteMortality ? ("⚡ " + L10n.t("mortality.action.execute")) : ("✓ " + L10n.t("mortality.action.done"))
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

        // ============================================================
        // Resolution action layer: REMOVED
        // This placeholder rebellion button (disabled, visible on resolved)
        // was duplicate #3 of the phase advance button.
        // The sole advance button is in ContextPanel.OperationSection.
        // ============================================================
    }

    // WP-J J-AC-10 / FC-08: QML 业务重建已移除 ——
    // 旧 `populationCampaignDone` 复合式（populationResolved || currentStep!="campaign" || campaigns>0）
    // 已被权威步骤读模型（sessionStore.phaseSteps / population view `steps`）取代。

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
