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
    // R8（SA §4.1 L-D v1.3 / §13，G2-delta-2）：产品级最小窗口 WIN_MIN = 1280×720
    // （Owner 2026-09-21 11:59 确认）；弹窗几何在 [WIN_MIN, ∞) 内夹取，窗口不可缩到此值以下。
    minimumWidth: 1280
    minimumHeight: 720
    title: "Eagle of Rome"
    color: "#14110D"

    GameShell {
        id: gameShell
        objectName: "gameShell"
        anchors.fill: parent
    }
}
