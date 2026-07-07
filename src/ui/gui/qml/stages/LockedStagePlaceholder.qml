import QtQuick 2.15
import QtQuick.Controls 2.15
import QtQuick.Layouts 1.15

import "../i18n"

Rectangle {
    id: root
    color: theme.bgApp

    ColumnLayout {
        anchors.centerIn: parent
        spacing: 16

        Text {
            Layout.alignment: Qt.AlignHCenter
            text: sessionStore.selectedPhaseSummary.handoff_task || GuiText.placeholderFallbackTask
            color: theme.accentBronze
            font.pixelSize: 18
            font.bold: true
        }
        Text {
            Layout.alignment: Qt.AlignHCenter
            text: sessionStore.selectedPhaseName || GuiText.placeholderFallbackName
            color: theme.textPrimary
            font.pixelSize: 18
            font.bold: true
        }
        Text {
            Layout.alignment: Qt.AlignHCenter
            text: sessionStore.selectedPhaseSummary.description || GuiText.placeholderFallbackDescription
            color: theme.textSecondary
            font.pixelSize: 12
            horizontalAlignment: Text.AlignHCenter
            wrapMode: Text.Wrap
            Layout.preferredWidth: 420
        }
        Text {
            Layout.alignment: Qt.AlignHCenter
            text: sessionStore.selectedPhaseSummary.disabled_reason || GuiText.placeholderFallbackReason
            color: theme.statusWarning
            font.pixelSize: 12
            horizontalAlignment: Text.AlignHCenter
            wrapMode: Text.Wrap
            Layout.preferredWidth: 420
        }
    }
}
