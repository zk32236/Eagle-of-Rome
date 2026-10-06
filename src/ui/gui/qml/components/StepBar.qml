import QtQuick 2.15
import QtQuick.Controls 2.15
import QtQuick.Layouts 1.15

import "../i18n"

/**
 * StepBar — 通用水平步骤引导条（WP-J J-AC-10 升级：唯一渲染 owner）
 *
 * 消费**权威**步骤模型：`steps: [ {key, label, state} ]`（由各阶段 `get_*_view().steps` 产出，
 * 经 `sessionStore.phaseSteps` 透传）。QML 只逐字渲染，零业务重建（FC-08）。
 *
 * 四态（FC-03；Owner 决策 ③ 统一）：
 *   - complete       绿 #228B22 + 白 ✓
 *   - current        金 #E8B84B + 暗字编号（粗体标签）
 *   - todo           灰 #E8D5C4 + 灰字编号
 *   - not_applicable 冷淡 #E8D5C4 + 无编号/✓（muted）
 *
 * 不渲染任何非步骤节点（FC-06 公示区不入步骤条）。
 *
 * WP-J Group-A R1 / FC-14（J-AC-12）：节点条**内容紧凑左对齐**（去 right 锚，禁拉伸铺满），
 * 节点间 = 固定 `gapStep = 7px`（唯一权威 = Product GUI Layout Contract Phase1 v3.25.1 §4.2
 * 「StageInstructionSlot (Step Bar): Gap 7px」）；余量 = 右侧留白。几何视口无关
 * （1280×720 == 1440×900 == 7）。
 */
Item {
    id: root

    property var steps: []

    // FC-14：节点间固定间距（契约值；禁自选近似值）。
    readonly property int gapStep: 7

    implicitHeight: 32
    implicitWidth: childrenRect.width

    function _stepState(step) {
        if (step && step.state) return step.state
        return "todo"
    }

    // FC-14：内容紧凑左对齐（仅锚 left + verticalCenter；**去 right 锚** → 不吸收剩余空间）。
    RowLayout {
        id: stepRow
        anchors.left: parent.left
        anchors.verticalCenter: parent.verticalCenter
        spacing: root.gapStep

        Repeater {
            model: root.steps

            RowLayout {
                id: stepItem
                objectName: "stepNode"
                spacing: 4
                Layout.fillHeight: true
                // FC-14：节点 = 不可拉伸单元（内容宽；余量落右侧留白）。
                Layout.fillWidth: false

                readonly property string stepState: root._stepState(modelData)
                readonly property bool isComplete: stepState === "complete"
                readonly property bool isCurrent: stepState === "current"
                readonly property bool isNotApplicable: stepState === "not_applicable"

                // Step circle
                Rectangle {
                    width: 18
                    height: 18
                    radius: 9
                    color: stepItem.isComplete ? "#228B22"
                         : stepItem.isCurrent ? "#E8B84B"
                         : "#E8D5C4"

                    Text {
                        anchors.centerIn: parent
                        visible: !stepItem.isNotApplicable
                        text: stepItem.isNotApplicable ? "" : (stepItem.isComplete ? "✓" : (index + 1))
                        color: stepItem.isComplete ? "#FFFFFF"
                             : stepItem.isCurrent ? "#3A3530"
                             : "#999999"
                        font.pixelSize: 10
                        font.bold: true
                    }
                }

                // Step text
                Text {
                    text: (modelData && modelData.label) ? modelData.label : ""
                    color: stepItem.isCurrent ? "#8B2500"
                         : stepItem.isComplete ? "#3A3530"
                         : stepItem.isNotApplicable ? "#999999"
                         : "#8B7355"
                    font.pixelSize: 11
                    font.bold: stepItem.isCurrent
                    verticalAlignment: Text.AlignVCenter
                    elide: Text.ElideRight
                    Layout.maximumWidth: 260
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
