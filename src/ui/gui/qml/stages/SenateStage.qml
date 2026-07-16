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
            if (hasSelectedProposal(options[i].key)) rows.push(options[i])
        }
        return rows
    }

    function syncDefaultSelection() {
        var options = sessionStore.senateProposalOptions || []
        var next = []
        for (var i = 0; i < options.length; i++) {
            if (i < 3 || options[i].type === "land") next.push(options[i].key)
        }
        selectedProposalKeys = next
    }

    Component.onCompleted: syncDefaultSelection()

    Connections {
        target: sessionStore
        function onSenateViewChanged() {
            if (sessionStore.senateCurrentStep === "proposal" && selectedProposalKeys.length === 0) root.syncDefaultSelection()
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
                    text: "会议主持：" + (sessionStore.senatePresidingOfficer.name ? sessionStore.senatePresidingOfficer.name : "暂无")
                        + "（" + (sessionStore.senatePresidingOfficer.office || "官职未定") + "）"
                    color: "#2C1E12"
                    font.pixelSize: 12
                    Layout.fillWidth: true
                    wrapMode: Text.Wrap
                }
                Text { text: root.seatLine(); color: "#9A2D0A"; font.pixelSize: 12; font.bold: true; Layout.fillWidth: true; wrapMode: Text.Wrap }
                Text { text: "※ 最终通过法案及政府运作结果将在此展示"; color: "#766652"; font.pixelSize: 11; Layout.fillWidth: true; wrapMode: Text.Wrap }
            }
        }

        Rectangle {
            visible: sessionStore.senateCurrentStep === "results"
            Layout.fillWidth: true
            Layout.preferredHeight: 118
            color: "#FFF7E9"
            border.color: "#D9AF63"
            border.width: 1
            radius: 6

            ColumnLayout {
                anchors.fill: parent
                anchors.margins: 10
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
                Rectangle {
                    Layout.fillWidth: true
                    Layout.fillHeight: true
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

        RowLayout {
            Layout.fillWidth: true
            Layout.preferredHeight: sessionStore.senateCurrentStep === "results" ? 330 : 460
            Layout.minimumHeight: sessionStore.senateCurrentStep === "results" ? 320 : 440
            Layout.maximumHeight: sessionStore.senateCurrentStep === "results" ? 330 : 460
            spacing: 12

            SenateWorkPanel {
                title: "1  执政官提案 · 配置参数"
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
                                        CheckBox {
                                            visible: sessionStore.senateCurrentStep === "proposal"
                                            enabled: sessionStore.canCreateSenateProposal
                                            checked: root.hasSelectedProposal(modelData.key)
                                            onToggled: root.setProposalSelected(modelData.key, checked)
                                        }
                                        Text {
                                            visible: sessionStore.senateCurrentStep !== "proposal"
                                            text: "\u2713"
                                            color: theme.statusSuccess
                                            font.pixelSize: 13
                                            font.bold: true
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
                    Rectangle {
                        Layout.fillWidth: true
                        Layout.preferredHeight: 26
                        radius: 4
                        enabled: sessionStore.canCreateSenateProposal && root.selectedProposalKeys.length > 0
                        opacity: enabled ? 1.0 : 0.45
                        gradient: Gradient { GradientStop { position: 0.0; color: "#D9AA52" } GradientStop { position: 1.0; color: "#BC7B28" } }
                        Text { anchors.centerIn: parent; text: root.proposalStepDone ? "\u2190 \u6cd5\u6848\u5df2\u63d0\u4ea4" : "\u63d0\u4ea4\u9009\u4e2d\u6cd5\u6848 \u2192 \u79fb\u4ea4\u8868\u51b3"; color: "#2C1E12"; font.pixelSize: 12; font.bold: true }
                        MouseArea { anchors.fill: parent; enabled: parent.enabled; onClicked: sessionStore.doSubmitSenateProposals(root.selectedProposals()) }
                    }
                }
            }

            SenateWorkPanel {
                title: "2  元老院表决"
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
                                delegate: CheckBox { Layout.fillWidth: true; enabled: sessionStore.senateCurrentStep === "senate_vote"; text: modelData.label || modelData.type; checked: true; font.pixelSize: 12 }
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
            Text { anchors.verticalCenter: parent.verticalCenter; anchors.left: parent.left; anchors.leftMargin: 10; text: title; color: "white"; font.pixelSize: 13; font.bold: true }
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
