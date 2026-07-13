import QtQuick 2.15
import QtQuick.Controls 2.15

/*!
 * PhaseRailIcon — v3.25.1 Codex v4.0 (§3 B)
 *
 * Layout contract: GUI_LAYOUT_CONTRACT_Phase1_v3.25.1.md §3.1
 *   Size: 74×54px, border-radius: 10px (pill shape)
 *   Column layout with icon + always-visible label
 *   Done:   gradient rgba(79,139,87,.70) → rgba(55,95,60,.72), text #F5EAD2
 *   Current: gradient #EFD27D → #D2A144, text #2C1E12, gold border + shadow
 *   Todo:   rgba(255,255,255,.055), text #877663, subtle border
 *   Hover:  translateY(-1px)
 *
 * Skeleton stage: only anchors, colors, layout. No business logic.
 */
Item {
    id: root

    property string iconText: ""
    property string label: ""
    property string state: "todo"   // "done" | "current" | "todo"
    signal clicked()

    width: 74
    height: 60

    // The pill
    Rectangle {
        id: pill
        anchors.centerIn: parent
        width: 74
        height: 60
        radius: 10
        border.width: root.state === "current" ? 2 : 1
        border.color: root.state === "current" ? "#F2D590" : "#33D9AF63"

        // Background gradient based on state
        gradient: Gradient {
            orientation: Gradient.Vertical
            GradientStop { position: 0.0; color: root.state === "done" ? "#B34F8B57" : root.state === "current" ? "#EFD27D" : "transparent" }
            GradientStop { position: 1.0; color: root.state === "done" ? "#B8375F3C" : root.state === "current" ? "#D2A144" : "transparent" }
        }
        color: root.state === "todo" ? "#0EFFFFFF" : "transparent"

        // Box shadow for current state (via outer glow rectangle)
        Rectangle {
            anchors.fill: parent
            anchors.margins: -6
            radius: 14
            visible: root.state === "current"
            color: "transparent"
            border.width: 3
            border.color: "#1FD9AF63"
            z: -1
        }

        // Column: icon + label
        Column {
            anchors.centerIn: parent
            spacing: 2

            // Icon (emoji)
            Text {
                anchors.horizontalCenter: parent.horizontalCenter
                text: root.iconText
                font.pixelSize: 16  // ~1rem
                color: {
                    if (root.state === "done") return "#F5EAD2"
                    if (root.state === "current") return "#2C1E12"
                    return "#877663"
                }
            }

            // Label (always visible)
            Text {
                anchors.horizontalCenter: parent.horizontalCenter
                text: root.label
                font.pixelSize: 11  // ~0.68rem
                color: {
                    if (root.state === "done") return "#F5EAD2"
                    if (root.state === "current") return "#2C1E12"
                    return "#877663"
                }
            }
        }

        MouseArea {
            id: mouseArea
            anchors.fill: parent
            hoverEnabled: true
            cursorShape: Qt.PointingHandCursor

            onEntered: {
                parent.anchors.verticalCenterOffset = -1
            }
            onExited: {
                parent.anchors.verticalCenterOffset = 0
            }
            onClicked: root.clicked()
        }
    }

    // Hover animation
    Behavior on scale {
        NumberAnimation { duration: 140 }
    }
}
