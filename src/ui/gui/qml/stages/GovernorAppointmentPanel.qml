import QtQuick 2.15
import QtQuick.Controls 2.15
import QtQuick.Layouts 1.15

import "../i18n"

/**
 * S5 — 总督任命面板
 *
 * 按 G2 布局契约实现，展示元老院阶段总督任命信息。
 * S4 确认自动分配 (assign_governors)，本面板为信息展示 + 结果确认。
 *
 * 数据状态：
 * - 正常态: 有待分配行省 + 有合法候选人
 * - 空态1: 所有行省已有候任总督
 * - 空态2: 无合法候选人
 * - 完成态: 总督任命已提交
 *
 * 数据源: sessionStore.governorAppointments (从 senate_view.governor_appointments DTO 映射)
 */
Rectangle {
    id: root
    color: "#FFF7E9"
    border.color: appointments.submitted ? "#2E9D4D" : "#D9AF63"
    border.width: 1
    radius: 6
    clip: true
    visible: true

    property var appointments: sessionStore.governorAppointments || {}
    property var pendingProvinces: appointments.pending_provinces || []
    property var completedProvinces: appointments.completed_provinces || []
    property bool canSubmit: appointments.can_submit || false
    property bool submitted: appointments.submitted || false
    property bool isEmpty: pendingProvinces.length === 0 && completedProvinces.length === 0
    property bool hasNoCandidates: pendingProvinces.length > 0 && (function() {
        for (var i = 0; i < pendingProvinces.length; i++) {
            if ((pendingProvinces[i].candidates || []).length > 0) return false
        }
        return true
    })()

    // 标题栏
    Rectangle {
        id: titleBar
        anchors.left: parent.left
        anchors.right: parent.right
        anchors.top: parent.top
        height: 36
        color: submitted ? "#1E7A3D" : "#8F2506"

        Text {
            anchors.verticalCenter: parent.verticalCenter
            anchors.left: parent.left
            anchors.leftMargin: 10
            text: submitted ? "\u2705 总督任命 \u2014 已提交" : "\U0001F3DB\uFE0F 总督任命"  // ✅已提交 / 🏛️总督任命
            color: "white"
            font.pixelSize: 13
            font.bold: true
        }
    }

    // 内容区域
    ColumnLayout {
        anchors.fill: parent
        anchors.topMargin: 44
        anchors.margins: 10
        spacing: 6

        // === 完成态 ===
        Text {
            visible: submitted && pendingProvinces.length === 0
            text: "\u2705 总督任命已提交，所有行省已分配候任总督"  // ✅ 所有行省已分配候任总督
            color: "#2E9D4D"
            font.pixelSize: 12
            font.bold: true
            Layout.fillWidth: true
            wrapMode: Text.Wrap
        }

        // === 空态1：所有已分配 ===
        Text {
            visible: !submitted && pendingProvinces.length === 0 && completedProvinces.length > 0
            text: "\u2705 所有行省已分配总督"
            color: "#766652"
            font.pixelSize: 12
            font.bold: true
            Layout.fillWidth: true
            wrapMode: Text.Wrap
        }

        // === 空态2：无合法候选人 ===
        Text {
            visible: !submitted && hasNoCandidates && pendingProvinces.length > 0
            text: "\u26A0\uFE0F 当前无合法候选人"
            color: "#D9AA52"
            font.pixelSize: 12
            font.bold: true
            Layout.fillWidth: true
            wrapMode: Text.Wrap
        }

        // === 完全空态 ===
        Text {
            visible: isEmpty
            text: "\u2139\uFE0F 暂无行省信息"  // ℹ️ 暂无行省信息
            color: "#766652"
            font.pixelSize: 12
            Layout.fillWidth: true
            wrapMode: Text.Wrap
        }

        // === 已完成行省列表 ===
        ColumnLayout {
            visible: completedProvinces.length > 0
            Layout.fillWidth: true
            spacing: 4

            Repeater {
                model: completedProvinces
                delegate: Rectangle {
                    Layout.fillWidth: true
                    height: 34
                    radius: 3
                    color: "#F0F9F0"
                    border.color: "#C8E6C9"
                    border.width: 1
                    RowLayout {
                        anchors.fill: parent
                        anchors.margins: 8
                        spacing: 6
                        Text {
                            text: "\u2705"
                            color: "#2E9D4D"
                            font.pixelSize: 12
                        }
                        ColumnLayout {
                            Layout.fillWidth: true
                            spacing: 1
                            Text {
                                text: modelData.name || ""
                                color: "#2C1E12"
                                font.pixelSize: 12
                                font.bold: true
                                elide: Text.ElideRight
                            }
                            Text {
                                text: (modelData.designated_governor || "") + " \u00B7 " + (modelData.governor_type_name || modelData.governor_type || "")
                                color: "#766652"
                                font.pixelSize: 10
                                elide: Text.ElideRight
                            }
                        }
                    }
                }
            }
        }

        // === 待分配行省列表 ===
        ScrollView {
            visible: pendingProvinces.length > 0 && !submitted
            Layout.fillWidth: true
            Layout.fillHeight: true
            clip: true
            contentWidth: availableWidth

            ColumnLayout {
                width: parent.width
                spacing: 6

                Repeater {
                    model: pendingProvinces
                    delegate: Rectangle {
                        Layout.fillWidth: true
                        height: 48
                        radius: 4
                        color: (modelData.candidates || []).length === 0 ? "#FFF6E6" : "#FFF6E6"
                        border.color: "#E0B56C"
                        border.width: 1

                        RowLayout {
                            anchors.fill: parent
                            anchors.margins: 8
                            spacing: 6

                            // 行省名称 + 类型
                            ColumnLayout {
                                Layout.preferredWidth: parent.width * 0.35
                                Layout.maximumWidth: 180
                                spacing: 1

                                Text {
                                    text: modelData.name || ""
                                    color: "#2C1E12"
                                    font.pixelSize: 12
                                    font.bold: true
                                    elide: Text.ElideRight
                                    Layout.fillWidth: true
                                }

                                Text {
                                    text: (modelData.governor_type_name || modelData.governor_type || "")
                                        + (modelData.current_governor ? " \u00B7 \u5F53\u524D:" + modelData.current_governor.name : "")
                                    color: "#766652"
                                    font.pixelSize: 10
                                    elide: Text.ElideRight
                                    Layout.fillWidth: true
                                }
                            }

                            // 候选人下拉 / 无候选人提示
                            Rectangle {
                                Layout.fillWidth: true
                                Layout.preferredHeight: 24
                                radius: 3
                                color: (modelData.candidates || []).length === 0 ? "#FDECD4" : "#FFF7E9"
                                border.color: (modelData.candidates || []).length === 0 ? "#E6A542" : "#D9AF63"
                                border.width: 1

                                Text {
                                    anchors.centerIn: parent
                                    text: (modelData.candidates || []).length === 0
                                          ? "\u26A0\uFE0F 无可用候选人"
                                          : (modelData.candidates || []).map(function(c) { return c.name + " (" + (c.faction_name || c.faction_id) + ")" }).join(" \u3001")
                                    color: (modelData.candidates || []).length === 0 ? "#9A2D0A" : "#2C1E12"
                                    font.pixelSize: 11
                                    elide: Text.ElideRight
                                    leftPadding: 5
                                    rightPadding: 5
                                    Layout.fillWidth: true
                                }
                            }

                            // 状态指示
                            Text {
                                text: (modelData.candidates || []).length > 0 ? "\u23F3 \u7B49\u5F85\u63D0\u4EA4" : ""  // ⏳ 等待提交
                                color: "#766652"
                                font.pixelSize: 10
                                visible: (modelData.candidates || []).length > 0
                            }
                        }
                    }
                }
            }
        }

        // === 提交所有任命按钮（显示，但 S4 自动分配故已禁用）===
        Rectangle {
            Layout.fillWidth: true
            Layout.preferredHeight: 26
            radius: 4
            enabled: canSubmit && !submitted
            opacity: enabled ? 1.0 : 0.45
            visible: false  // S4 自动分配，隐藏提交按钮
            gradient: Gradient {
                GradientStop { position: 0.0; color: enabled ? "#D9AA52" : "#D8B16C" }
                GradientStop { position: 1.0; color: enabled ? "#BC7B28" : "#D8B16C" }
            }
            Text {
                anchors.centerIn: parent
                text: "\U0001F4E8 提交所有任命"  // 📨
                color: "#2C1E12"
                font.pixelSize: 12
                font.bold: true
            }
            MouseArea {
                anchors.fill: parent
                enabled: parent.enabled
                onClicked: {
                    // S4 自动分配，当前无需手动提交
                    console.log("S5: Governor appointment submit is automatic via S4 resolve_senate")
                }
            }
        }

        // === 跳过按钮（显示，但 S4 自动分配故已禁用）===
        Rectangle {
            Layout.fillWidth: true
            Layout.preferredHeight: 24
            radius: 4
            opacity: 0.45
            visible: false  // S4 自动分配，跳过操作不适用
            color: "#D8B16C"
            Text {
                anchors.centerIn: parent
                text: "跳过此操作（进入其他提案）"
                color: "#60411E"
                font.pixelSize: 11
            }
        }
    }
}
