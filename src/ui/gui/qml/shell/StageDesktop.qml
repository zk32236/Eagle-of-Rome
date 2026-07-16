import QtQuick 2.15
import QtQuick.Controls 2.15
import QtQuick.Layouts 1.15

import "../stages"
import "../components"
import "../i18n"

/*!
 * \brief StageDesktop — v3.25.1 Codex v4.0 central ivory work surface (§4 C)
 *
 * Layout contract: GUI_LAYOUT_CONTRACT_Phase1_v3.25.1.md §4
 *   x=112, y=82, w=1022, h=736
 *   bg: linear-gradient(180deg, rgba(255,255,255,.36), rgba(232,223,207,.28)) on #F2EEE4
 *   border: 1px solid rgba(217,175,99,.46), radius: 10px
 *   padding: 18px
 *
 * Four named DA-fillable slots:
 *   StageHeaderSlot → StageInstructionSlot → StageContentSlot → StageActionSlot
 *
 * Skeleton stage: only slots, colors, layout. No business logic.
 */
Rectangle {
    id: root
    objectName: "centerPanel"
    color: "transparent"

    property bool compactActionSlot: false

    // Desktop background gradient
    Rectangle {
        anchors.fill: parent
        radius: theme.radius
        gradient: Gradient {
            orientation: Gradient.Vertical
            GradientStop { position: 0.0; color: "#5CFFFFFF" }   // rgba(255,255,255,.36)
            GradientStop { position: 1.0; color: "#47E8DFCF" }   // rgba(232,223,207,.28)
        }
        border.color: "#75D9AF63"  // rgba(217,175,99,.46)
        border.width: 1
    }

    // Ivory desk base
    Rectangle {
        anchors.fill: parent
        radius: theme.radius
        color: theme.ivoryDesk
        z: -1
    }

    ColumnLayout {
        anchors.fill: parent
        anchors.topMargin: 10
        anchors.leftMargin: 10
        anchors.rightMargin: 10
        anchors.bottomMargin: 18
        spacing: 10

        // ---- Slot 1: StageHeaderSlot — phase badge, title, description ----
        // H0.5 P1: fix hierarchy collapse. implicitHeight defaults to 0 on Item,
        // causing all anchors.fill content (badge+title+desc) to collapse to 0px.
        // Use explicit 80px to accommodate: badge(22) + 6spacing + title(~24) + 6spacing + desc(~18)
        Item {
            id: stageHeaderSlot
            objectName: "stageHeaderSlot"
            Layout.fillWidth: true
            Layout.preferredHeight: 80  // badge(22) + 6 + title(~24) + 6 + desc(~18)
        }

        // ---- Slot 2: StageInstructionSlot — step guide bar ----
        // H0.3: fix wrong property. ColumnLayout uses Layout.preferredHeight,
        // not the Item.height property. height: 32 was silently ignored by layout.
        Item {
            id: stageInstructionSlot
            objectName: "stageInstructionSlot"
            Layout.fillWidth: true
            Layout.preferredHeight: 50  // H0.5 P1: increased from 32; step bar needs ~38px (20px circles + 9px top padding + 9px bottom)
            visible: true  // H0: always visible; GameShell controls content visibility
        }

        // ---- Slot 3: StageContentSlot — phase-specific content area ----
        Item {
            id: stageContentSlot
            objectName: "stageContentSlot"
            Layout.fillWidth: true
            Layout.fillHeight: true
        }

        // ---- Slot 4: StageActionSlot — phase main action button ----
        Rectangle {
            id: stageActionSlot
            objectName: "stageActionSlot"
            Layout.fillWidth: true
            Layout.preferredHeight: root.compactActionSlot ? 0 : 46
            color: "transparent"
            visible: !root.compactActionSlot
        }
    }

    // ---- Backward-compat aliases for existing test expectations ----
    readonly property alias stageHeader: stageHeaderSlot
    readonly property alias stageInstruction: stageInstructionSlot
    readonly property alias stageContent: stageContentSlot
    readonly property alias stageAction: stageActionSlot
}
