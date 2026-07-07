import QtQuick 2.15
import QtQuick.Controls 2.15
import QtQuick.Layouts 1.15

import "../i18n"

/**
 * TopStatusBar.qml — Global info bar
 * Design V2.0 §1.1
 *
 * Shows: turn/treasury/public land/legion/fleet/province/living
 * Always visible, 56px height, deep red + gold text
 */
Rectangle {
    id: root
    color: "#8B2500"  // 深红底色
    height: 40

    RowLayout {
        anchors.fill: parent
        anchors.leftMargin: 16
        anchors.rightMargin: 16
        spacing: 10

        // ── 左：游戏标题（Phase-2 §4.1 / §21：增强 + SPQR）──
        Text {
            text: "🏛 EAGLE OF ROME · SPQR"
            color: "#FFD700"
            font.pixelSize: 13
            font.family: theme.fontTitle
            font.bold: true
            Layout.preferredWidth: 200
        }

        // 标题与指标之间弹性间距（Phase-4 §3.2：平衡分布）
        Item { Layout.minimumWidth: 12 }

        // ── 分隔线 ──
        Rectangle {
            width: 1; height: 22
            color: "#55FFD700"
            Layout.alignment: Qt.AlignVCenter
        }

        // ── 国库 ──
        RowLayout {
            spacing: 6
            Layout.alignment: Qt.AlignVCenter
            Text { text: "💰"; font.pixelSize: 12 }
            Text {
                text: (sessionStore.treasury || 0) + " 国库"
                color: "white"
                font.pixelSize: 10
                font.bold: true
            }
        }

        // ── 派系 ──
        RowLayout {
            spacing: 6
            Layout.alignment: Qt.AlignVCenter
            Text { text: "🛡"; font.pixelSize: 12 }
            Text {
                text: (sessionStore.viewerFactionCount || 12) + " 派系"
                color: "white"
                font.pixelSize: 10
                font.bold: true
            }
        }

        // ── 影响力 ──
        RowLayout {
            spacing: 6
            Layout.alignment: Qt.AlignVCenter
            Text { text: "⚖"; font.pixelSize: 12 }
            Text {
                text: (sessionStore.factionInfluence || 68) + " 影响力"
                color: "white"
                font.pixelSize: 10
                font.bold: true
            }
        }

        // ── 稳定度 ──
        RowLayout {
            spacing: 6
            Layout.alignment: Qt.AlignVCenter
            Text { text: "🏛"; font.pixelSize: 12 }
            Text {
                text: (sessionStore.stability || 78) + "% 稳定度"
                color: "white"
                font.pixelSize: 10
                font.bold: true
            }
        }

        // ── 战争 ──
        RowLayout {
            spacing: 6
            Layout.alignment: Qt.AlignVCenter
            Text { text: "⚔"; font.pixelSize: 12 }
            Text {
                text: (sessionStore.warCount || 0) + " 战争"
                color: "white"
                font.pixelSize: 10
                font.bold: true
            }
        }

        Item { Layout.fillWidth: true }

        // ── 分隔线 ──
        Rectangle {
            width: 1; height: 22
            color: "#55FFD700"
            Layout.alignment: Qt.AlignVCenter
        }

        // ── 回合/年份（RHS，Phase-2 §4.3）──
        RowLayout {
            spacing: 4
            Layout.alignment: Qt.AlignVCenter
            Text {
                text: (sessionStore.yearDisplay || "282 BC") + "  ·  回合 " + (sessionStore.turnNumber || 1)
                color: "#FFD9A0"
                font.pixelSize: 11
                font.bold: true
            }
        }
    }
}
