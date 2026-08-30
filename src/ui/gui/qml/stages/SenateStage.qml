import QtQuick 2.15
import QtQuick.Controls 2.15
import QtQuick.Layouts 1.15

import "../components"
import "../i18n"

Rectangle {
    id: root
    color: "transparent"

    property var selectedProposalKeys: []
    property var selectedVetoProposalIds: []
    property bool proposalStepDone: sessionStore.senateCurrentStep !== "proposal"

    FactionStyle { id: factionStyle }

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

    // WP-F R1-F-03：per-proposal 支持率 helper（join 权威 vote_results，纯展示除法，禁重算/decider 重入）
    function voteResultFor(proposalId) {
        var rows = sessionStore.senateVoteResults || []
        for (var i = 0; i < rows.length; i++) {
            if (Number(rows[i].proposal_id) === Number(proposalId)) return rows[i]
        }
        return null
    }
    function supportRateText(vr) {
        if (!vr || vr.total_influence <= 0) return "\u652f\u6301\u7387 \u2014"
        var pct = Math.round(vr.support_influence * 100 / vr.total_influence)
        if (vr.vetoed) return "\u672a\u901a\u8fc7 \u00b7 \u652f\u6301\u7387 " + pct + "%"
        if (vr.passed) return "\u901a\u8fc7 \u00b7 \u652f\u6301\u7387 " + pct + "%"
        return "\u672a\u901a\u8fc7 \u00b7 \u652f\u6301\u7387 " + pct + "%"
    }

    function senateVoteButtonText() {
        if (sessionStore.senateCurrentStep === "proposal") return "\u7b49\u5f85\u6267\u653f\u5b98\u63d0\u4ea4\u6cd5\u6848"
        return "\u786e\u8ba4\u8868\u51b3 \u2192 \u79fb\u4ea4\u5426\u51b3\u73af\u8282"
    }

    // WP-F R2-01（F-01B/C/D）：Stage 3 只渲染权威 passed-only 候选集——按后端
    // senateVetoCandidateIds 映射 display rows（禁 QML 平行过滤/重算/阈值判定）
    function vetoCandidateRows() {
        var ids = sessionStore.senateVetoCandidateIds || []
        var rows = sessionStore.senateSubmittedProposals || []
        var out = []
        for (var i = 0; i < rows.length; i++) {
            for (var j = 0; j < ids.length; j++) {
                if (Number(rows[i].id) === Number(ids[j])) { out.push(rows[i]); break }
            }
        }
        return out
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

    // ---- WP-D AU-6: Public Announcement 渲染（数据来自 authoritative DTO，禁 QML 推导） ----
    function _announcementEnactedText() {
        var rows = (sessionStore.senatePublicAnnouncement || {}).enacted_proposals || []
        if (rows.length === 0) return "\u65e0"
        var parts = []
        for (var i = 0; i < rows.length; i++) {
            var r = rows[i]
            var line = r.title || ""
            var kp = r.key_parameters || {}
            if (r.type === "land" && kp.amount_C !== undefined) {
                line += "（" + (kp.act_type === "sale" ? "\u51fa\u552e" : "\u5206\u914d") + " " + kp.amount_C + " C \u516c\u5730）"
            } else if (r.type === "war" && kp.legions !== undefined) {
                line += "（" + kp.legions + " \u519b\u56e2\uff09"
            } else if (r.type === "budget" && kp.modified_budget !== undefined) {
                line += "（\u9884\u7b97 " + kp.modified_budget + " T\uff09"
            }
            parts.push(line)
        }
        return parts.join("\uff1b")
    }

    function _directActionText() {
        var rows = (sessionStore.senatePublicAnnouncement || {}).direct_actions || []
        if (rows.length === 0) return "\u65e0"
        var parts = []
        for (var i = 0; i < rows.length; i++) {
            var a = rows[i]
            parts.push("\u63a5\u7ba1\u6218\u4e89 \u2014 " + (a.war_name || a.war_id) + " \u00b7 " + (a.commander_name || a.commander_id))
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
    // WP-F S1-2 (003/R-01): 本地三分支硬编码已删除 → 共享 FactionStyle 实例（factionStyle.factionColor）。

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
        return '<font color="' + factionStyle.factionColor(c.faction_name) + '">' + (c.name || "") + "</font>"
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
            var color = factionStyle.factionColor(rows[i].faction_name)
            parts.push('<font color="' + color + '">' + name + " " + (rows[i].percent || 0) + "%" + "</font>")
        }
        return "席位占比：" + parts.join(" · ")
    }

    function presidingLine() {
        var po = sessionStore.senatePresidingOfficer || {}
        var name = po.name || "暂无"
        var office = po.office || "官职未定"
        var factionName = po.faction_name || ""
        var base = "会议主持："
        if (factionName.length > 0) {
            return base
                + '<font color="' + factionStyle.factionColor(factionName) + '">' + name + '</font>'
                + "（" + office + "）"
                + ' · <font color="' + factionStyle.factionColor(factionName) + '">' + factionName + '</font>'
        }
        return base + name + "（" + office + "）"
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
        // AU-R1-04a（R1-04 冻结契约）：checkbox 为控制交互——checked 自动展开 /
        // unchecked 折叠（无陈旧参数面板残留）；三角 toggleBillExpanded 保留为手动覆盖。
        var expanded = expandedBillKeys.slice()
        var epos = expanded.indexOf(key)
        if (checked && epos < 0) expanded.push(key)
        if (!checked && epos >= 0) expanded.splice(epos, 1)
        expandedBillKeys = expanded
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
            var amountC = billParamValue(o.key, "amount_C", (o.params && o.params.amount_C) || 0)
            var publicLand = o.public_land || 0
            if (amountC <= 0 || publicLand <= 0) return true
        }
        return false
    }

    // ---- WP-05V V4: FC-12 表决参数描述（复用 proposal params，回退 label） ----
    function voteParamDescription(item) {
        if (!item) return ""
        if (item.type === "war") return ""  // 后端 _proposal_label 已含「（征召 N 个军团）」，避免重复（G5 识图缺陷）
        if (item.type === "budget") return ""  // 后端 _proposal_label 已含「（预算 N T）」，避免重复（G5 识图缺陷，与 war 同源）
        if (item.type === "land") return ""  // AU-7：后端 _proposal_label 已含「出售 N C（约 M%）」，与 war/budget 同源避免重复（实现注记：计划 Q-4 字面会与 label 重复，按文件内既有模式取 label 为准）
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

                // WP-D AU-6: ✅ 最终通过（Public Announcement —— 仅 final enacted，D-06 rejected 不进公示）
                Text {
                    visible: ((sessionStore.senatePublicAnnouncement || {}).enacted_proposals || []).length > 0
                    text: "\u2705 \u6700\u7ec8\u901a\u8fc7\uff1a" + root._announcementEnactedText()
                    color: "#2E7D32"
                    font.pixelSize: 12
                    font.bold: true
                    Layout.fillWidth: true
                    wrapMode: Text.Wrap
                    maximumLineCount: 3
                    elide: Text.ElideRight
                }

                // WP-D AU-6: ⚡ 直接生效（Direct Actions —— 依法直接生效，不经过 vote/veto）
                Text {
                    visible: ((sessionStore.senatePublicAnnouncement || {}).direct_actions || []).length > 0
                    text: "\u26a1 \u76f4\u63a5\u751f\u6548\uff1a" + root._directActionText()
                    color: "#9A2D0A"
                    font.pixelSize: 12
                    font.bold: true
                    Layout.fillWidth: true
                    wrapMode: Text.Wrap
                    maximumLineCount: 3
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
                    // WP-F G7-02：无目标 → 折叠/隐藏（WP-G 权威状态驱动，零业务移除）
                    Rectangle {
                        visible: sessionStore.senateCurrentStep === "proposal" && (sessionStore.senateTakeoverOptions || []).length > 0
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
                                    property real defaultBudget: (modelData.budget_range) ? modelData.budget_range.default : 0
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
                                                // AU-R1-03a：非执政官 viewer 三角禁用（参数面板不可展开）
                                                enabled: sessionStore.canCreateSenateProposal
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
                                                    // AU-R1-03a：非执政官 viewer 不可编辑（authority 门控）
                                                    enabled: sessionStore.canCreateSenateProposal && ((modelData.legion_options && modelData.legion_options.allowed && modelData.legion_options.allowed.length > 0) ? true : false)
                                                    model: (modelData.legion_options && modelData.legion_options.allowed) ? modelData.legion_options.allowed : []
                                                    currentIndex: root.legionIndexFor(root.billParamValue(billKey, "legions", (modelData.params && modelData.params.legions) || 0), (modelData.legion_options && modelData.legion_options.allowed) || [])
                                                    onActivated: root.setBillParam(billKey, "legions", model[currentIndex])
                                                }
                                                Text {
                                                    visible: !(modelData.legion_options && modelData.legion_options.allowed)
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
                                                    // AU-R1-03a：非执政官 viewer 不可编辑（authority 门控）
                                                    enabled: sessionStore.canCreateSenateProposal && (modelData.budget_range ? true : false)
                                                    from: (modelData.budget_range) ? modelData.budget_range.min : 0
                                                    to: (modelData.budget_range) ? modelData.budget_range.max : 0
                                                    stepSize: (modelData.budget_range) ? modelData.budget_range.step : 1
                                                    value: (modelData.params && modelData.params.modified_budget !== undefined) ? modelData.params.modified_budget : defaultBudget
                                                    onValueChanged: root.setBillParam(billKey, "modified_budget", Math.round(value))
                                                }
                                                Text {
                                                    visible: !modelData.budget_range
                                                    text: "值域待定义"
                                                    color: "#9A2D0A"
                                                    font.pixelSize: 11
                                                }
                                            }

                                            // FC-05/FC-06 卖地/分地 amount_C slider（AU-7：authoritative = params.amount_C int 主输入；
                                            // percent 仅派生展示 = amount_C / root public_land，禁独立编辑）
                                            ColumnLayout {
                                                visible: modelData.type === "land"
                                                Layout.fillWidth: true
                                                spacing: 2
                                                RowLayout {
                                                    Layout.fillWidth: true
                                                    Text { text: "土地数量"; color: "#2C1E12"; font.pixelSize: 11; Layout.preferredWidth: 60 }
                                                    Text {
                                                        text: Math.round(landSlider.value) + " C（约 " + Math.round((landSlider.value / (modelData.public_land || 1)) * 100) + "%）"
                                                        color: "#9A2D0A"
                                                        font.pixelSize: 11
                                                        font.bold: true
                                                    }
                                                }
                                                Slider {
                                                    id: landSlider
                                                    Layout.fillWidth: true
                                                    // AU-R1-03a：非执政官 viewer 不可编辑（authority 门控）；
                                                    // AU-R1-06c：public_land 缺失 → 回退 1（null-safe）
                                                    enabled: sessionStore.canCreateSenateProposal
                                                    from: 1
                                                    to: modelData.public_land || 1
                                                    stepSize: 1
                                                    value: (modelData.params && modelData.params.amount_C !== undefined) ? modelData.params.amount_C : 1
                                                    onValueChanged: root.setBillParam(billKey, "amount_C", Math.round(value))
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
                        // WP-D AU-3/AU-1：移除 selectedProposalKeys.length>0（空批合法）；
                        // AI 分支（canTriggerAIProposer）按钮同样可点（frozen §11 Scenario B，见偏离 D-7）
                        enabled: (sessionStore.canCreateSenateProposal || sessionStore.canTriggerAIProposer) && !root.hasZeroValueLandSelection()
                        opacity: enabled ? 1.0 : 0.45
                        gradient: Gradient { GradientStop { position: 0.0; color: "#D9AA52" } GradientStop { position: 1.0; color: "#BC7B28" } }
                        Text {
                            anchors.centerIn: parent
                            text: root.proposalStepDone ? "\u2190 \u6cd5\u6848\u5df2\u63d0\u4ea4"
                                : (sessionStore.canTriggerAIProposer ? "AI \u6267\u653f\u5b98\u81ea\u52a8\u63d0\u6848 \u2192"
                                   : (root.selectedProposalKeys.length === 0 ? "\u672c\u4f1a\u671f\u4e0d\u63d0\u4ea4\u6cd5\u6848 \u2192 \u7ed3\u675f\u63d0\u6848" : "\u63d0\u4ea4\u9009\u4e2d\u6cd5\u6848 \u2192 \u79fb\u4ea4\u8868\u51b3"))
                            color: "#2C1E12"; font.pixelSize: 12; font.bold: true
                        }
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
                                delegate: ColumnLayout {
                                    Layout.fillWidth: true
                                    spacing: 2
                                    CheckBox { Layout.fillWidth: true; enabled: sessionStore.senateCurrentStep === "senate_vote"; text: (modelData.label || modelData.type) + root.voteParamDescription(modelData); checked: true; font.pixelSize: 12 }
                                    // WP-F R2-01（F-01A）：投票完成后（voted_all → 中间投影已产出）
                                    // Stage 2 即显示权威通过/未通过 + 支持率（纯展示除法，禁 QML 阈值判定）
                                    Text {
                                        visible: root.voteResultFor(modelData.id) !== null
                                        text: root.supportRateText(root.voteResultFor(modelData.id))
                                        color: "#766652"
                                        font.pixelSize: 10
                                        Layout.fillWidth: true
                                    }
                                }
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
                                    height: sessionStore.senateCurrentStep === "results" ? 66 : 48
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
                                            Text {
                                                visible: sessionStore.senateCurrentStep === "results"
                                                text: root.supportRateText(root.voteResultFor(modelData.id))
                                                color: "#766652"
                                                font.pixelSize: 10
                                                Layout.fillWidth: true
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
