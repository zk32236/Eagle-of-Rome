import QtQuick 2.15
import QtQuick.Window 2.15

import "shell"

Window {
    id: mainWindow
    visible: true
    width: 1440
    height: 900
    title: "Eagle of Rome"
    color: "#121512"

    GameShell {
        id: gameShell
        objectName: "gameShell"
        anchors.fill: parent
    }
}
