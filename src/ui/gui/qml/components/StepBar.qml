import QtQuick 2.15
import QtQuick.Controls 2.15
import QtQuick.Layouts 1.15

import "../i18n"

/**
 * StepBar — 通用水平步骤引导条 (§2.7)
 *
 * EXACT step circle colors:
 *   .sn.done:    #228B22 (success green), white text
 *   .sn.current: #E8B84B (gold), dark text
 *   .sn.todo:    #E8D5C4 (light gray), gray text
 *
 * Usage:
 *   StepBar {
 *       steps: ["⚡ 执行天命", "📜 查看事件结果"]
 *       currentStep: 0
 *   }
 */
Item {
    id: root

    property var steps: []
    property int currentStep: 0
    property int doneSteps: currentStep

    implicitHeight: 32
    implicitWidth: childrenRect.width

    RowLayout {
        id: stepRow
        anchors.left: parent.left
        anchors.right: parent.right
        anchors.verticalCenter: parent.verticalCenter
        spacing: 4

        Repeater {
            model: root.steps

            RowLayout {
                id: stepItem
                spacing: 4
                Layout.fillHeight: true

                // Step circle
                Rectangle {
                    width: 18
                    height: 18
                    radius: 9
                    color: {
                        if (index < root.doneSteps) return "#228B22"
                        if (index === root.currentStep) return "#E8B84B"
                        return "#E8D5C4"
                    }

                    Text {
                        anchors.centerIn: parent
                        text: index < root.doneSteps ? "✓" : (index + 1)
                        color: {
                            if (index < root.doneSteps) return "#FFFFFF"
                            if (index === root.currentStep) return "#3A3530"
                            return "#999999"
                        }
                        font.pixelSize: 10
                        font.bold: true
                    }
                }

                // Step text
                Text {
                    text: modelData || ""
                    color: {
                        if (index === root.currentStep) return "#8B2500"
                        if (index < root.doneSteps) return "#3A3530"
                        return "#8B7355"
                    }
                    font.pixelSize: 11
                    font.bold: index === root.currentStep
                    verticalAlignment: Text.AlignVCenter
                    Layout.fillHeight: true
                }

                // Arrow (except last)
                Text {
                    visible: index < root.steps.length - 1
                    text: "→"
                    color: "#B8A080"
                    font.pixelSize: 11
                    Layout.alignment: Qt.AlignVCenter
                    Layout.leftMargin: 2
                    Layout.rightMargin: 2
                }
            }
        }
    }
}
