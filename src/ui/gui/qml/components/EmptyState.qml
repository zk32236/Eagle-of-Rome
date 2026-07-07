import QtQuick 2.15
import QtQuick.Controls 2.15
import QtQuick.Layouts 1.15


ColumnLayout {
    spacing: 8

    property string icon: "📭"
    property string title: "空状态"
    property string subtitle: ""

    Text {
        Layout.alignment: Qt.AlignHCenter
        text: icon
        font.pixelSize: 32
    }
    Text {
        Layout.alignment: Qt.AlignHCenter
        text: title
        color: theme.textPrimary
        font.pixelSize: 14
        font.bold: true
    }
    Text {
        Layout.alignment: Qt.AlignHCenter
        text: subtitle
        color: theme.textSecondary
        font.pixelSize: 11
        visible: subtitle.length > 0
    }
}
