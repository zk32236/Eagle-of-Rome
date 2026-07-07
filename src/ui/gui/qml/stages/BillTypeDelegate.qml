import QtQuick 2.15
import QtQuick.Controls 2.15
import QtQuick.Layouts 1.15

import "../i18n"

/**
 * BillTypeDelegate.qml — 法案类型配置代理
 * 用于元老院阶段子环节1，展示8种法案的参数配置界面
 */
Rectangle {
    id: root
    property var billData: ({})
    property string subStep: "proposal"
    property bool canAct: true
    signal addRequested(string type, var params)

    color: _expanded ? theme.bgSurface3 : "transparent"
    border.color: _expanded ? theme.accentPrimary : "transparent"
    border.width: _expanded ? 1 : 0
    radius: 4
    clip: true

    property bool _expanded: false
    property var _params: ({})

    function resetConfig() {
        _params = {}
        var type = billData.type || ""
        if (type === "war") { _params = { legions: 4, war_id: "" } }
        else if (type === "peace") { _params = { war_id: "" } }
        else if (type === "governor") { _params = { province_id: "", candidate_id: 0 } }
        else if (type === "budget") { _params = { amount: 50 } }
        else if (type === "tax") { _params = { amount: 50 } }
        else if (type === "sell_land") { _params = { percent: 10 } }
        else if (type === "grant_land") { _params = { percent: 10 } }
        else if (type === "takeover_war") { _params = { war_id: "" } }
    }

    function setParam(key, value) {
        var p = _params
        p[key] = value
        _params = p
    }

    function billTypeLabel(type) {
        var map = {
            "war": "⚔️ 宣战", "peace": "☮️ 停战", "governor": "🏛️ 总督任命",
            "budget": "💰 建造合同", "tax": "📜 包税合同",
            "sell_land": "🏡 卖地法案", "grant_land": "🌾 分地法案",
            "takeover_war": "🛡️ 接管战争"
        }
        return map[type] || type
    }

    ColumnLayout {
        anchors.fill: parent; anchors.margins: 4
        spacing: 2

        // 标题行（点击展开/收起）
        RowLayout {
            Layout.fillWidth: true
            Layout.preferredHeight: 22
            spacing: 4

            Text {
                text: root._expanded ? "▾" : "▸"
                color: theme.accentBronze; font.pixelSize: 10
            }
            Text {
                text: root.billTypeLabel(billData.type || billData.label || "")
                color: theme.textPrimary; font.pixelSize: 10; font.bold: true
                Layout.fillWidth: true; elide: Text.ElideRight
            }
            Text {
                text: billData.description || ""
                color: theme.textMuted; font.pixelSize: 9
                Layout.maximumWidth: 60; elide: Text.ElideRight
                visible: !root._expanded
            }

            Button {
                text: root._expanded ? "收起" : "➕ 配置"
                implicitWidth: 50; implicitHeight: 20
                visible: canAct && subStep === "proposal"
                contentItem: Text {
                    text: parent.text; color: "white"; font.pixelSize: 9
                    horizontalAlignment: Text.AlignHCenter
                }
                background: Rectangle {
                    color: root._expanded ? theme.bgSurface3 : "#8B2500"; radius: 3
                }
                onClicked: {
                    if (!root._expanded) root.resetConfig()
                    root._expanded = !root._expanded
                }
            }
        }

        // 展开配置区
        ColumnLayout {
            Layout.fillWidth: true
            Layout.preferredHeight: root._expanded && root.billData ? _configHeight() : 0
            visible: root._expanded
            spacing: 3
            Layout.leftMargin: 10

            function _configHeight() {
                var type = billData.type || billData.label || ""
                if (type === "war" || type === "governor" || type === "takeover_war") return 90
                if (type === "peace") return 60
                return 70
            }

            Loader {
                Layout.fillWidth: true; Layout.fillHeight: true
                sourceComponent: {
                    var type = billData.type || billData.label || ""
                    if (type === "war") return warConfig
                    if (type === "peace") return peaceConfig
                    if (type === "governor") return governorConfig
                    if (type === "budget") return sliderConfig
                    if (type === "tax") return sliderConfig
                    if (type === "sell_land") return sliderConfig
                    if (type === "grant_land") return sliderConfig
                    if (type === "takeover_war") return takeoverWarConfig
                    return defaultConfig
                }
                property var params: root._params
                property string billType: billData.type || billData.label || ""
            }
        }

        // 添加到提案按钮
        Button {
            Layout.fillWidth: true
            text: "添加到提案"
            visible: root._expanded && canAct && subStep === "proposal"
            implicitHeight: 22
            contentItem: Text {
                text: parent.text; color: "white"; font.pixelSize: 9
                horizontalAlignment: Text.AlignHCenter
            }
            background: Rectangle {
                color: theme.accentPrimary; radius: 3
            }
            onClicked: {
                root.addRequested(billData.type || billData.label || "", root._params)
                root._expanded = false
            }
        }
    }

    // ── 宣战配置 ──
    Component {
        id: warConfig
        ColumnLayout {
            spacing: 3
            Text { text: "选择宣战目标："; color: theme.textSecondary; font.pixelSize: 9 }
            ComboBox {
                Layout.fillWidth: true
                model: {
                    var data = sessionStore.senateAvailableWars || {}
                    var threats = data.threats || []
                    var names = threats.map(function(t) { return t.enemy_name || t.name || "未知" })
                    return names.length > 0 ? names : ["暂无可用宣战目标"]
                }
                onCurrentTextChanged: root.setParam("threat_id", currentText)
            }
            Text { text: "征召军团数量："; color: theme.textSecondary; font.pixelSize: 9 }
            ComboBox {
                Layout.fillWidth: true
                model: ["2", "3", "4", "5", "6", "7", "8", "9", "10"]
                currentIndex: 2
                onCurrentTextChanged: root.setParam("legions", parseInt(currentText))
            }
        }
    }

    // ── 停战配置（只读展示） ──
    Component {
        id: peaceConfig
        ColumnLayout {
            spacing: 3
            Text { text: "选择停战条约："; color: theme.textSecondary; font.pixelSize: 9 }
            ComboBox {
                Layout.fillWidth: true
                model: {
                    var treaties = sessionStore.senatePendingPeaceTreaties || []
                    var names = treaties.map(function(t) { return t.name || t.title || "条约#" + t.id })
                    return names.length > 0 ? names : ["暂无待批和约"]
                }
                onCurrentTextChanged: root.setParam("treaty_id", currentText)
            }
            Rectangle {
                Layout.fillWidth: true; height: 20
                color: theme.bgSurface2; radius: 3
                Text {
                    anchors.fill: parent; anchors.margins: 4
                    text: "选中条约后展示条款细节"
                    color: theme.textMuted; font.pixelSize: 9
                    verticalAlignment: Text.AlignVCenter
                }
            }
        }
    }

    // ── 总督任命配置 ──
    Component {
        id: governorConfig
        ColumnLayout {
            spacing: 3
            Text { text: "选择行省："; color: theme.textSecondary; font.pixelSize: 9 }
            ComboBox {
                Layout.fillWidth: true
                model: {
                    var vacancies = sessionStore.senateGovernorVacancies || []
                    var names = vacancies.map(function(v) {
                        return v.province_name || v.name || "行省#" + v.governor_type
                    })
                    return names.length > 0 ? names : ["暂无空缺行省"]
                }
                onCurrentTextChanged: root.setParam("province", currentText)
            }
            Text { text: "提名人选："; color: theme.textSecondary; font.pixelSize: 9 }
            ComboBox {
                Layout.fillWidth: true
                model: {
                    var candidates = sessionStore.senateGovernorCandidates || []
                    var names = candidates.map(function(c) { return c.name || "人物#" + c.figure_id })
                    return names.length > 0 ? names : ["暂无合格候选人"]
                }
                onCurrentTextChanged: root.setParam("candidate_id", currentText)
            }
        }
    }

    // ── 滑块配置（通用：建造/包税/卖地/分地） ──
    Component {
        id: sliderConfig
        ColumnLayout {
            spacing: 3
            Text {
                text: {
                    var type = root.billData.type || ""
                    if (type === "budget" || type === "tax") return "合同金额：" + (root._params.amount || 50) + " T"
                    if (type === "sell_land") return "出售公地：" + (root._params.percent || 10) + "%"
                    if (type === "grant_land") return "分配公地：" + (root._params.percent || 10) + "%"
                    return ""
                }
                color: theme.accentBronze; font.pixelSize: 10; font.bold: true
            }
            Slider {
                Layout.fillWidth: true
                from: 5
                to: { var t = root.billData.type || ""; return (t === "budget" || t === "tax") ? 200 : 50 }
                stepSize: { var t = root.billData.type || ""; return (t === "budget" || t === "tax") ? 5 : 1 }
                value: { var t = root.billData.type || ""; return (t === "budget" || t === "tax") ? 50 : 10 }
                onValueChanged: {
                    var t = root.billData.type || ""
                    if (t === "budget" || t === "tax") root.setParam("amount", value)
                    else root.setParam("percent", value)
                }
            }
            Text {
                text: {
                    var type = root.billData.type || ""
                    if (type === "budget" || type === "tax") return "国库参考：" + (sessionStore.treasury || 0) + " T"
                    if (type === "sell_land" || type === "grant_land") return "公地参考：" + (sessionStore.publicLand || 0) + " C"
                    return ""
                }
                color: theme.textMuted; font.pixelSize: 9
            }
        }
    }

    // ── 接管战争配置 ──
    Component {
        id: takeoverWarConfig
        ColumnLayout {
            spacing: 3
            Rectangle {
                Layout.fillWidth: true; height: 20
                color: "#1AFFD700"; radius: 3
                Text {
                    anchors.centerIn: parent
                    text: "⚡ 绕过元老院和保民官，提交即执行"
                    color: "#FFD700"; font.pixelSize: 9; font.bold: true
                }
            }
            Text { text: "选择要接管的战争："; color: theme.textSecondary; font.pixelSize: 9 }
            ComboBox {
                Layout.fillWidth: true
                model: {
                    var wars = sessionStore.senateActiveForeignWars || []
                    var names = wars.map(function(w) { return w.name || w.title || "战争#" + w.id })
                    return names.length > 0 ? names : ["暂无活跃战争"]
                }
                onCurrentTextChanged: root.setParam("war_id", currentText)
            }
            Text {
                text: "※ 接管后战争指挥权转移至本派系"
                color: theme.statusWarning; font.pixelSize: 9
            }
        }
    }

    Component {
        id: defaultConfig
        ColumnLayout {
            Text {
                text: "配置界面加载中…"
                color: theme.textMuted; font.pixelSize: 9
            }
        }
    }
}
