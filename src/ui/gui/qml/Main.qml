import QtQuick 2.15
import QtQuick.Window 2.15

import "shell"

/*!
 * Main.qml — v3.25.1 Codex v4.0 visual baseline
 * Viewport: 1440x900, deep-ink shell (#14110D)
 * See GUI_LAYOUT_CONTRACT_Phase1_v3.25.1.md
 */
Window {
    id: mainWindow
    visible: true
    width: 1440
    height: 900
    title: "Eagle of Rome"
    color: "#14110D"

    GameShell {
        id: gameShell
        objectName: "gameShell"
        anchors.fill: parent
    }
}
