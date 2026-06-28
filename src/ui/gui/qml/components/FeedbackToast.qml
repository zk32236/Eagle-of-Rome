import QtQuick 2.15
import QtQuick.Controls 2.15
import QtQuick.Layouts 1.15


Rectangle {
    id: root
    height: 40
    radius: theme.radius
    color: {
        if (type === "success") return "#1A70A17C"
        if (type === "error") return "#1AC45151"
        if (type === "warning") return "#1AC4933D"
        return "#1A6C8FA1"
    }
    border.color: {
        if (type === "success") return theme.statusSuccess
        if (type === "error") return theme.statusError
        if (type === "warning") return theme.statusWarning
        return theme.statusInfo
    }
    border.width: 1

    property string type: "info"
    property string message: ""

    RowLayout {
        anchors.fill: parent
        anchors.margins: 10
        spacing: 8
        Text {
            text: {
                if (root.type === "success") return "✅"
                if (root.type === "error") return "❌"
                if (root.type === "warning") return "⚠️"
                return "ℹ️"
            }
            font.pixelSize: 14
        }
        Text {
            text: root.message
            color: theme.textPrimary
            font.pixelSize: 12
            Layout.fillWidth: true
            wrapMode: Text.Wrap
        }
    }
}
