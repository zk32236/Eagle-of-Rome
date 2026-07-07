import QtQuick 2.15
import QtQuick.Controls 2.15
import QtQuick.Layouts 1.15

import "../i18n"

/**
 * ImpactDetail.qml — 天命影响详情组件
 * 用于 MortalityStage 显示死亡/灾害/英雄等事件影响
 */
Rectangle {
    id: root
    property var impactData: ({})

    implicitHeight: 20
    color: "transparent"

    RowLayout {
        anchors.fill: parent
        spacing: 4

        Rectangle {
            width: 4; height: 4; radius: 2
            color: theme.accentBronze
            Layout.alignment: Qt.AlignVCenter
        }

        Text {
            text: _formatImpact(root.impactData)
            color: theme.textMuted
            font.pixelSize: 10
            Layout.fillWidth: true
            wrapMode: Text.Wrap
        }
    }

    function _formatImpact(impact) {
        if (!impact) return ""
        if (impact.type === "figure_death") {
            var parts = []
            if (impact.figure_name) parts.push("死亡：" + impact.figure_name)
            if (impact.faction_name) parts.push("派系：" + impact.faction_name)
            if (impact.land_lost !== undefined) parts.push("损失土地 " + impact.land_lost + " C（收归国库）")
            if (impact.wealth_lost !== undefined) parts.push("损失财富 " + impact.wealth_lost + " T（收归国库）")
            return parts.join(" · ")
        }
        if (impact.type === "active_event") {
            return "本回合事件：" + (impact.key || "")
        }
        if (impact.type === "province_grievance") {
            return "民怨：" + (impact.province_name || impact.province_id || "") + " " + impact.old + "→" + impact.new
        }
        if (impact.type === "war_threat") {
            return "战争威胁：" + (impact.war_name || impact.war_id || "") + " " + impact.old + "→" + impact.new
        }
        if (impact.type === "hero_spawn") {
            return "英雄登场：" + (impact.name || "随机猛人")
        }
        if (impact.type === "disaster") {
            return "灾害：" + (impact.province_name || impact.province_id || "") + " 损失 " + (impact.loss_ratio !== undefined ? Math.round(impact.loss_ratio * 100) + "%" : "")
        }
        return (impact.name || impact.type || "")
    }
}
