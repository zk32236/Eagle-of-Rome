import QtQuick 2.15
import QtQuick.Controls 2.15
import QtQuick.Layouts 1.15

import "../components"
import "../i18n"

Rectangle {
    id: root
    color: theme.bgApp

    ColumnLayout {
        anchors.fill: parent
        anchors.margins: 20
        spacing: 16

        RowLayout {
            Layout.fillWidth: true
            spacing: 16
            Text {
                text: GuiText.mortalityTitle
                color: theme.textPrimary
                font.pixelSize: 18
                font.family: theme.fontTitle
                font.bold: true
            }
            Text {
                text: GuiText.mortalityIntro
                color: theme.textSecondary
                font.pixelSize: 12
                Layout.fillWidth: true
                wrapMode: Text.Wrap
            }
            Text {
                text: sessionStore.canExecuteMortality ? GuiText.mortalityReady : GuiText.mortalityResolved
                color: sessionStore.canExecuteMortality ? theme.accentBronze : theme.textMuted
                font.pixelSize: 12
                font.bold: true
            }
        }

        Rectangle {
            Layout.fillWidth: true
            Layout.preferredHeight: 88
            color: theme.bgSurface1
            border.color: theme.borderNormal
            border.width: 1
            radius: theme.radius

            ColumnLayout {
                anchors.fill: parent
                anchors.margins: 14
                spacing: 6
                Text {
                    text: GuiText.currentPhase + "：" + (sessionStore.currentPhaseName || "")
                    color: theme.accentPrimary
                    font.pixelSize: 13
                    font.bold: true
                }
                Text {
                    text: GuiText.mortalityContinueHint
                    color: theme.textSecondary
                    font.pixelSize: 11
                    wrapMode: Text.Wrap
                    Layout.fillWidth: true
                }
            }
        }

        Rectangle {
            Layout.fillWidth: true
            Layout.fillHeight: true
            color: theme.bgSurface1
            border.color: theme.borderNormal
            border.width: 1
            radius: theme.radius

            ColumnLayout {
                anchors.fill: parent
                anchors.margins: 14
                spacing: 10

                Text {
                    text: GuiText.mortalityEventsTitle
                    color: theme.textPrimary
                    font.pixelSize: 14
                    font.bold: true
                }

                Text {
                    visible: (sessionStore.mortalityEvents || []).length === 0
                    text: GuiText.mortalityNoResult
                    color: theme.textMuted
                    font.pixelSize: 12
                    wrapMode: Text.Wrap
                    Layout.fillWidth: true
                }

                ScrollView {
                    visible: (sessionStore.mortalityEvents || []).length > 0
                    Layout.fillWidth: true
                    Layout.fillHeight: true
                    clip: true

                    ColumnLayout {
                        width: parent.width
                        spacing: 8
                        Repeater {
                            model: sessionStore.mortalityEvents || []
                            delegate: Rectangle {
                                Layout.fillWidth: true
                                height: eventColumn.implicitHeight + 18
                                color: theme.bgSurface2
                                border.color: theme.borderNormal
                                border.width: 1
                                radius: theme.radius

                                ColumnLayout {
                                    id: eventColumn
                                    anchors.left: parent.left
                                    anchors.right: parent.right
                                    anchors.margins: 9
                                    anchors.verticalCenter: parent.verticalCenter
                                    spacing: 5

                                    Text {
                                        text: modelData.name || ""
                                        color: theme.accentBronze
                                        font.pixelSize: 13
                                        font.bold: true
                                        Layout.fillWidth: true
                                    }
                                    Text {
                                        text: modelData.summary || ""
                                        color: theme.textSecondary
                                        font.pixelSize: 11
                                        wrapMode: Text.Wrap
                                        Layout.fillWidth: true
                                    }
                                    Repeater {
                                        model: modelData.impacts || []
                                        delegate: Text {
                                            text: GuiText.mortalityImpactText(modelData)
                                            color: theme.textMuted
                                            font.pixelSize: 10
                                            wrapMode: Text.Wrap
                                            Layout.fillWidth: true
                                        }
                                    }
                                }
                            }
                        }
                    }
                }
            }
        }

        RowLayout {
            Layout.fillWidth: true
            spacing: 10
            AppButton {
                Layout.preferredWidth: 180
                text: GuiText.executeMortality
                type: "primary"
                enabled: sessionStore.canExecuteMortality
                onClicked: {
                    var result = sessionStore.doExecuteMortality()
                    if (!result.success) {
                        showFeedback("error", result.message)
                    }
                }
            }
            AppButton {
                Layout.preferredWidth: 180
                text: GuiText.advanceMortality
                type: "primary"
                enabled: sessionStore.canAdvanceMortality
                onClicked: {
                    var result = sessionStore.doAdvanceMortality()
                    if (!result.success) {
                        showFeedback("error", result.message)
                    }
                }
            }
            Text {
                text: sessionStore.selectedPhaseSummary.disabled_reason || ""
                visible: !sessionStore.canExecuteMortality && !sessionStore.canAdvanceMortality
                color: theme.textMuted
                font.pixelSize: 11
                wrapMode: Text.Wrap
                Layout.fillWidth: true
            }
        }
    }
}
