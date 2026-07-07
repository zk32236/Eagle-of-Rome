import QtQuick 2.15
import QtQuick.Controls 2.15
import QtQuick.Layouts 1.15

import "../components"
import "../i18n"

/**
 * PhaseRail.qml — 左侧阶段导航图标栏
 * 缩窄为 emoji 图标 + tooltip，与 V3.23 原型对齐
 */
Rectangle {
    id: root
    color: theme.bgSurface1
    border.color: theme.borderNormal
    border.width: 1

    // 阶段图标映射
    function phaseIcon(phaseId) {
        var map = {
            "mortality": "⚡",    // 天命
            "revenue": "💰",     // 收入
            "forum": "📢",       // 广场
            "population": "🗳️",  // 人口
            "senate": "🏛️",     // 元老院
            "war": "⚔️",        // 战争
            "resolution": "📜"   // 决算
        }
        return map[phaseId] || "•"
    }

    ColumnLayout {
        anchors.fill: parent
        anchors.margins: 4
        spacing: 2

        // 顶部留白
        Item { Layout.preferredHeight: 4 }

        Repeater {
            model: sessionStore.phaseNavigation || []
            delegate: Rectangle {
                id: phaseItem
                objectName: "phaseNavItem_" + modelData.id
                Layout.fillWidth: true
                Layout.preferredHeight: 44
                color: "transparent"

                // 圆形阶段按钮（Phase-2 §5：all phase buttons are circular；Phase-4 §4.2：活跃态降重）
                Rectangle {
                    id: phaseCircle
                    anchors.centerIn: parent
                    width: 36; height: 36; radius: 18
                    color: isActive ? "#8B2500" : "transparent"
                    border.color: isActive ? "#E8A030" :
                                   modelData.implemented ? theme.borderNormal : "transparent"
                    border.width: isActive ? 1.5 : (modelData.implemented ? 1 : 0)

                    property bool isActive: sessionStore.selectedPhaseId === modelData.id

                    Text {
                        anchors.centerIn: parent
                        text: root.phaseIcon(modelData.id)
                        font.pixelSize: 16
                        color: isActive ? "#FFD700" :
                               modelData.implemented ? theme.textPrimary : theme.textMuted
                    }

                    // 执行状态指示
                    Rectangle {
                        anchors.right: parent.right
                        anchors.bottom: parent.bottom
                        width: 8; height: 8; radius: 4
                        visible: modelData.executed && !modelData.current
                        color: theme.statusSuccess
                        border.color: theme.bgSurface1
                        border.width: 1
                    }
                }

                // Tooltip
                ToolTip {
                    visible: ma.containsMouse
                    text: modelData.name + (modelData.actionable ? "" : " (" + (modelData.handoff_task || "未开放") + ")")
                    delay: 600
                    font.pixelSize: 10
                }

                // Hover（鼠标悬停时轻微高亮圆形）
                MouseArea {
                    id: ma
                    anchors.fill: parent
                    hoverEnabled: true
                    onClicked: sessionStore.selectPhase(modelData.id)
                    cursorShape: Qt.PointingHandCursor
                    onEntered: {
                        if (!phaseCircle.isActive)
                            phaseCircle.color = theme.bgSurface2
                    }
                    onExited: {
                        if (!phaseCircle.isActive)
                            phaseCircle.color = "transparent"
                    }
                }
            }
        }

        // 弹性空间
        Item { Layout.fillHeight: true }

        // 底部留空（开发工具按钮已隐藏，对齐 Design 原型 Phase-2 §5）
    }
}
