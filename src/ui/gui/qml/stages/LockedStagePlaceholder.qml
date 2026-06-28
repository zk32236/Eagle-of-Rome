import QtQuick 2.15
import QtQuick.Controls 2.15
import QtQuick.Layouts 1.15


Rectangle {
    id: root
    color: theme.bgApp

    ColumnLayout {
        anchors.centerIn: parent
        spacing: 16

        Text {
            Layout.alignment: Qt.AlignHCenter
            text: "🔒"
            font.pixelSize: 48
        }
        Text {
            Layout.alignment: Qt.AlignHCenter
            text: "尚未迁移"
            color: theme.textPrimary
            font.pixelSize: 18
            font.bold: true
        }
        Text {
            Layout.alignment: Qt.AlignHCenter
            text: "该阶段将在后续 P1 功能开发中逐步接入 GUI。"
            color: theme.textSecondary
            font.pixelSize: 12
        }
    }
}
