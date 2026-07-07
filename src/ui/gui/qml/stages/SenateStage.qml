import QtQuick 2.15
import QtQuick.Controls 2.15
import QtQuick.Layouts 1.15

import "../i18n"
import "../components"

/**
 * SenateStage.qml — 元老院阶段 GUI
 * 设计规范 V2.0 §3.5
 *
 * 布局：
 *   顶部通栏 [公示区]
 *   3 个子环节面板并排 [①执政官提案] [②元老表决] [③保民官否决]
 *   各面板初始锁定状态(半透明+中央提示)，前置环节完成后自动解锁
 *
 * 关键交互：
 *   ① 提案 → 8种法案展开配置（下拉/滑块/只读）
 *   ② 表决 → 勾选同意(多选)，未勾选=否决
 *   ③ 否决 → 勾选否决(多选)，未勾选=同意
 *   两面死锁逃生 → 全部否决时出现⏭️结束按钮
 *   接管战争 → 绕过表决，提交即执行
 */
Rectangle {
    id: root
    color: theme.bgApp

    // ── 提案配置暂存 ──
    property var configuredBills: []
    property var pendingBillConfig: ({})

    // ── 交互模式可见性：仅当游戏真正到达元老院阶段时才显示 ──
    property bool _showInteractive: sessionStore.senateView.is_current_phase

    // ── 工具函数 ──
    function subStepIndex(step) {
        var map = { "announce": 0, "proposal": 1, "vote": 2, "veto": 3, "completed": 4 }
        return map[step] || 1
    }

    function hasVotableBills() {
        // 过滤掉接管战争（绕过表决）
        var bills = sessionStore.senateProposals || []
        for (var i = 0; i < bills.length; i++) {
            if (bills[i].type !== "takeover_war") return true
        }
        return false
    }

    function getVotableBills() {
        var bills = sessionStore.senateProposals || []
        return bills.filter(function(b) { return b.type !== "takeover_war" })
    }

    function getPassedBills() {
        var results = sessionStore.senateVoteResults || {}
        var passed = []
        var bills = sessionStore.senateProposals || []
        for (var i = 0; i < bills.length; i++) {
            var bid = bills[i].proposal_id
            if (results[bid] && results[bid].passed) {
                passed.push(bills[i])
            }
        }
        return passed
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

    function addConfiguredBill(type, params) {
        var entry = { type: type, label: billTypeLabel(type), params: params }
        var newList = configuredBills.slice()
        newList.push(entry)
        configuredBills = newList
    }

    function removeConfiguredBill(index) {
        var newList = configuredBills.slice()
        newList.splice(index, 1)
        configuredBills = newList
    }

    function submitAllProposals() {
        var bills = configuredBills
        if (bills.length === 0) {
            root.showFeedback("warning", "请先配置至少一项法案")
            return
        }
        var successCount = 0
        var failCount = 0
        for (var i = 0; i < bills.length; i++) {
            var bill = bills[i]
            var paramsJson = JSON.stringify(bill.params || {})
            var result = sessionStore.doSenatePropose(bill.type, paramsJson)
            if (result.success) {
                successCount++
            } else {
                failCount++
                console.log("Proposal failed:", bill.type, result.message)
            }
        }
        if (successCount > 0) {
            configuredBills = []
            root.showFeedback("success", "已提交 " + successCount + " 项法案")
        }
        if (failCount > 0) {
            root.showFeedback("error", failCount + " 项法案提交失败")
        }
    }

    function submitVotes() {
        var checked = []
        // collect checked vote IDs from voteCheckboxes
        var proposals = getVotableBills()
        for (var i = 0; i < proposals.length; i++) {
            var pid = proposals[i].proposal_id
            // We'll handle this via the checkbox component's state
        }
        var idsStr = JSON.stringify(selectedVoteIds.slice())
        var result = sessionStore.doSenateVote(idsStr)
        if (result.success) {
            root.showFeedback("success", "表决已提交")
        } else {
            root.showFeedback("error", result.message || "表决失败")
        }
    }

    function submitVetoes() {
        var idsStr = JSON.stringify(selectedVetoIds.slice())
        var result = sessionStore.doSenateVeto(idsStr)
        if (result.success) {
            root.showFeedback("success", "否决已提交")
        } else {
            root.showFeedback("error", result.message || "否决失败")
        }
    }

    function showFeedback(type, message) {
        // Use a simple signal approach — raise through logUiEvent temporarily
        sessionStore.logUiEvent("[Feedback:" + type + "] " + message)
    }

    // ── Vote/Veto selection tracking ──
    property var selectedVoteIds: []
    function toggleVoteId(pid) {
        var arr = selectedVoteIds.slice()
        var idx = arr.indexOf(pid)
        if (idx >= 0) arr.splice(idx, 1)
        else arr.push(pid)
        selectedVoteIds = arr
    }

    property var selectedVetoIds: []
    function toggleVetoId(pid) {
        var arr = selectedVetoIds.slice()
        var idx = arr.indexOf(pid)
        if (idx >= 0) arr.splice(idx, 1)
        else arr.push(pid)
        selectedVetoIds = arr
    }

    function isVoteChecked(pid) { return selectedVoteIds.indexOf(pid) >= 0 }
    function isVetoChecked(pid) { return selectedVetoIds.indexOf(pid) >= 0 }

    // ── Layout ──
    ColumnLayout {
        anchors.fill: parent
        anchors.margins: 8
        spacing: 4

        // =========================================================================
        // 顶部通栏：公示区（始终显示）
        // =========================================================================
        Rectangle {
            id: announcementBar
            Layout.fillWidth: true
            Layout.preferredHeight: 56
            color: theme.bgSurface1
            border.color: theme.borderNormal
            radius: theme.radius
            visible: true

            RowLayout {
                anchors.fill: parent
                anchors.margins: 8
                spacing: 10

                // 左：会议主持 + 标题
                ColumnLayout {
                    Layout.alignment: Qt.AlignVCenter
                    spacing: 2
                    Text {
                        text: "🏛️ 元老院议事"
                        color: theme.textPrimary
                        font.pixelSize: 13
                        font.family: theme.fontTitle
                        font.bold: true
                    }
                    // 会议主持
                    RowLayout {
                        spacing: 6
                        Text {
                            text: "会议主持："
                            color: theme.textMuted
                            font.pixelSize: 9
                        }
                        Text {
                            text: sessionStore.senatePresidingOfficer.name || "—"
                            color: theme.accentBronze
                            font.pixelSize: 9
                            font.bold: true
                        }
                        Text {
                            text: sessionStore.senatePresidingOfficer.office
                                ? "(" + sessionStore.senatePresidingOfficer.office + ")" : ""
                            color: theme.textSecondary
                            font.pixelSize: 9
                        }
                    }
                }

                // 中：席位占比
                ColumnLayout {
                    Layout.alignment: Qt.AlignVCenter
                    spacing: 2
                    Text {
                        text: "席位占比"
                        color: theme.textMuted
                        font.pixelSize: 9
                        font.bold: true
                    }
                    RowLayout {
                        spacing: 6
                        Repeater {
                            model: sessionStore.senateFactionLeaders || []
                            delegate: RowLayout {
                                spacing: 3
                                Rectangle {
                                    width: 6; height: 6; radius: 3
                                    color: {
                                        var fname = (modelData.faction_id || modelData.name || "")
                                        if (fname === "Optimates" || fname === "opt") return "#8B0000"
                                        if (fname === "Populares" || fname === "pop") return "#006400"
                                        if (fname === "Equites" || fname === "equ") return "#00008B"
                                        return theme.accentBronze
                                    }
                                }
                                Text {
                                    text: {
                                        var fname = (modelData.faction_id || modelData.name || "")
                                        return fname.substring(0, 4)
                                    }
                                    color: theme.textPrimary; font.pixelSize: 10
                                }
                            }
                        }
                    }
                }

                Item { Layout.fillWidth: true }

                // 右：当前阶段状态 + 只读/操作模式
                ColumnLayout {
                    Layout.alignment: Qt.AlignVCenter
                    spacing: 2
                    Text {
                        text: sessionStore.senateView.is_current_phase
                            ? (sessionStore.senateSubStep === "completed" ? "✅ 完成" : "当前")
                            : "🔍 只读"
                        color: sessionStore.senateView.is_current_phase
                            ? theme.statusSuccess : theme.statusWarning
                        font.pixelSize: 10
                        font.bold: true
                    }
                    Text {
                        text: sessionStore.senateView.is_current_phase
                            ? "环节 " + subStepIndex(sessionStore.senateSubStep) + "/3"
                            : "历史"
                        color: theme.textSecondary
                        font.pixelSize: 9
                    }
                }
            }

            // 通过法案公示（子环节3完成后显示）
            Rectangle {
                anchors.top: parent.bottom
                anchors.left: parent.left
                anchors.right: parent.right
                height: 40
                color: theme.bgSurface2
                border.color: theme.statusSuccess
                radius: 4
                visible: sessionStore.senateSubStep === "completed" ||
                        (sessionStore.senateVoteResults && Object.keys(sessionStore.senateVoteResults).length > 0)

                RowLayout {
                    anchors.fill: parent; anchors.margins: 8; spacing: 8
                    Text {
                        text: "📜 政府运作结果："
                        color: theme.textPrimary; font.pixelSize: 11; font.bold: true
                    }
                    Text {
                        text: {
                            var passed = getPassedBills()
                            if (passed.length === 0) return "⚠️ 无法案通过"
                            return passed.map(function(b) {
                                return billTypeLabel(b.type) + " #" + b.proposal_id
                            }).join("  |  ")
                        }
                        color: theme.statusSuccess; font.pixelSize: 11
                        Layout.fillWidth: true; elide: Text.ElideRight
                    }
                }
            }
        }

        // =========================================================================
        // 进度指示条
        // =========================================================================
        Rectangle {
            Layout.fillWidth: true
            Layout.preferredHeight: 24
            color: "transparent"
            visible: true

            RowLayout {
                anchors.centerIn: parent
                spacing: 6
                Repeater {
                    model: [
                        { id: "announce", label: "📢 公示" },
                        { id: "proposal", label: "① 提案" },
                        { id: "vote", label: "② 表决" },
                        { id: "veto", label: "③ 否决" },
                    ]
                    delegate: RowLayout {
                        spacing: 4
                        Rectangle {
                            width: 14; height: 14; radius: 7
                            color: {
                                var cur = subStepIndex(sessionStore.senateSubStep)
                                var idx = index
                                if (idx < cur) return theme.statusSuccess
                                if (idx === cur) return theme.accentBronze
                                return "#E8D5C4"
                            }
                            Text {
                                anchors.centerIn: parent
                                text: index === 0 ? "≡" : index
                                color: (index <= subStepIndex(sessionStore.senateSubStep)) ? "white" : theme.textMuted
                                font.pixelSize: 8; font.bold: true
                            }
                        }
                        Text {
                            text: modelData.label
                            color: (index <= subStepIndex(sessionStore.senateSubStep))
                                ? theme.textPrimary : theme.textMuted
                            font.pixelSize: 9
                            font.bold: (index) === subStepIndex(sessionStore.senateSubStep)
                        }
                        Text {
                            text: "→"
                            color: theme.textMuted; font.pixelSize: 9
                            visible: index < 3
                        }
                    }
                }
            }
        }

        // =========================================================================
        // 3 子环节面板并排（可操作模式）
        // =========================================================================
        RowLayout {
            Layout.fillWidth: true
            Layout.fillHeight: true
            spacing: 6
            visible: _showInteractive

            // ────────────────────────────────────────────────────────────────
            // 面板 ①：执政官提案
            // ────────────────────────────────────────────────────────────────
            Rectangle {
                id: panelProposal
                Layout.fillWidth: true; Layout.fillHeight: true
                color: theme.bgSurface1
                border.color: (sessionStore.senateSubStep === "proposal") ? theme.accentPrimaryDark : theme.borderNormal
                border.width: (sessionStore.senateSubStep === "proposal") ? 2 : 1
                radius: theme.radius
                clip: true

                ColumnLayout {
                    anchors.fill: parent
                    anchors.margins: 0
                    spacing: 0

                    // 面板头部
                    Rectangle {
                        Layout.fillWidth: true
                        Layout.preferredHeight: 24
                        color: (sessionStore.senateSubStep === "proposal") ? "#8B2500" : theme.bgSurface3

                        RowLayout {
                            anchors.fill: parent; anchors.margins: 4; spacing: 4
                            Rectangle {
                                width: 18; height: 18; radius: 9
                                color: "#FFD700"
                                Text {
                                    anchors.centerIn: parent
                                    text: "①"
                                    color: "#8B2500"
                                    font.pixelSize: 10; font.bold: true
                                }
                            }
                            Text {
                                text: "执政官提案"
                                color: (sessionStore.senateSubStep === "proposal") ? "white" : theme.textPrimary
                                font.pixelSize: 10; font.bold: true
                                Layout.fillWidth: true
                            }
                            Rectangle {
                                visible: sessionStore.senateSubStep === "proposal"
                                color: theme.statusSuccess; radius: 3
                                implicitWidth: 28; implicitHeight: 16
                                Text {
                                    anchors.centerIn: parent
                                    text: "可操作"
                                    color: "white"; font.pixelSize: 8; font.bold: true
                                }
                            }
                        }
                    }

                    // 面板内容
                    ColumnLayout {
                        Layout.fillWidth: true; Layout.fillHeight: true
                        Layout.margins: 8
                        spacing: 4

                        // 当前已配置的提案列表
                        ScrollView {
                            Layout.fillWidth: true
                            Layout.preferredHeight: configuredBills.length > 0 ? 60 : 0
                            clip: true
                            visible: configuredBills.length > 0

                            ColumnLayout {
                                width: parent.width; spacing: 2
                                Text {
                                    text: "已配置 (" + configuredBills.length + ")："
                                    color: theme.textMuted; font.pixelSize: 9
                                }
                                Repeater {
                                    model: configuredBills
                                    delegate: Rectangle {
                                        Layout.fillWidth: true; height: 20
                                        color: theme.bgSurface2; radius: 3
                                        RowLayout {
                                            anchors.fill: parent; anchors.margins: 4; spacing: 4
                                            Text {
                                                text: modelData.label
                                                color: theme.accentPrimary; font.pixelSize: 10
                                                Layout.fillWidth: true; elide: Text.ElideRight
                                            }
                                            Text {
                                                text: "✕"
                                                color: theme.statusError; font.pixelSize: 10
                                                MouseArea {
                                                    anchors.fill: parent
                                                    onClicked: root.removeConfiguredBill(index)
                                                    cursorShape: Qt.PointingHandCursor
                                                }
                                            }
                                        }
                                    }
                                }
                            }
                        }

                        // 可用法案类型
                        Text {
                            text: "可选法案："
                            color: theme.textMuted; font.pixelSize: 10
                        }

                        ScrollView {
                            Layout.fillWidth: true; Layout.fillHeight: true; clip: true
                            ColumnLayout {
                                width: parent.width; spacing: 3
                                Repeater {
                                    model: sessionStore.senateProposalTypes || []
                                    delegate: BillTypeDelegate {
                                        Layout.fillWidth: true
                                        Layout.preferredHeight: modelData._expanded ? 140 : 26
                                        billData: modelData
                                        subStep: sessionStore.senateSubStep
                                        canAct: sessionStore.senateCanPropose && sessionStore.isCurrentPlayer
                                        onAddRequested: function(type, params) {
                                            root.addConfiguredBill(type, params)
                                        }
                                    }
                                }
                            }
                        }
                    }

                    // 面板底部操作
                    Rectangle {
                        Layout.fillWidth: true
                        Layout.preferredHeight: 36
                        color: theme.bgSurface2
                        border.color: theme.borderNormal; border.width: 1

                        RowLayout {
                            anchors.fill: parent; anchors.margins: 6; spacing: 6
                            Text {
                                text: "已选 " + configuredBills.length + " 项"
                                color: theme.textSecondary; font.pixelSize: 10
                            }
                            Item { Layout.fillWidth: true }
                            Button {
                                text: "📤 提交选中法案"
                                enabled: configuredBills.length > 0 && sessionStore.senateCanPropose
                                        && sessionStore.isCurrentPlayer
                                contentItem: Text {
                                    text: parent.text; color: "white"; font.pixelSize: 10
                                    horizontalAlignment: Text.AlignHCenter
                                }
                                background: Rectangle {
                                    color: parent.enabled ? "#8B2500" : theme.bgSurface3
                                    radius: 4
                                }
                                onClicked: root.submitAllProposals()
                            }
                        }
                    }
                }

                // 锁定遮罩（非提案环节时）
                Rectangle {
                    anchors.fill: parent
                    color: Qt.rgba(0, 0, 0, 0.45)
                    visible: sessionStore.senateSubStep !== "proposal"
                    z: 10

                    ColumnLayout {
                        anchors.centerIn: parent
                        spacing: 6
                        Text { text: "🔒"; color: "white"; font.pixelSize: 24; horizontalAlignment: Text.AlignHCenter; Layout.fillWidth: true }
                        Text {
                            text: "等待提案完成"
                            color: "white"; font.pixelSize: 12; font.bold: true
                            horizontalAlignment: Text.AlignHCenter; Layout.fillWidth: true
                        }
                        Text {
                            text: "所有玩家表决后将自动解锁"
                            color: "#CCCCCC"; font.pixelSize: 10
                            horizontalAlignment: Text.AlignHCenter; Layout.fillWidth: true
                        }
                    }
                }
            }

            // ────────────────────────────────────────────────────────────────
            // 面板 ②：元老表决
            // ────────────────────────────────────────────────────────────────
            Rectangle {
                id: panelVote
                Layout.fillWidth: true; Layout.fillHeight: true
                color: theme.bgSurface1
                border.color: (sessionStore.senateSubStep === "vote") ? theme.accentPrimaryDark : theme.borderNormal
                border.width: (sessionStore.senateSubStep === "vote") ? 2 : 1
                radius: theme.radius
                clip: true

                ColumnLayout {
                    anchors.fill: parent; anchors.margins: 0; spacing: 0

                    // 面板头部
                    Rectangle {
                        Layout.fillWidth: true; Layout.preferredHeight: 24
                        color: (sessionStore.senateSubStep === "vote") ? "#8B2500" : theme.bgSurface3
                        RowLayout {
                            anchors.fill: parent; anchors.margins: 4; spacing: 4
                            Rectangle {
                                width: 18; height: 18; radius: 9; color: "#FFD700"
                                Text {
                                    anchors.centerIn: parent; text: "②"; color: "#8B2500"
                                    font.pixelSize: 10; font.bold: true
                                }
                            }
                            Text {
                                text: "元老表决"
                                color: (sessionStore.senateSubStep === "vote") ? "white" : theme.textPrimary
                                font.pixelSize: 10; font.bold: true
                                Layout.fillWidth: true
                            }
                            Rectangle {
                                visible: sessionStore.senateSubStep === "vote"
                                color: theme.statusSuccess; radius: 3
                                implicitWidth: 24; implicitHeight: 14
                                Text {
                                    anchors.centerIn: parent; text: "可操作"
                                    color: "white"; font.pixelSize: 7; font.bold: true
                                }
                            }
                        }
                    }

                    // 面板内容
                    ColumnLayout {
                        Layout.fillWidth: true; Layout.fillHeight: true
                        Layout.margins: 8; spacing: 6

                        Text {
                            text: { return "勾选同意，未勾选=否决（" + (hasVotableBills() ? getVotableBills().length : 0) + " 项）" }
                            color: theme.textSecondary; font.pixelSize: 10
                            visible: sessionStore.senateSubStep === "vote"
                            wrapMode: Text.Wrap
                            Layout.fillWidth: true
                        }

                        ScrollView {
                            Layout.fillWidth: true; Layout.fillHeight: true; clip: true
                            visible: sessionStore.senateSubStep === "vote" && getVotableBills().length > 0

                            ColumnLayout {
                                width: parent.width; spacing: 3
                                Repeater {
                                    model: getVotableBills()
                                    delegate: Rectangle {
                                        Layout.fillWidth: true; height: 28
                                        color: root.isVoteChecked(modelData.proposal_id) ? "#1A8B2500" : theme.bgSurface2
                                        border.color: root.isVoteChecked(modelData.proposal_id) ? theme.accentPrimary : theme.borderNormal
                                        radius: 4

                                        RowLayout {
                                            anchors.fill: parent; anchors.margins: 4; spacing: 6
                                            CheckBox {
                                                checked: root.isVoteChecked(modelData.proposal_id)
                                                onCheckedChanged: root.toggleVoteId(modelData.proposal_id)
                                            }
                                            Text {
                                                text: "#" + modelData.proposal_id + " " + billTypeLabel(modelData.type)
                                                color: theme.textPrimary; font.pixelSize: 10
                                                Layout.fillWidth: true; elide: Text.ElideRight
                                            }
                                            Text {
                                                text: modelData.description || ""
                                                color: theme.textMuted; font.pixelSize: 9
                                                Layout.maximumWidth: 100; elide: Text.ElideRight
                                            }
                                        }
                                    }
                                }
                            }
                        }

                        // 空状态：无法案可投票
                        Text {
                            visible: sessionStore.senateSubStep === "vote" && getVotableBills().length === 0
                            text: "当前无法案可供表决"
                            color: theme.textMuted; font.pixelSize: 11
                            Layout.alignment: Qt.AlignCenter
                        }

                        Item { Layout.fillHeight: true }

                        // 死锁逃生提示（表决全部否决）
                        Rectangle {
                            Layout.fillWidth: true; Layout.preferredHeight: 32
                            color: "#C451510F"
                            border.color: theme.statusError; radius: 4
                            visible: sessionStore.senateSubStep === "vote"
                                    && hasVotableBills()
                                    && selectedVoteIds.length === 0

                            RowLayout {
                                anchors.fill: parent; anchors.margins: 6; spacing: 6
                                Text {
                                    text: "⚠️"
                                    color: theme.statusError; font.pixelSize: 12
                                }
                                Text {
                                    text: "不勾选任何法案 = 全部否决，将触发死锁逃生"
                                    color: theme.statusError; font.pixelSize: 9
                                    wrapMode: Text.Wrap
                                    Layout.fillWidth: true
                                }
                            }
                        }

                        // 提交按钮
                        Button {
                            Layout.fillWidth: true
                            text: "🗳️ 确认表决 → 移交否决环节"
                            visible: sessionStore.senateSubStep === "vote"
                                    && hasVotableBills()
                                    && sessionStore.senateCanVote
                                    && sessionStore.isCurrentPlayer
                            contentItem: Text {
                                text: parent.text; color: "white"; font.pixelSize: 10
                                horizontalAlignment: Text.AlignHCenter
                            }
                            background: Rectangle {
                                color: parent.enabled ? "#8B2500" : theme.bgSurface3; radius: 4
                            }
                            onClicked: root.submitVotes()
                        }

                        // 死锁逃生按钮（全部否决时）
                        Button {
                            Layout.fillWidth: true
                            text: "⏭️ 全部否决 → 结束元老院阶段"
                            visible: sessionStore.senateSubStep === "vote"
                                    && hasVotableBills()
                                    && selectedVoteIds.length === 0
                                    && sessionStore.senateCanVote
                                    && sessionStore.isCurrentPlayer
                            contentItem: Text {
                                text: parent.text; color: "white"; font.pixelSize: 10
                                horizontalAlignment: Text.AlignHCenter
                            }
                            background: Rectangle {
                                color: theme.statusWarning; radius: 4
                            }
                            onClicked: {
                                var result = sessionStore.doSenateVote("[]")
                                if (result.success) {
                                    root.showFeedback("info", "所有法案被否决，进入死锁逃生模式")
                                }
                            }
                        }
                    }
                }

                // 锁定遮罩（非表决环节）
                Rectangle {
                    anchors.fill: parent
                    color: Qt.rgba(0, 0, 0, 0.45)
                    visible: sessionStore.senateSubStep !== "vote"
                    z: 10

                    ColumnLayout {
                        anchors.centerIn: parent; spacing: 6
                        Text { text: "🔒"; color: "white"; font.pixelSize: 24; horizontalAlignment: Text.AlignHCenter; Layout.fillWidth: true }
                        Text {
                            text: "等待表决开始"
                            color: "white"; font.pixelSize: 12; font.bold: true
                            horizontalAlignment: Text.AlignHCenter; Layout.fillWidth: true
                        }
                        Text {
                            text: sessionStore.senateSubStep === "proposal" ? "执政官提交提案后将自动解锁" : "已完成"
                            color: "#CCCCCC"; font.pixelSize: 10
                            horizontalAlignment: Text.AlignHCenter; Layout.fillWidth: true
                        }
                    }
                }
            }

            // ────────────────────────────────────────────────────────────────
            // 面板 ③：保民官否决
            // ────────────────────────────────────────────────────────────────
            Rectangle {
                id: panelVeto
                Layout.fillWidth: true; Layout.fillHeight: true
                color: theme.bgSurface1
                border.color: (sessionStore.senateSubStep === "veto") ? theme.accentPrimaryDark : theme.borderNormal
                border.width: (sessionStore.senateSubStep === "veto") ? 2 : 1
                radius: theme.radius
                clip: true

                ColumnLayout {
                    anchors.fill: parent; anchors.margins: 0; spacing: 0

                    Rectangle {
                        Layout.fillWidth: true; Layout.preferredHeight: 24
                        color: (sessionStore.senateSubStep === "veto") ? "#8B2500" : theme.bgSurface3
                        RowLayout {
                            anchors.fill: parent; anchors.margins: 4; spacing: 4
                            Rectangle {
                                width: 18; height: 18; radius: 9; color: "#FFD700"
                                Text {
                                    anchors.centerIn: parent; text: "③"; color: "#8B2500"
                                    font.pixelSize: 10; font.bold: true
                                }
                            }
                            Text {
                                text: "保民官否决"
                                color: (sessionStore.senateSubStep === "veto") ? "white" : theme.textPrimary
                                font.pixelSize: 10; font.bold: true
                                Layout.fillWidth: true
                            }
                            Rectangle {
                                visible: sessionStore.senateSubStep === "veto"
                                color: theme.statusSuccess; radius: 3
                                implicitWidth: 24; implicitHeight: 14
                                Text {
                                    anchors.centerIn: parent; text: "可操作"
                                    color: "white"; font.pixelSize: 7; font.bold: true
                                }
                            }
                        }
                    }

                    ColumnLayout {
                        Layout.fillWidth: true; Layout.fillHeight: true
                        Layout.margins: 8; spacing: 6

                        Text {
                            text: { return "勾选否决，未勾选=同意（" + getPassedBills().length + " 项通过）" }
                            color: theme.textSecondary; font.pixelSize: 10
                            visible: sessionStore.senateSubStep === "veto"
                            wrapMode: Text.Wrap; Layout.fillWidth: true
                        }

                        ScrollView {
                            Layout.fillWidth: true; Layout.fillHeight: true; clip: true
                            visible: sessionStore.senateSubStep === "veto" && getPassedBills().length > 0

                            ColumnLayout {
                                width: parent.width; spacing: 3
                                Repeater {
                                    model: getPassedBills()
                                    delegate: Rectangle {
                                        Layout.fillWidth: true; height: 28
                                        color: root.isVetoChecked(modelData.proposal_id) ? "#1A8B2500" : theme.bgSurface2
                                        border.color: root.isVetoChecked(modelData.proposal_id) ? theme.statusError : theme.borderNormal
                                        radius: 4

                                        RowLayout {
                                            anchors.fill: parent; anchors.margins: 4; spacing: 6
                                            CheckBox {
                                                checked: root.isVetoChecked(modelData.proposal_id)
                                                onCheckedChanged: root.toggleVetoId(modelData.proposal_id)
                                            }
                                            Text {
                                                text: "#" + modelData.proposal_id + " " + billTypeLabel(modelData.type)
                                                color: theme.textPrimary; font.pixelSize: 10
                                                Layout.fillWidth: true; elide: Text.ElideRight
                                            }
                                            Text {
                                                text: modelData.description || ""
                                                color: theme.textMuted; font.pixelSize: 9
                                                Layout.maximumWidth: 100; elide: Text.ElideRight
                                            }
                                        }
                                    }
                                }
                            }
                        }

                        // 空状态
                        Text {
                            visible: sessionStore.senateSubStep === "veto" && getPassedBills().length === 0
                            text: "无法案通过，无需否决"
                            color: theme.textMuted; font.pixelSize: 11
                            Layout.alignment: Qt.AlignCenter
                        }

                        // 否决环节跳过提示（表决环节全部否决时）
                        Text {
                            visible: sessionStore.senateSubStep !== "veto"
                                    && sessionStore.senateIsDeadlocked
                            text: "⚠️ 所有法案均被否决，跳过否决环节"
                            color: theme.statusWarning; font.pixelSize: 10; font.bold: true
                            Layout.fillWidth: true; wrapMode: Text.Wrap
                            Layout.alignment: Qt.AlignCenter
                        }

                        Item { Layout.fillHeight: true }

                        // 确认否决按钮
                        Button {
                            Layout.fillWidth: true
                            text: "🛡️ 确认否决 → 公示结果"
                            visible: sessionStore.senateSubStep === "veto"
                                    && sessionStore.senateCanVeto
                                    && sessionStore.isCurrentPlayer
                            contentItem: Text {
                                text: parent.text; color: "white"; font.pixelSize: 10
                                horizontalAlignment: Text.AlignHCenter
                            }
                            background: Rectangle {
                                color: parent.enabled ? "#8B2500" : theme.bgSurface3; radius: 4
                            }
                            onClicked: root.submitVetoes()
                        }

                        // 死锁逃生：否决环节全部否决
                        Rectangle {
                            Layout.fillWidth: true; Layout.preferredHeight: 32
                            color: "#C451510F"
                            border.color: theme.statusError; radius: 4
                            visible: sessionStore.senateSubStep === "veto"
                                    && getPassedBills().length > 0
                                    && selectedVetoIds.length === getPassedBills().length
                                    && selectedVetoIds.length > 0

                            Text {
                                anchors.centerIn: parent
                                text: "⚠️ 全部否决将触发死锁逃生"
                                color: theme.statusError; font.pixelSize: 10; font.bold: true
                            }
                        }

                        Button {
                            Layout.fillWidth: true
                            text: "⏭️ 全部否决 → 结束元老院阶段"
                            visible: sessionStore.senateSubStep === "veto"
                                    && getPassedBills().length > 0
                                    && selectedVetoIds.length === getPassedBills().length
                                    && selectedVetoIds.length > 0
                                    && sessionStore.senateCanVeto
                                    && sessionStore.isCurrentPlayer
                            contentItem: Text {
                                text: parent.text; color: "white"; font.pixelSize: 10
                                horizontalAlignment: Text.AlignHCenter
                            }
                            background: Rectangle {
                                color: theme.statusWarning; radius: 4
                            }
                            onClicked: {
                                var idsStr = JSON.stringify(selectedVetoIds.slice())
                                var result = sessionStore.doSenateVeto(idsStr)
                                if (result.success) {
                                    root.showFeedback("info", "所有法案被否决，阶段提前结束")
                                    // Trigger resolve
                                    sessionStore.doSenateResolve()
                                }
                            }
                        }

                        // 阶段完成按钮（子环节3完成后）
                        Button {
                            Layout.fillWidth: true
                            text: "✅ 阶段完成"
                            visible: sessionStore.senateSubStep === "completed"
                            contentItem: Text {
                                text: parent.text; color: "white"; font.pixelSize: 11
                                horizontalAlignment: Text.AlignHCenter
                            }
                            background: Rectangle { color: theme.statusSuccess; radius: 4 }
                            onClicked: sessionStore.doSenateResolve()
                        }
                    }
                }

                // 锁定遮罩（非否决环节）
                Rectangle {
                    anchors.fill: parent
                    color: Qt.rgba(0, 0, 0, 0.45)
                    visible: sessionStore.senateSubStep !== "veto" && sessionStore.senateSubStep !== "completed"
                    z: 10

                    ColumnLayout {
                        anchors.centerIn: parent; spacing: 6
                        Text { text: "🔒"; color: "white"; font.pixelSize: 24; horizontalAlignment: Text.AlignHCenter; Layout.fillWidth: true }
                        Text {
                            text: "等待否决开始"
                            color: "white"; font.pixelSize: 12; font.bold: true
                            horizontalAlignment: Text.AlignHCenter; Layout.fillWidth: true
                        }
                        Text {
                            text: sessionStore.senateSubStep === "proposal" ? "提案完成后将进入表决" :
                                   sessionStore.senateSubStep === "vote" ? "表决完成后将自动解锁" : ""
                            color: "#CCCCCC"; font.pixelSize: 10
                            horizontalAlignment: Text.AlignHCenter; Layout.fillWidth: true
                        }
                    }
                }

                // 已完成标记（子环节3完成后）
                Rectangle {
                    anchors.fill: parent
                    color: Qt.rgba(0, 0, 0, 0.25)
                    visible: sessionStore.senateSubStep === "completed"
                    z: 10

                    ColumnLayout {
                        anchors.centerIn: parent; spacing: 6
                        Text { text: "✅"; color: theme.statusSuccess; font.pixelSize: 32; horizontalAlignment: Text.AlignHCenter; Layout.fillWidth: true }
                        Text {
                            text: "元老院阶段已完成"
                            color: "white"; font.pixelSize: 13; font.bold: true
                            horizontalAlignment: Text.AlignHCenter; Layout.fillWidth: true
                        }
                    }
                }
            }
        }

        // =========================================================================
        // 只读模式（非当前阶段时显示）
        // =========================================================================
        ColumnLayout {
            Layout.fillWidth: true; Layout.fillHeight: true
            spacing: 8
            visible: !_showInteractive

            // 只读模式头部状态
            Rectangle {
                Layout.fillWidth: true
                Layout.preferredHeight: 60
                color: theme.bgSurface1
                border.color: theme.borderNormal
                radius: theme.radius

                ColumnLayout {
                    anchors.fill: parent; anchors.margins: 10; spacing: 4
                    Text {
                        text: sessionStore.senateView.summary
                            ? (sessionStore.senateView.summary.message || "") : ""
                        color: theme.accentPrimary; font.pixelSize: 13; font.bold: true
                        Layout.fillWidth: true; wrapMode: Text.Wrap
                    }
                    Text {
                        text: {
                            var v = sessionStore.senateView
                            var leaders = v.faction_leaders || []
                            var wars = (v.active_foreign_wars || []).length
                            var threats = (v.war_threats || []).length
                            return "派系领袖 " + leaders.length + " · 活跃战争 " + wars + " · 战争威胁 " + threats
                        }
                        color: theme.textSecondary; font.pixelSize: 11
                        Layout.fillWidth: true; wrapMode: Text.Wrap
                    }
                }
            }

            // 只读内容滚动区
            ScrollView {
                Layout.fillWidth: true; Layout.fillHeight: true; clip: true
                ColumnLayout {
                    width: parent.width; spacing: 8
                    SenateReadOnlySection { title: "🏛️ 会议主持"; items: [sessionStore.senatePresidingOfficer] }
                    SenateReadOnlySection { title: "🏛️ 派系领袖"; items: sessionStore.senateFactionLeaders }
                    SenateReadOnlySection { title: "⚔️ 活跃战争"; items: sessionStore.senateActiveForeignWars }
                    SenateReadOnlySection { title: "⚠️ 战争威胁"; items: sessionStore.senateWarThreats }
                    SenateReadOnlySection { title: "☮️ 待批和约"; items: sessionStore.senatePendingPeaceTreaties }
                    SenateReadOnlySection { title: "🏛️ 总督空缺"; items: sessionStore.senateGovernorVacancies }
                    SenateReadOnlySection { title: "📦 待发包合同"; items: sessionStore.senatePendingContracts }
                }
            }

            Text {
                text: "※ 仅浏览已有信息，实际操作在元老院阶段进行"
                color: theme.textMuted; font.pixelSize: 10; wrapMode: Text.Wrap
                Layout.fillWidth: true
            }
        }
    }

    // ── 底部提示（始终可见） ──
    Text {
        anchors.bottom: parent.bottom; anchors.right: parent.right
        anchors.margins: 8
        text: _showInteractive
            ? ("当前玩家: " + (sessionStore.viewerFactionName || "") + " | " + (sessionStore.isCurrentPlayer ? "🎯 你的回合" : "⏳ 等待其他玩家"))
            : ""
        color: theme.textMuted; font.pixelSize: 9
        visible: _showInteractive
    }
}
