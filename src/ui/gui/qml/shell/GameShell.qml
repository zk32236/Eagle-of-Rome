import QtQuick 2.15
import QtQuick.Controls 2.15
import QtQuick.Layouts 1.15
import Qt5Compat.GraphicalEffects

import "../stages"
import "../components"
import "../i18n"

/*!
 * \brief GameShell — v3.25.1 Codex v4.0 main shell skeleton.
 *
 * Layout contract: GUI_LAYOUT_CONTRACT_Phase1_v3.25.1.md
 *
 *   A — TopStatusBar:  x=10, y=10, w=1420, h=62
 *   B — PhaseRail:     x=10, y=82, w=92, h=736   (inside main-wrapper: padding=10)
 *   C — StageDesktop:  x=112, y=82, w=1022, h=736 (center, gap=10 each side)
 *   D — ContextPanel:  x=1144, y=82, w=286, h=736
 *   E — BottomQueryBar: x=10, y=828, w=1420, h=62
 *   F — MainAction:    inside StageDesktop.StageActionSlot
 *
 * Viewport: 1440×900. main-wrapper replaces anchors with direct positioning
 * to match exact contract coordinates.
 */
Rectangle {
    id: root
    objectName: "gameShellRoot"
    color: theme.bgApp

    // 暴露给外部的方法
    function showFeedback(type, message) {
        contextPanel.showFeedback(type, message)
    }
    function showHandoff(nextPlayerId) {
        handoffOverlay.show(nextPlayerId)
    }

    // ============================================================
    // A — TopStatusBar (§2)
    // x=10, y=10, w=1420, h=62
    // ============================================================
    TopStatusBar {
        id: topBar
        objectName: "topStatusBar"
        anchors.top: parent.top
        anchors.topMargin: 10
        anchors.left: parent.left
        anchors.leftMargin: 10
        anchors.right: parent.right
        anchors.rightMargin: 10
        height: 62
    }

    // ============================================================
    // main-wrapper inner padding = 10px all sides
    // Content area: y = 10(header margin) + 62(header h) + 10(padding) = 82
    // Content area left: 10(padding)
    // ============================================================

    // ============================================================
    // B — PhaseRail (§3)
    // x=10, y=82, w=92, h=736
    // ============================================================
    PhaseRail {
        id: phaseRail
        objectName: "phaseRail"
        anchors.top: topBar.bottom
        anchors.topMargin: 10     // main-wrapper padding top
        anchors.left: parent.left
        anchors.leftMargin: 10    // main-wrapper padding left
        anchors.bottom: bottomQueryBar.top
        anchors.bottomMargin: 10  // main-wrapper padding bottom
        width: 92
    }

    // ============================================================
    // D — ContextPanel (§5)
    // x=1144, y=82, w=286, h=736
    // ============================================================
    ContextPanel {
        id: contextPanel
        objectName: "contextPanel"
        anchors.top: topBar.bottom
        anchors.topMargin: 10
        anchors.right: parent.right
        anchors.rightMargin: 10
        anchors.bottom: bottomQueryBar.top
        anchors.bottomMargin: 10
        width: 286
    }

    // ============================================================
    // E — BottomQueryBar (§6)
    // x=10, y=828, w=1420, h=62
    // ============================================================
    BottomQueryBar {
        id: bottomQueryBar
        objectName: "bottomQueryBar"
        anchors.left: parent.left
        anchors.leftMargin: 10
        anchors.right: parent.right
        anchors.rightMargin: 10
        anchors.bottom: parent.bottom
        anchors.bottomMargin: 10
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
    // C — StageDesktop (§4) — H0: 4 slots populated per phase
    // x=112, y=82, w=1022, h=736
    // Gap B→C = 10, gap C→D = 10
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
        anchors.topMargin: 10
        anchors.left: phaseRail.right
        anchors.leftMargin: 10   // gap B→C
        anchors.right: contextPanel.left
        anchors.rightMargin: 10  // gap C→D
        anchors.bottom: bottomQueryBar.top
        anchors.bottomMargin: 10

        // ---- StageHeaderSlot — mortality badge+title+desc / other phases generic ----
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

                // Phase badge (999px pill style) — H0.2: gradient per layout contract §4.1
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
                    text: "🎴 " + GuiText.mortalityTitle
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
                    text: "💰 " + "收入结算"
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

            // Other phases: generic header (original stageAnnouncement style)
            ColumnLayout {
                visible: sessionStore.selectedPhaseId !== "mortality"
                    && sessionStore.selectedPhaseId !== "revenue"
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
        }

        // ---- StageInstructionSlot — mortality step bar (visible for all phases) ----
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
        }

        // ---- StageContentSlot — phase stage components ----
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

            LockedStagePlaceholder {
                id: lockedPlaceholder
                objectName: "lockedStagePlaceholder"
                anchors.fill: parent
                visible: sessionStore.selectedPhaseId !== "mortality"
                    && sessionStore.selectedPhaseId !== "revenue"
                    && sessionStore.selectedPhaseId !== "population"
                    && sessionStore.selectedPhaseId !== "senate"
            }
        }

        // ---- StageActionSlot — mortality execute button ----
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
            // Two-state: execute → done (advance button is in ContextPanel)
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

                // Drop shadow (D-06) — active when button is usable
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
                    text: sessionStore.canExecuteMortality ? "⚡ 执行天命" : "✅ 已执行"
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

        // Revenue action layer — only settlement button
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

            // Revenue primary action button — Two-state: settle → done
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
                        : "⛔ 不可操作"
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
