import QtQuick 2.15
import QtQuick.Controls 2.15
import QtQuick.Layouts 1.15


Rectangle {
    id: root
    height: 60
    radius: theme.radius
    color: theme.bgSurface2
    border.color: theme.borderNormal
    border.width: 1

    property string icon: ""
    property string label: ""
    property string value: ""

    RowLayout {
        anchors.fill: parent
        anchors.margins: 10
        spacing: 8

        Text {
            text: root.icon
            font.pixelSize: 16
            Layout.preferredWidth: 24
        }
        ColumnLayout {
            spacing: 2
            Layout.fillWidth: true
            Text {
                text: root.label
                color: theme.textMuted
                font.pixelSize: 10
            }
            Text {
                text: root.value
                color: theme.textPrimary
                font.pixelSize: 14
                font.bold: true
            }
        }
    }
}
