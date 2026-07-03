import QtQuick 2.15
import QtQuick.Controls 2.15
import QtQuick.Layouts 1.15

import "../i18n"

Rectangle {
    id: root
    color: theme.bgApp

    function itemText(item, fallbackName) {
        if (!item) return fallbackName || ""
        return item.name || item.leader_name || item.province_name || item.contract_id || fallbackName || ""
    }

    function detailText(item) {
        if (!item) return ""
        if (item.faction_name) {
            return GuiText.senateInfluenceDetail(item.faction_name, item.influence)
        }
        if (item.threat_level !== undefined) {
            return GuiText.senateThreatDetail(item.threat_level, item.naval_required)
        }
        if (item.indemnity !== undefined) {
            return GuiText.senatePeaceDetail(item.indemnity, item.duration)
        }
        if (item.governor_type_name) {
            return item.governor_type_name
        }
        if (item.base_cost !== undefined) {
            return GuiText.senateContractDetail(item.base_cost, item.expected_profit)
        }
        return item.status || item.type || ""
    }

    ColumnLayout {
        anchors.fill: parent
        anchors.margins: 20
        spacing: 14

        RowLayout {
            Layout.fillWidth: true
            spacing: 16
            Text {
                text: GuiText.senateTitle
                color: theme.textPrimary
                font.pixelSize: 18
                font.family: theme.fontTitle
                font.bold: true
            }
            Text {
                text: GuiText.senateReadonlyIntro
                color: theme.textSecondary
                font.pixelSize: 12
                Layout.fillWidth: true
                wrapMode: Text.Wrap
            }
            Text {
                text: GuiText.senateReadonlyBadge
                color: theme.accentBronze
                font.pixelSize: 12
                font.bold: true
            }
        }

        Rectangle {
            Layout.fillWidth: true
            Layout.preferredHeight: 92
            color: theme.bgSurface1
            border.color: theme.borderNormal
            border.width: 1
            radius: theme.radius

            ColumnLayout {
                anchors.fill: parent
                anchors.margins: 14
                spacing: 6
                Text {
                    text: (sessionStore.senateView.summary && sessionStore.senateView.summary.message)
                        ? sessionStore.senateView.summary.message
                        : GuiText.senateFutureTaskHint
                    color: theme.accentPrimary
                    font.pixelSize: 13
                    font.bold: true
                    Layout.fillWidth: true
                    wrapMode: Text.Wrap
                }
                Text {
                    text: GuiText.senateCountLine(sessionStore.senateView)
                    color: theme.textSecondary
                    font.pixelSize: 11
                    Layout.fillWidth: true
                    wrapMode: Text.Wrap
                }
                Text {
                    text: GuiText.senateActionsDisabled
                    color: theme.statusWarning
                    font.pixelSize: 11
                    Layout.fillWidth: true
                    wrapMode: Text.Wrap
                }
            }
        }

        RowLayout {
            Layout.fillWidth: true
            spacing: 12

            Rectangle {
                Layout.fillWidth: true
                Layout.preferredHeight: 82
                color: theme.bgSurface1
                border.color: theme.borderNormal
                border.width: 1
                radius: theme.radius

                ColumnLayout {
                    anchors.fill: parent
                    anchors.margins: 12
                    spacing: 6
                    Text {
                        text: GuiText.senatePresidingOfficer
                        color: theme.textPrimary
                        font.pixelSize: 13
                        font.bold: true
                    }
                    Text {
                        text: sessionStore.senatePresidingOfficer.name
                            ? sessionStore.senatePresidingOfficer.name + " / " + (sessionStore.senatePresidingOfficer.office || "")
                            : GuiText.senateNoItems
                        color: theme.textSecondary
                        font.pixelSize: 12
                        Layout.fillWidth: true
                        wrapMode: Text.Wrap
                    }
                }
            }

            Rectangle {
                Layout.fillWidth: true
                Layout.preferredHeight: 82
                color: theme.bgSurface1
                border.color: theme.borderNormal
                border.width: 1
                radius: theme.radius

                ColumnLayout {
                    anchors.fill: parent
                    anchors.margins: 12
                    spacing: 6
                    Text {
                        text: GuiText.senateFactionLeaders
                        color: theme.textPrimary
                        font.pixelSize: 13
                        font.bold: true
                    }
                    Text {
                        text: sessionStore.senateFactionLeaders.length > 0
                            ? GuiText.senateLeaderCount(sessionStore.senateFactionLeaders.length)
                            : GuiText.senateNoItems
                        color: theme.textSecondary
                        font.pixelSize: 12
                    }
                }
            }
        }

        ScrollView {
            Layout.fillWidth: true
            Layout.fillHeight: true
            clip: true

            ColumnLayout {
                width: parent.width
                spacing: 12

                SenateReadOnlySection {
                    title: GuiText.senateFactionLeaders
                    items: sessionStore.senateFactionLeaders
                }
                SenateReadOnlySection {
                    title: GuiText.senateActiveWars
                    items: sessionStore.senateActiveForeignWars
                }
                SenateReadOnlySection {
                    title: GuiText.senateWarThreats
                    items: sessionStore.senateWarThreats
                }
                SenateReadOnlySection {
                    title: GuiText.senatePendingPeace
                    items: sessionStore.senatePendingPeaceTreaties
                }
                SenateReadOnlySection {
                    title: GuiText.senateGovernorVacancies
                    items: sessionStore.senateGovernorVacancies
                }
                SenateReadOnlySection {
                    title: GuiText.senatePendingContracts
                    items: sessionStore.senatePendingContracts
                }
            }
        }

        Text {
            text: GuiText.senateFutureTaskHint
            color: theme.textMuted
            font.pixelSize: 11
            wrapMode: Text.Wrap
            Layout.fillWidth: true
        }
    }

    component SenateReadOnlySection: Rectangle {
        property string title: ""
        property var items: []

        Layout.fillWidth: true
        height: sectionColumn.implicitHeight + 22
        color: theme.bgSurface1
        border.color: theme.borderNormal
        border.width: 1
        radius: theme.radius

        ColumnLayout {
            id: sectionColumn
            anchors.left: parent.left
            anchors.right: parent.right
            anchors.margins: 12
            anchors.verticalCenter: parent.verticalCenter
            spacing: 8

            Text {
                text: title
                color: theme.textPrimary
                font.pixelSize: 13
                font.bold: true
                Layout.fillWidth: true
            }

            Text {
                visible: !items || items.length === 0
                text: GuiText.senateNoItems
                color: theme.textMuted
                font.pixelSize: 11
            }

            Repeater {
                model: items || []
                delegate: ColumnLayout {
                    Layout.fillWidth: true
                    spacing: 2

                    Text {
                        text: root.itemText(modelData, "")
                        color: theme.accentBronze
                        font.pixelSize: 12
                        font.bold: true
                        Layout.fillWidth: true
                        wrapMode: Text.Wrap
                    }
                    Text {
                        text: root.detailText(modelData)
                        color: theme.textSecondary
                        font.pixelSize: 10
                        Layout.fillWidth: true
                        wrapMode: Text.Wrap
                    }
                }
            }
        }
    }
}
