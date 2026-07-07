import QtQuick 2.15
import QtQuick.Controls 2.15
import QtQuick.Layouts 1.15

import "../i18n"

/**
 * SenateReadOnlySection.qml — 只读信息区块组件
 * 用于元老院只读模式，展示各类列表信息
 */
Rectangle {
    id: root
    property string title: ""
    property var items: []

    Layout.fillWidth: true
    height: column.implicitHeight + 22
    color: theme.bgSurface1
    border.color: theme.borderNormal
    border.width: 1
    radius: theme.radius

    ColumnLayout {
        id: column
        anchors.left: parent.left; anchors.right: parent.right
        anchors.margins: 12; anchors.verticalCenter: parent.verticalCenter
        spacing: 8

        Text {
            text: root.title
            color: theme.textPrimary
            font.pixelSize: 13; font.bold: true
            Layout.fillWidth: true
        }

        Text {
            visible: !root.items || root.items.length === 0
            text: "暂无数据"
            color: theme.textMuted; font.pixelSize: 11
        }

        Repeater {
            model: root.items || []
            delegate: ColumnLayout {
                Layout.fillWidth: true; spacing: 2
                Text {
                    text: {
                        var item = modelData
                        return item.name || item.leader_name || item.province_name
                               || item.enemy_name || item.contract_id || ""
                    }
                    color: theme.accentBronze; font.pixelSize: 12; font.bold: true
                    Layout.fillWidth: true; wrapMode: Text.Wrap
                }
                Text {
                    text: {
                        var item = modelData
                        if (item.faction_name) return item.faction_name + " 影响力:" + (item.influence || "-")
                        if (item.threat_level !== undefined) return "威胁等级:" + item.threat_level
                        if (item.indemnity !== undefined) return "赔款:" + item.indemnity + " 期限:" + (item.duration || "-")
                        if (item.governor_type_name) return item.governor_type_name
                        if (item.base_cost !== undefined) return "预算:" + item.base_cost + " 预期收益:" + (item.expected_profit || "-")
                        return item.status || item.type || ""
                    }
                    color: theme.textSecondary; font.pixelSize: 10
                    Layout.fillWidth: true; wrapMode: Text.Wrap
                }
            }
        }
    }
}
