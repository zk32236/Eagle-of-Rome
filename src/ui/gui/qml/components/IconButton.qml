import QtQuick 2.15
import QtQuick.Controls 2.15


Rectangle {
    id: root
    width: 32
    height: 32
    radius: 4
    color: mouseArea.containsPress ? theme.bgSurface3 : (mouseArea.containsMouse ? theme.bgSurface2 : "transparent")

    property string icon: ""
    property string tooltip: ""

    signal clicked

    Text {
        anchors.centerIn: parent
        text: root.icon
        font.pixelSize: 16
    }

    MouseArea {
        id: mouseArea
        anchors.fill: parent
        hoverEnabled: true
        onClicked: root.clicked()
    }
}
