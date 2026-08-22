import QtQuick 2.15
import QtQuick.Controls 2.15
import QtQuick.Layouts 1.15

import "../i18n"

Rectangle {
    id: root
    color: "transparent"

    property var selectedProposalKeys: []
    property var selectedVetoProposalIds: []
    property bool proposalStepDone: sessionStore.senateCurrentStep !== "proposal"

    function itemText(item, fallbackName) {
        if (!item) return fallbackName || ""
        return item.name || item.leader_name || item.province_name || item.contract_id || fallbackName || ""
    }

    function detailText(item) {
        if (!item) return ""
        if (item.faction_name) return GuiText.senateInfluenceDetail(item.faction_name, item.influence)
        if (item.threat_level !== undefined) return GuiText.senateThreatDetail(item.threat_level, item.naval_required)
        if (item.indemnity !== undefined) return GuiText.senatePeaceDetail(item.indemnity, item.duration)
        if (item.governor_type_name) return item.governor_type_name
        if (item.base_cost !== undefined) return GuiText.senateContractDetail(item.base_cost, item.expected_profit)
        return item.status || item.type || ""
    }

    function proposalTitle(item) {
        if (!item) return ""
        return item.title || item.label || item.name || item.type || ""
    }

    function proposalDetail(item) {
        if (!item) return ""
        return item.detail || item.summary || item.description || ""
    }

    function resultMark(item) {
        if (!item) return "\u2713"
        return item.result === "rejected" ? "\u2717" : "\u2713"
    }

    function resultMarkColor(item) {
        if (!item) return theme.statusSuccess
        return item.result === "rejected" ? "#B3261E" : theme.statusSuccess
    }

    function senateVoteButtonText() {
        if (sessionStore.senateCurrentStep === "proposal") return "\u7b49\u5f85\u6267\u653f\u5b98\u63d0\u4ea4\u6cd5\u6848"
        return "\u786e\u8ba4\u8868\u51b3 \u2192 \u79fb\u4ea4\u5426\u51b3\u73af\u8282"
    }

    function vetoCandidateRows() {
        return sessionStore.senateSubmittedProposals || []
    }

    function passedResultRows() {
        var rows = sessionStore.senateSubmittedProposals || []
        var passed = []
        for (var i = 0; i < rows.length; i++) {
            if ((rows[i].result || "passed") === "passed") passed.push(rows[i])
        }
        return passed
    }

    function rejectedResultRows() {
        var rows = sessionStore.senateSubmittedProposals || []
        var rejected = []
        for (var i = 0; i < rows.length; i++) {
            if (rows[i].result === "rejected") rejected.push(rows[i])
        }
        return rejected
    }

    function resultTitleList(rows) {
        var names = []
        for (var i = 0; i < rows.length; i++) names.push(proposalTitle(rows[i]))
        return names.join("\uff1b")
    }

    function passedResultText() {
        var text = resultTitleList(passedResultRows())
        return text.length > 0 ? text : "\u65e0\u6700\u7ec8\u901a\u8fc7\u6cd5\u6848"
    }

    function rejectedResultText() {
        var text = resultTitleList(rejectedResultRows())
        return text.length > 0 ? text : "\u65e0"
    }

    // S4: Governor assignment summary for results display
    function _governorSummary() {
        var rows = sessionStore.senateResult.governor_assignments || []
        if (rows.length === 0) return "\u65e0\u884c\u7701\u9700\u8981\u4efb\u547d\u603b\u7763"
        var parts = []
        for (var i = 0; i < rows.length; i++) {
            parts.push(rows[i].name + "(" + rows[i].province_id + ")")
        }
        return parts.join("\uff1b")
    }

    // S4: Rebellion commander assignment summary for results display
    function _commanderSummary() {
        var rows = sessionStore.senateResult.rebellion_commander_assignments || []
        if (rows.length === 0) return "\u65e0\u8d77\u4e49\u9700\u8981\u6307\u6325\u5b98"
        var parts = []
        for (var i = 0; i < rows.length; i++) {
            parts.push(rows[i].name + "(" + rows[i].rebellion_id + ")")
        }
        return parts.join("\uff1b")
    }

    // S4: Fleet assignment summary for results display
    function _fleetSummary() {
        var rows = sessionStore.senateResult.fleet_assignments || []
        if (rows.length === 0) return "\u65e0"
        var parts = []
        for (var i = 0; i < rows.length; i++) {
            parts.push(rows[i].war_name + "(" + rows[i].total_power + ")")
        }
        return parts.join("\uff1b")
    }

    function tribuneActionText() {
        if (sessionStore.canManuallySelectSenateVeto) return "\u786e\u8ba4\u5426\u51b3 \u2192 \u516c\u793a\u7ed3\u679c"
        return "AI\u5224\u5b9a\u5426\u51b3 \u2192 \u516c\u793a\u7ed3\u679c"
    }

    function hasSelectedVeto(id) {
        return selectedVetoProposalIds.indexOf(id) >= 0
    }

    function setVetoSelected(id, checked) {
        if (id === undefined || id === null || isNaN(id)) return
        var next = selectedVetoProposalIds.slice()
        var pos = next.indexOf(id)
        if (checked && pos < 0) next.push(id)
        if (!checked && pos >= 0) next.splice(pos, 1)
        selectedVetoProposalIds = next
    }

    function leaderCountCopy(count) {
        return GuiText.senateLeaderCount(count)
    }

    // ---- WP-05V V3: 派系色（FC-08 冻结值：Opt=#8B0000 / Pop=#006400 / Equ=#00008B） ----

    function factionColor(factionName) {
        if (!factionName) return "#2C1E12"
        if (factionName.indexOf("Optimates") >= 0) return "#8B0000"
        if (factionName.indexOf("Populares") >= 0) return "#006400"
        if (factionName.indexOf("Equites") >= 0) return "#00008B"
        return "#2C1E12"
    }

    // ---- WP-05V V4 (G6 Narrow): FC-09 阶级枚举名 → 中文标签 ----
    function classTierLabel(tier) {
        if (tier === "NOBILE") return "贵族"
        if (tier === "EQUES") return "骑士"
        if (tier === "PLEBEIAN") return "平民"
        return tier || ""
    }

    // ---- WP-05V G6 Narrow: FC-14 governor 候选人只读信息（复用 governorAppointments DTO） ----
    function governorCandidateInfo(proposal) {
        if (!proposal || !proposal.params) return null
        var provId = proposal.params.province_id
        var candId = proposal.params.candidate_id
        var appts = sessionStore.governorAppointments || {}
        var pending = appts.pending_provinces || []
        for (var i = 0; i < pending.length; i++) {
            if (pending[i].province_id !== provId) continue
            var cands = pending[i].candidates || []
            for (var j = 0; j < cands.length; j++) {
                if (cands[j].id === candId) return cands[j]
            }
        }
        return null
    }

    function governorCandidateNameLine(proposal) {
        var c = governorCandidateInfo(proposal)
        if (!c) return ""
        return '<font color="' + factionColor(c.faction_name) + '">' + (c.name || "") + "</font>"
            + " · " + classTierLabel(c.class_tier)
    }

    function governorCandidateAttrsLine(proposal) {
        var c = governorCandidateInfo(proposal)
        if (!c) return ""
        return "\u519B\u7565 " + (c.martial !== undefined ? c.martial : "\u2014")
            + " \u00B7 \u667A\u7565 " + (c.intelligence !== undefined ? c.intelligence : "\u2014")
            + " \u00B7 \u9B45\u529B " + (c.charisma !== undefined ? c.charisma : "\u2014")
            + " \u00B7 \u5F71\u54CD\u529B " + (c.influence !== undefined ? c.influence : "\u2014")
    }

    function seatLineRich() {
        var rows = sessionStore.senateSeatShares || []
        if (rows.length === 0) return "席位占比：暂无"
        var parts = []
        for (var i = 0; i < rows.length; i++) {
            var name = rows[i].faction_name || rows[i].faction_id || ""
            var color = factionColor(rows[i].faction_name)
            parts.push('<font color="' + color + '">' + name + " " + (rows[i].percent || 0) + "%" + "</font>")
        }
        return "席位占比：" + parts.join(" · ")
    }

    function presidingLine() {
        var po = sessionStore.senatePresidingOfficer || {}
        var name = po.name || "暂无"
        var office = po.office || "官职未定"
        var factionName = po.faction_name || ""
        var base = "会议主持：" + name + "（" + office + "）"
        if (factionName.length > 0) {
            return base + ' · <font color="' + factionColor(factionName) + '">' + factionName + '</font>'
        }
        return base
    }

    function seatLine() {
        var rows = sessionStore.senateSeatShares || []
        if (rows.length === 0) return "席位占比：暂无"
        var parts = []
        for (var i = 0; i < rows.length; i++) {
            var name = rows[i].faction_name || rows[i].faction_id || ""
            parts.push(name + " " + (rows[i].percent || 0) + "%")
        }
        return "席位占比：" + parts.join(" · ")
    }

    function hasSelectedProposal(key) { return selectedProposalKeys.indexOf(key) >= 0 }

    function setProposalSelected(key, checked) {
        var next = selectedProposalKeys.slice()
        var pos = next.indexOf(key)
        if (checked && pos < 0) next.push(key)
        if (!checked && pos >= 0) next.splice(pos, 1)
        selectedProposalKeys = next
    }

    function selectedProposals() {
        var rows = []
        var options = sessionStore.senateProposalOptions || []
        for (var i = 0; i < options.length; i++) {
            var o = options[i]
            if (!hasSelectedProposal(o.key)) continue
            var overrides = billParams[o.key]
            if (!overrides) { rows.push(o); continue }
            var merged = {}
            for (var k in o) { if (o.hasOwnProperty(k)) merged[k] = o[k] }
            var p = {}
            var baseParams = o.params || {}
            for (var pk in baseParams) { if (baseParams.hasOwnProperty(pk)) p[pk] = baseParams[pk] }
            for (var ok in overrides) { if (overrides.hasOwnProperty(ok)) p[ok] = overrides[ok] }
            merged.params = p
            rows.push(merged)
        }
        return rows
    }

    function syncDefaultSelection() {
        var options = sessionStore.senateProposalOptions || []
        var next = []
        for (var i = 0; i < options.length; i++) {
            if (options[i].type === "war" || options[i].type === "peace" || options[i].type === "budget") next.push(options[i].key)
        }
        selectedProposalKeys = next
    }

    // ---- WP-05V V2: accordion 展开状态 + 参数覆盖 ----

    property var expandedBillKeys: []
    property var billParams: ({})

    function toggleBillExpanded(key) {
        var next = expandedBillKeys.slice()
        var pos = next.indexOf(key)
        if (pos >= 0) next.splice(pos, 1)
        else next.push(key)
        expandedBillKeys = next
    }

    function expandCheckedBills() {
        expandedBillKeys = selectedProposalKeys.slice()
    }

    function billParamValue(key, name, fallback) {
        var o = billParams[key]
        if (o && o[name] !== undefined) return o[name]
        return fallback
    }

    function setBillParam(key, name, value) {
        var next = {}
        for (var k in billParams) {
            if (!billParams.hasOwnProperty(k)) continue
            var sub = {}
            for (var n in billParams[k]) { if (billParams[k].hasOwnProperty(n)) sub[n] = billParams[k][n] }
            next[k] = sub
        }
        var target = next[key] || {}
        target[name] = value
        next[key] = target
        billParams = next
    }

    function legionIndexFor(v, model) {
        if (!model || !v) return -1
        return model.indexOf(v)
    }

    function hasZeroValueLandSelection() {
        var options = sessionStore.senateProposalOptions || []
        for (var i = 0; i < options.length; i++) {
            var o = options[i]
            if (o.type !== "land" || !hasSelectedProposal(o.key)) continue
            var percent = billParamValue(o.key, "percent", (o.params && o.params.percent) || 0)
            var publicLand = o.public_land || 0
            if (percent <= 0 || publicLand <= 0) return true
        }
        return false
    }

    // ---- WP-05V V4: FC-12 表决参数描述（复用 proposal params，回退 label） ----
    function voteParamDescription(item) {
        if (!item) return ""
        if (item.type === "war") return ""  // 后端 _proposal_label 已含「（征召 N 个军团）」，避免重复（G5 识图缺陷）
        if (item.type === "budget") return ""  // 后端 _proposal_label 已含「（预算 N T）」，避免重复（G5 识图缺陷，与 war 同源）
        if (item.type === "land") {
            var actName = item.act_type === "sale" ? "出售" : "分配"
            return "（" + actName + " " + ((item.percent !== undefined ? item.percent : 0) * 100).toFixed(0) + "% 公地）"
        }
        return ""
    }

    function refreshAccordion() {
        syncDefaultSelection()
        expandCheckedBills()
    }

    Component.onCompleted: {
        refreshAccordion()
    }

    Connections {
        target: sessionStore
        function onSenateViewChanged() {
            // 提案阶段：选项加载完成后同步默认选中并展开（G7「只有法案条目无控件」闭合）
            if (sessionStore.senateCurrentStep === "proposal") {
                if (selectedProposalKeys.length === 0) root.refreshAccordion()
                else root.expandCheckedBills()
            }
        }
    }

    ColumnLayout {
        anchors.fill: parent
        anchors.margins: 14
        spacing: 10

        Rectangle {
            Layout.fillWidth: true
            Layout.preferredHeight: 92
            color: "#FFF7E9"
            border.color: "#D9AF63"
            border.width: 1
            radius: 6
            ColumnLayout {
                anchors.fill: parent
                anchors.margins: 12
                spacing: 5
                Text { text: "🏛 元老院议事"; color: "#2C1E12"; font.pixelSize: 13; font.bold: true }
                Text {
                    text: root.presidingLine()
                    textFormat: Text.RichText
                    color: "#2C1E12"
                    font.pixelSize: 12
                    Layout.fillWidth: true
                    wrapMode: Text.Wrap
                }
                Text { text: root.seatLineRich(); textFormat: Text.RichText; color: "#9A2D0A"; font.pixelSize: 12; font.bold: true; Layout.fillWidth: true; wrapMode: Text.Wrap }
                Text { text: "※ 最终通过法案及政府运作结果将在此展示"; color: "#766652"; font.pixelSize: 11; Layout.fillWidth: true; wrapMode: Text.Wrap }
            }
        }

        Rectangle {
            visible: sessionStore.senateCurrentStep === "results"
            Layout.fillWidth: true
            Layout.preferredHeight: 150
            Layout.minimumHeight: 110
            Layout.maximumHeight: 200
            color: "#FFF7E9"
            border.color: "#D9AF63"
            border.width: 1
            radius: 6
            clip: true

            ScrollView {
                anchors.fill: parent
                anchors.margins: 4
                clip: true
                contentWidth: availableWidth
                ColumnLayout {
                    width: parent.width
                    spacing: 6
                Text {
                    visible: root.rejectedResultRows().length > 0
                    text: "\u26d4 \u4fdd\u6c11\u5b98\u5426\u51b3 " + root.rejectedResultRows().length + " \u9879\uff1a" + root.rejectedResultText()
                    color: "#B3261E"
                    font.pixelSize: 12
                    font.bold: true
                    Layout.fillWidth: true
                    wrapMode: Text.Wrap
                    maximumLineCount: 2
                    elide: Text.ElideRight
                }

                // S4: Governor assignment results
                Text {
                    visible: (sessionStore.senateResult.governor_assignments || []).length > 0
                    text: "\u2022 \u884c\u7701\u603b\u7763\u4efb\u547d\uff1a" + root._governorSummary()
                    color: "#2C1E12"
                    font.pixelSize: 11
                    font.bold: true
                    Layout.fillWidth: true
                    wrapMode: Text.Wrap
                    maximumLineCount: 3
                    elide: Text.ElideRight
                }

                // S4: Rebellion commander assignment results
                Text {
                    visible: (sessionStore.senateResult.rebellion_commander_assignments || []).length > 0
                    text: "\u2022 \u8d77\u4e49\u6307\u6325\u5b98\u4efb\u547d\uff1a" + root._commanderSummary()
                    color: "#2C1E12"
                    font.pixelSize: 11
                    font.bold: true
                    Layout.fillWidth: true
                    wrapMode: Text.Wrap
                    maximumLineCount: 3
                    elide: Text.ElideRight
                }

                // S4: Fleet assignment results
                Text {
                    visible: (sessionStore.senateResult.fleet_assignments || []).length > 0
                    text: "\u2022 \u8230\u961f\u6307\u6d3e\uff1a" + root._fleetSummary()
                    color: "#2C1E12"
                    font.pixelSize: 11
                    font.bold: true
                    Layout.fillWidth: true
                    wrapMode: Text.Wrap
                    maximumLineCount: 3
                    elide: Text.ElideRight
                }

                Rectangle {
                    Layout.fillWidth: true
                    Layout.preferredHeight: 84
                    Layout.minimumHeight: 72
                    radius: 4
                    color: "#FFF6E6"
                    border.color: "#2E9D4D"
                    border.width: 1
                    RowLayout {
                        anchors.fill: parent
                        anchors.margins: 10
                        spacing: 10
                        Text {
                            text: "\u653f\u5e9c\n\u8fd0\u4f5c"
                            color: "#2C1E12"
                            font.pixelSize: 12
                            font.bold: true
                            horizontalAlignment: Text.AlignHCenter
                            verticalAlignment: Text.AlignVCenter
                            Layout.preferredWidth: 44
                            Layout.fillHeight: true
                        }
                        Text {
                            text: "\u2022 \u6700\u7ec8\u901a\u8fc7\uff1a" + root.passedResultText() + "\n\u2022 \u901a\u8fc7\u6cd5\u6848\u7eb3\u5165\u6267\u884c\uff0c\u56fd\u5e93\u3001\u516c\u5730\u4e0e\u5408\u540c\u7ed3\u679c\u540c\u6b65\u751f\u6548"
                            color: "#2C1E12"
                            font.pixelSize: 12
                            font.bold: true
                            Layout.fillWidth: true
                            Layout.fillHeight: true
                            wrapMode: Text.Wrap
                            maximumLineCount: 4
                            elide: Text.ElideRight
                            verticalAlignment: Text.AlignVCenter
                        }
                    }
                }
                }
            }
        }

        RowLayout {
            Layout.fillWidth: true
            Layout.preferredHeight: sessionStore.senateCurrentStep === "results" ? 200 : 460
            Layout.minimumHeight: sessionStore.senateCurrentStep === "results" ? 170 : 460
            Layout.maximumHeight: sessionStore.senateCurrentStep === "results" ? 240 : 460
            spacing: 12

            SenateWorkPanel {
                title: "1  执政官提案 · 配置参数"
                fpNum: "1"
                active: sessionStore.senateCurrentStep === "proposal"
                completed: root.proposalStepDone
                Layout.fillWidth: true
                Layout.fillHeight: true

                ColumnLayout {
                    anchors.fill: parent
                    anchors.margins: 10
                    anchors.topMargin: 44
                    spacing: 7
                    Text {
                        text: sessionStore.senateCurrentStep === "proposal" ? "勾选执政官本轮提交元老院的法案。" : "已提交法案，等待元老院表决。"
                        color: theme.textSecondary
                        font.pixelSize: 11
                        Layout.fillWidth: true
                        wrapMode: Text.Wrap
                    }

                    // DEV-13: 战争接管（直接职权，无需表决）
                    Rectangle {
                        visible: sessionStore.senateCurrentStep === "proposal"
                        Layout.fillWidth: true
                        Layout.preferredHeight: 92
                        radius: 4
                        color: "#FDF3E0"
                        border.color: "#E6A542"
                        border.width: 1
                        ColumnLayout {
                            anchors.fill: parent
                            anchors.margins: 8
                            spacing: 4
                            Text {
                                text: "🛡️ 接管战争 ⚡ 无需表决"
                                color: "#9A2D0A"
                                font.pixelSize: 12
                                font.bold: true
                            }
                            Text {
                                text: "执政官可直接接管进行中的外战，不进入元老院表决。"
                                color: "#766652"
                                font.pixelSize: 10
                                Layout.fillWidth: true
                                wrapMode: Text.Wrap
                            }
                            Repeater {
                                model: sessionStore.senateTakeoverOptions || []
                                delegate: Rectangle {
                                    Layout.fillWidth: true
                                    height: 28
                                    radius: 3
                                    color: "#FFF7E9"
                                    border.color: "#D9AF63"
                                    border.width: 1
                                    RowLayout {
                                        anchors.fill: parent
                                        anchors.margins: 4
                                        spacing: 6
                                        Text {
                                            text: (modelData.name || modelData.war_id) + (modelData.reason ? "（" + modelData.reason + "）" : "")
                                            color: "#2C1E12"
                                            font.pixelSize: 11
                                            Layout.fillWidth: true
                                            elide: Text.ElideRight
                                        }
                                        Rectangle {
                                            Layout.preferredWidth: 52
                                            Layout.preferredHeight: 20
                                            radius: 3
                                            enabled: sessionStore.canTakeoverSenateWar
                                            opacity: enabled ? 1.0 : 0.45
                                            color: enabled ? "#D9AA52" : "#D8B16C"
                                            Text {
                                                anchors.centerIn: parent
                                                text: "接管"
                                                color: "#2C1E12"
                                                font.pixelSize: 11
                                                font.bold: true
                                            }
                                            MouseArea {
                                                anchors.fill: parent
                                                enabled: parent.enabled
                                                onClicked: sessionStore.doTakeoverWar(modelData.war_id)
                                            }
                                        }
                                    }
                                }
                            }
                        }
                    }
                    ScrollView {
                        Layout.fillWidth: true
                        Layout.fillHeight: true
                        clip: true
                        contentWidth: availableWidth
                        ColumnLayout {
                            width: parent.width
                            spacing: 6
                            Repeater {
                                model: sessionStore.senateCurrentStep === "proposal" ? (sessionStore.senateProposalOptions || []) : (sessionStore.senateSubmittedProposals || [])
                                delegate: Rectangle {
                                    id: billCard
                                    Layout.fillWidth: true
                                    property bool isProposal: sessionStore.senateCurrentStep === "proposal"
                                    property bool expanded: isProposal && root.expandedBillKeys.indexOf(modelData.key) >= 0
                                    property string billKey: (modelData && modelData.key) ? modelData.key : ""
                                    property real defaultBudget: (modelData.params && modelData.params.budget_range) ? modelData.params.budget_range.default : 0
                                    property real defaultPercent: (modelData.params && modelData.params.percent) ? modelData.params.percent : 0.10
                                    Layout.preferredHeight: isProposal
                                        ? (expanded ? cardColumn.implicitHeight + 12 : headerRow.implicitHeight + 12)
                                        : 48
                                    Layout.minimumHeight: 32
                                    radius: 4
                                    color: "#FFF6E6"
                                    border.color: "#E0B56C"
                                    border.width: 1

                                    ColumnLayout {
                                        id: cardColumn
                                        anchors.fill: parent
                                        anchors.margins: 6
                                        spacing: 4

                                        RowLayout {
                                            id: headerRow
                                            Layout.fillWidth: true
                                            spacing: 6

                                            CheckBox {
                                                visible: isProposal
                                                enabled: sessionStore.canCreateSenateProposal
                                                checked: root.hasSelectedProposal(modelData.key)
                                                onToggled: root.setProposalSelected(modelData.key, checked)
                                            }

                                            Text {
                                                visible: !isProposal
                                                text: "\u2713"
                                                color: theme.statusSuccess
                                                font.pixelSize: 13
                                                font.bold: true
                                            }

                                            Text {
                                                text: root.proposalTitle(modelData)
                                                color: "#2C1E12"
                                                font.pixelSize: 12
                                                font.bold: true
                                                Layout.fillWidth: true
                                                elide: Text.ElideRight
                                            }

                                            Text {
                                                visible: isProposal
                                                text: expanded ? "\u25BC" : "\u25B6"
                                                color: "#766652"
                                                font.pixelSize: 10
                                                horizontalAlignment: Text.AlignHCenter
                                                verticalAlignment: Text.AlignVCenter
                                            }

                                            MouseArea {
                                                visible: isProposal
                                                width: 18
                                                height: 20
                                                cursorShape: Qt.PointingHandCursor
                                                onClicked: root.toggleBillExpanded(billKey)
                                            }
                                        }

                                        Text {
                                            visible: !isProposal && root.proposalDetail(modelData).length > 0
                                            text: root.proposalDetail(modelData)
                                            color: "#766652"
                                            font.pixelSize: 10
                                            Layout.fillWidth: true
                                            elide: Text.ElideRight
                                        }

                                        ColumnLayout {
                                            id: billBody
                                            visible: isProposal && expanded
                                            Layout.fillWidth: true
                                            spacing: 6

                                            Text {
                                                visible: root.proposalDetail(modelData).length > 0
                                                text: root.proposalDetail(modelData)
                                                color: "#766652"
                                                font.pixelSize: 10
                                                Layout.fillWidth: true
                                                wrapMode: Text.Wrap
                                            }

                                            // FC-01 宣战军团数量下拉（authoritative：legion_options = config 派生 [min..可用池]）
                                            RowLayout {
                                                visible: modelData.type === "war"
                                                Layout.fillWidth: true
                                                spacing: 6
                                                Text { text: "征召军团"; color: "#2C1E12"; font.pixelSize: 11; Layout.preferredWidth: 60 }
                                                ComboBox {
                                                    id: legionCombo
                                                    Layout.fillWidth: true
                                                    enabled: (modelData.params && modelData.params.legion_options) ? true : false
                                                    model: (modelData.params && modelData.params.legion_options) ? modelData.params.legion_options : []
                                                    currentIndex: root.legionIndexFor(root.billParamValue(billKey, "legions", (modelData.params && modelData.params.legions) || 0), (modelData.params && modelData.params.legion_options) || [])
                                                    onActivated: root.setBillParam(billKey, "legions", model[currentIndex])
                                                }
                                                Text {
                                                    visible: !(modelData.params && modelData.params.legion_options)
                                                    text: "值域待定义"
                                                    color: "#9A2D0A"
                                                    font.pixelSize: 11
                                                }
                                            }

                                            // FC-03/FC-04 预算 slider（authoritative：budget_range = config 派生 per-contract 值域）
                                            ColumnLayout {
                                                visible: modelData.type === "budget"
                                                Layout.fillWidth: true
                                                spacing: 2
                                                RowLayout {
                                                    Layout.fillWidth: true
                                                    Text { text: "预算金额"; color: "#2C1E12"; font.pixelSize: 11; Layout.preferredWidth: 60 }
                                                    Text {
                                                        text: Math.round(budgetSlider.value) + " T"
                                                        color: "#9A2D0A"
                                                        font.pixelSize: 11
                                                        font.bold: true
                                                    }
                                                }
                                                Slider {
                                                    id: budgetSlider
                                                    Layout.fillWidth: true
                                                    enabled: (modelData.params && modelData.params.budget_range) ? true : false
                                                    from: (modelData.params && modelData.params.budget_range) ? modelData.params.budget_range.min : 0
                                                    to: (modelData.params && modelData.params.budget_range) ? modelData.params.budget_range.max : 0
                                                    stepSize: (modelData.params && modelData.params.budget_range) ? modelData.params.budget_range.step : 1
                                                    value: defaultBudget
                                                    onValueChanged: root.setBillParam(billKey, "modified_budget", Math.round(value))
                                                }
                                                Text {
                                                    visible: !(modelData.params && modelData.params.budget_range)
                                                    text: "值域待定义"
                                                    color: "#9A2D0A"
                                                    font.pixelSize: 11
                                                }
                                            }

                                            // FC-05/FC-06 卖地/分地 percent slider + 公地换算
                                            ColumnLayout {
                                                visible: modelData.type === "land"
                                                Layout.fillWidth: true
                                                spacing: 2
                                                RowLayout {
                                                    Layout.fillWidth: true
                                                    Text { text: "土地比例"; color: "#2C1E12"; font.pixelSize: 11; Layout.preferredWidth: 60 }
                                                    Text {
                                                        text: (landSlider.value * 100).toFixed(0) + "% = " + Math.floor((modelData.public_land || 0) * landSlider.value) + " C"
                                                        color: "#9A2D0A"
                                                        font.pixelSize: 11
                                                        font.bold: true
                                                    }
                                                }
                                                Slider {
                                                    id: landSlider
                                                    Layout.fillWidth: true
                                                    from: 0.05
                                                    to: 1.00
                                                    stepSize: 0.05
                                                    value: defaultPercent
                                                    onValueChanged: root.setBillParam(billKey, "percent", value)
                                                }
                                            }

                                            // FC-14 + FC-09 + FC-13: governor 候选人只读展示 + 合格条件提示（G6 Narrow）
                                            ColumnLayout {
                                                visible: modelData.type === "governor"
                                                Layout.fillWidth: true
                                                spacing: 4

                                                Text {
                                                    text: "合格条件：元老院成员，曾任大法官以上官职"
                                                    color: "#766652"
                                                    font.pixelSize: 10
                                                    Layout.fillWidth: true
                                                    wrapMode: Text.Wrap
                                                }

                                                Text {
                                                    visible: root.governorCandidateNameLine(modelData).length > 0
                                                    text: root.governorCandidateNameLine(modelData)
                                                    textFormat: Text.RichText
                                                    color: "#2C1E12"
                                                    font.pixelSize: 11
                                                    font.bold: true
                                                    Layout.fillWidth: true
                                                    wrapMode: Text.Wrap
                                                }

                                                Text {
                                                    visible: root.governorCandidateAttrsLine(modelData).length > 0
                                                    text: root.governorCandidateAttrsLine(modelData)
                                                    color: "#766652"
                                                    font.pixelSize: 10
                                                    Layout.fillWidth: true
                                                    wrapMode: Text.Wrap
                                                }
                                            }
                                        }
                                    }
                                }
                            }
                        }
                    }
                    Rectangle {
                        Layout.fillWidth: true
                        Layout.preferredHeight: 26
                        radius: 4
                        enabled: sessionStore.canCreateSenateProposal && root.selectedProposalKeys.length > 0 && !root.hasZeroValueLandSelection()
                        opacity: enabled ? 1.0 : 0.45
                        gradient: Gradient { GradientStop { position: 0.0; color: "#D9AA52" } GradientStop { position: 1.0; color: "#BC7B28" } }
                        Text { anchors.centerIn: parent; text: root.proposalStepDone ? "\u2190 \u6cd5\u6848\u5df2\u63d0\u4ea4" : "\u63d0\u4ea4\u9009\u4e2d\u6cd5\u6848 \u2192 \u79fb\u4ea4\u8868\u51b3"; color: "#2C1E12"; font.pixelSize: 12; font.bold: true }
                        MouseArea { anchors.fill: parent; enabled: parent.enabled; onClicked: sessionStore.doSubmitSenateProposals(root.selectedProposals()) }
                    }
                }
            }

            SenateWorkPanel {
                title: "2  元老院表决"
                fpNum: "2"
                active: sessionStore.senateCurrentStep === "senate_vote"
                completed: sessionStore.senateCurrentStep === "tribune_veto" || sessionStore.senateCurrentStep === "results"
                Layout.fillWidth: true
                Layout.fillHeight: true
                ColumnLayout {
                    anchors.fill: parent
                    anchors.margins: 10
                    anchors.topMargin: 44
                    spacing: 7
                    Text { text: "勾选同意（多选），未勾选 = 否决。所有派系执行完毕后进入否决环节。"; color: theme.textSecondary; font.pixelSize: 11; Layout.fillWidth: true; wrapMode: Text.Wrap }
                    ScrollView {
                        Layout.fillWidth: true
                        Layout.fillHeight: true
                        clip: true
                        contentWidth: availableWidth
                        ColumnLayout {
                            width: parent.width
                            spacing: 6
                            Repeater {
                                model: sessionStore.senateSubmittedProposals || []
                                delegate: CheckBox { Layout.fillWidth: true; enabled: sessionStore.senateCurrentStep === "senate_vote"; text: (modelData.label || modelData.type) + root.voteParamDescription(modelData); checked: true; font.pixelSize: 12 }
                            }
                        }
                    }
                    ActionButton {
                        text: root.senateVoteButtonText()
                        enabled: sessionStore.canSubmitSenateVote
                        onTriggered: sessionStore.doSubmitSenateVotes()
                    }
                }
                LockedOverlay { anchors.fill: parent; visible: sessionStore.senateCurrentStep === "proposal"; text: "⏳ 等待执政官提交法案" }
            }

            SenateWorkPanel {
                title: "3  保民官否决"
                fpNum: "3"
                active: sessionStore.senateCurrentStep === "tribune_veto"
                completed: sessionStore.senateCurrentStep === "results"
                Layout.fillWidth: true
                Layout.fillHeight: true
                ColumnLayout {
                    anchors.fill: parent
                    anchors.margins: 10
                    anchors.topMargin: 44
                    spacing: 7
                    Text { text: "\u901a\u8fc7\u6cd5\u6848\u5217\u8868\u3002\u4fdd\u6c11\u5b98\u52fe\u9009\u5426\u51b3\uff08\u591a\u9009\uff09\uff0c\u672a\u52fe\u9009 = \u540c\u610f\u3002"; color: theme.textSecondary; font.pixelSize: 11; Layout.fillWidth: true; wrapMode: Text.Wrap }
                    ScrollView {
                        Layout.fillWidth: true
                        Layout.fillHeight: true
                        clip: true
                        contentWidth: availableWidth
                        ColumnLayout {
                            width: parent.width
                            spacing: 6
                            Repeater {
                                model: root.vetoCandidateRows()
                                delegate: Rectangle {
                                    Layout.fillWidth: true
                                    height: 48
                                    radius: 4
                                    color: "#FFF6E6"
                                    border.color: "#E0B56C"
                                    border.width: 1
                                    RowLayout {
                                        anchors.fill: parent
                                        anchors.margins: 8
                                        spacing: 6
                                        Text {
                                            visible: sessionStore.senateCurrentStep === "results"
                                            text: root.resultMark(modelData)
                                            color: root.resultMarkColor(modelData)
                                            font.pixelSize: 13
                                            font.bold: true
                                        }
                                        CheckBox {
                                            visible: sessionStore.senateCurrentStep !== "results"
                                            enabled: sessionStore.senateCurrentStep === "tribune_veto" && sessionStore.canManuallySelectSenateVeto
                                            checked: root.hasSelectedVeto(Number(modelData.id))
                                            onToggled: root.setVetoSelected(Number(modelData.id), checked)
                                        }
                                        ColumnLayout {
                                            Layout.fillWidth: true
                                            spacing: 1
                                            Text {
                                                text: root.proposalTitle(modelData)
                                                color: "#2C1E12"
                                                font.pixelSize: 12
                                                font.bold: true
                                                Layout.fillWidth: true
                                                elide: Text.ElideRight
                                            }
                                            Text {
                                                visible: root.proposalDetail(modelData).length > 0
                                                text: root.proposalDetail(modelData)
                                                color: "#766652"
                                                font.pixelSize: 10
                                                Layout.fillWidth: true
                                                elide: Text.ElideRight
                                            }
                                        }
                                    }
                                }
                            }
                        }
                    }
                    ActionButton {
                        text: root.tribuneActionText()
                        enabled: sessionStore.canSubmitSenateVeto
                        onTriggered: sessionStore.doSubmitSenateVetoes(root.selectedVetoProposalIds)
                    }
                }
                LockedOverlay { anchors.fill: parent; visible: sessionStore.senateCurrentStep !== "tribune_veto" && sessionStore.senateCurrentStep !== "results"; text: "⏳ 等待元老院表决完成" }
            }
        }
    }

    component StageStep: Row {
        property bool done: false
        property bool active: false
        property string label: ""
        spacing: 5
        Layout.alignment: Qt.AlignVCenter
        Rectangle {
            width: 20
            height: 20
            radius: 10
            color: done ? theme.statusSuccess : (active ? "#E8B84B" : "#E8D5C4")
            Text { anchors.centerIn: parent; text: done ? "✓" : label.substring(0, 1); color: done ? "white" : "#2C1E12"; font.pixelSize: 11; font.bold: true }
        }
        Text { text: label.replace(/^[0-9] /, ""); color: active || done ? theme.textPrimary : theme.textMuted; font.pixelSize: 12; font.bold: active; anchors.verticalCenter: parent.verticalCenter }
    }

    component StepArrow: Text { text: "→"; color: "#B8A080"; font.pixelSize: 12; Layout.alignment: Qt.AlignVCenter }

    component SenateWorkPanel: Rectangle {
        property string title: ""
        property string fpNum: ""
        property bool active: false
        property bool completed: false
        color: "#FFF7E9"
        border.color: active ? "#9A2D0A" : "#D9AF63"
        border.width: 1
        radius: 6
        clip: true
        Rectangle {
            anchors.left: parent.left
            anchors.right: parent.right
            anchors.top: parent.top
            height: 36
            color: active || completed ? "#8F2506" : "#B98A76"
            Rectangle {
                anchors.left: parent.left
                anchors.leftMargin: 10
                anchors.verticalCenter: parent.verticalCenter
                width: 20
                height: 20
                radius: 10
                color: "#D9AA52"
                visible: fpNum.length > 0
                Text { anchors.centerIn: parent; text: fpNum; color: "#8F2506"; font.pixelSize: 11; font.bold: true }
            }
            Text { anchors.verticalCenter: parent.verticalCenter; anchors.left: parent.left; anchors.leftMargin: fpNum.length > 0 ? 38 : 10; text: title; color: "white"; font.pixelSize: 13; font.bold: true }
        }
    }

    component ActionButton: Rectangle {
        property string text: ""
        signal triggered()
        Layout.fillWidth: true
        Layout.preferredHeight: 26
        radius: 4
        opacity: enabled ? 1.0 : 0.45
        gradient: Gradient { GradientStop { position: 0.0; color: enabled ? "#D9AA52" : "#D8B16C" } GradientStop { position: 1.0; color: enabled ? "#BC7B28" : "#D8B16C" } }
        Text { anchors.centerIn: parent; text: parent.text; color: "#2C1E12"; font.pixelSize: 12; font.bold: true }
        MouseArea { anchors.fill: parent; enabled: parent.enabled; onClicked: parent.triggered() }
    }

    component ActionStub: Rectangle {
        property string text: ""
        Layout.fillWidth: true
        Layout.preferredHeight: 26
        radius: 4
        color: "#D8B16C"
        opacity: 0.65
        Text { anchors.centerIn: parent; text: parent.text; color: "#60411E"; font.pixelSize: 12; font.bold: true }
    }

    component LockedOverlay: Rectangle {
        property string text: ""
        color: "#C7A79899"
        radius: 6
        z: 20
        Text { anchors.centerIn: parent; text: parent.text; color: "white"; font.pixelSize: 12; font.bold: true }
    }
}
