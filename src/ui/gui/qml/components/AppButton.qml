import QtQuick 2.15
import QtQuick.Controls 2.15
import QtQuick.Layouts 1.15


Rectangle {
    id: root
    height: 36
    radius: theme.radius
    color: {
        if (type === "primary") return theme.accentPrimary
        if (type === "secondary") return theme.bgSurface2
        if (type === "danger") return theme.statusError
        return "transparent"
    }
    border.color: {
        if (type === "primary") return theme.accentPrimaryDark
        if (type === "secondary") return theme.borderNormal
        if (type === "danger") return theme.statusError
        return "transparent"
    }
    border.width: type === "ghost" ? 0 : 1

    property string text: ""
    property string type: "primary"  // primary | secondary | danger | ghost
    property int fontSize: 12
    property bool enabled: true

    signal clicked

    Text {
        anchors.centerIn: parent
        text: root.text
        color: root.type === "primary" ? "white" : (root.type === "danger" ? "white" : theme.textPrimary)
        font.pixelSize: root.fontSize
        font.bold: root.type === "primary"
    }

    MouseArea {
        anchors.fill: parent
        enabled: root.enabled
        onClicked: root.clicked()
    }

    states: [
        State {
            when: !root.enabled
            PropertyChanges { target: root; opacity: 0.5 }
        }
    ]
}
