import QtQuick 2.15
import QtQuick.Controls 2.15
import QtQuick.Layouts 1.15

import "../stages"
import "../components"
import "../i18n"

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

    // 顶部状态栏
    TopStatusBar {
        id: topBar
        objectName: "topStatusBar"
        anchors.top: parent.top
        anchors.left: parent.left
        anchors.right: parent.right
        height: 56
    }

    // 左侧阶段导航
    PhaseRail {
        id: phaseRail
        objectName: "phaseRail"
        anchors.top: topBar.bottom
        anchors.left: parent.left
        anchors.bottom: bottomQueryBar.top
        width: 176
    }

    // 右侧上下文面板
    ContextPanel {
        id: contextPanel
        objectName: "contextPanel"
        anchors.top: topBar.bottom
        anchors.right: parent.right
        anchors.bottom: bottomQueryBar.top
        width: 320
    }

    BottomQueryBar {
        id: bottomQueryBar
        objectName: "bottomQueryBar"
        anchors.left: parent.left
        anchors.right: parent.right
        anchors.bottom: parent.bottom
        height: 76
        onQueryRequested: function(queryId) {
            var result = sessionStore.doGlobalQuery(queryId)
            if (result.success) {
                queryResultOverlay.open()
            } else {
                showFeedback("error", result.message)
            }
        }
    }

    // 中央阶段容器
    Rectangle {
        id: centerPanel
        objectName: "centerPanel"
        anchors.top: topBar.bottom
        anchors.left: phaseRail.right
        anchors.right: contextPanel.left
        anchors.bottom: bottomQueryBar.top
        color: theme.bgApp
        border.color: theme.borderNormal
        border.width: 0

        Rectangle {
            id: stageAnnouncement
            objectName: "stageAnnouncement"
            anchors.top: parent.top
            anchors.left: parent.left
            anchors.right: parent.right
            height: 96
            color: theme.bgSurface1
            border.color: theme.borderNormal
            border.width: 1

            ColumnLayout {
                anchors.fill: parent
                anchors.margins: 14
                spacing: 6

                RowLayout {
                    Layout.fillWidth: true
                    Text {
                        text: GuiText.stageAnnouncementTitle
                        color: theme.textMuted
                        font.pixelSize: 11
                        font.bold: true
                    }
                    Item { Layout.fillWidth: true }
                    Text {
                        text: GuiText.stageModeText(sessionStore.selectedPhaseSummary)
                        color: sessionStore.selectedPhaseSummary.actionable ? theme.statusSuccess : theme.statusWarning
                        font.pixelSize: 11
                        font.bold: true
                    }
                }
                Text {
                    text: sessionStore.selectedPhaseName || sessionStore.currentPhaseName || GuiText.populationFallbackName
                    color: theme.textPrimary
                    font.pixelSize: 18
                    font.family: theme.fontTitle
                    font.bold: true
                    Layout.fillWidth: true
                }
                Text {
                    text: sessionStore.selectedPhaseSummary.description || GuiText.placeholderFallbackDescription
                    color: theme.textSecondary
                    font.pixelSize: 12
                    wrapMode: Text.Wrap
                    Layout.fillWidth: true
                }
            }
        }

        Rectangle {
            id: stageContainer
            objectName: "stageContainer"
            anchors.top: stageAnnouncement.bottom
            anchors.left: parent.left
            anchors.right: parent.right
            anchors.bottom: parent.bottom
            color: theme.bgApp
            border.color: theme.borderNormal
            border.width: 0

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

            LockedStagePlaceholder {
                id: lockedPlaceholder
                objectName: "lockedStagePlaceholder"
                anchors.fill: parent
                visible: sessionStore.selectedPhaseId !== "mortality"
                    && sessionStore.selectedPhaseId !== "population"
                    && sessionStore.selectedPhaseId !== "senate"
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
