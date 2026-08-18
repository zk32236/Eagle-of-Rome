import QtQuick 2.15
import QtQuick.Controls 2.15
import QtQuick.Layouts 1.15

import "../components"

Rectangle {
    id: root
    objectName: "populationStageRoot"
    color: "transparent"

    property var offices: ["consul", "censor", "praetor", "quaestor", "tribune"]
    property var selectedVotes: ({})
    // EOR-DEFECT-20260817-01 Fix A (P0): 年度切换哨兵 —— 上次快照所见年度（turnNumber）
    property int _lastSeenTurn: 0
    property color actionButtonTop: "#FFF9EC"
    property color actionButtonBottom: "#E8D5B8"
    property color actionButtonHover: "#F4DFB8"

    FactionStyle { id: factionStyle }

    // EOR-DEFECT-20260817-01 Fix A (P0): 年度推进（turnNumber 变化）→ 清空跨年残留的选票状态。
    // 守卫 `turnNumber !== _lastSeenTurn`：仅在真实年度切换时重置一次；
    // 同年度内快照刷新 / 多玩家 handoff（turnNumber 不变）不触发。
    // 重置后，无候选人 office 在 selectedVotes 中键缺失 → 提交时 .get(office, 0) 回落 ABSTAIN。
    Connections {
        target: sessionStore
        function onSnapshotChanged() {
            if (sessionStore.turnNumber !== root._lastSeenTurn) {
                root._lastSeenTurn = sessionStore.turnNumber
                root.selectedVotes = ({})
            }
        }
    }

    // 组件创建时同步当前年度，避免把「创建后首个快照」误判为年度切换。
    Component.onCompleted: root._lastSeenTurn = sessionStore.turnNumber

    function officeName(office) {
        var names = {
            "consul": "执政官",
            "censor": "监察官",
            "praetor": "大法官",
            "quaestor": "财务官",
            "tribune": "保民官"
        }
        return names[office] || office
    }

    function officeIcon(office) {
        var icons = {
            "consul": "🛡",
            "censor": "📜",
            "praetor": "⚖",
            "quaestor": "💰",
            "tribune": "🛡"
        }
        return icons[office] || "🏛"
    }

    function factionShort(name) {
        return factionStyle.factionShort(name)
    }

    function candidatesForOffice(office) {
        var rows = []
        var all = sessionStore.populationCandidates || []
        for (var i = 0; i < all.length; i++) {
            if (all[i].office === office) rows.push(all[i])
        }
        return rows
    }

    function myCandidateRows() {
        var rows = []
        var all = sessionStore.populationCandidates || []
        for (var i = 0; i < all.length; i++) {
            if (all[i].faction_id === sessionStore.viewerFactionId) rows.push(all[i])
        }
        return rows
    }

    function campaignSubmitted() {
        return sessionStore.populationCurrentStep !== "campaign"
            || sessionStore.populationResolved
            || (sessionStore.populationCampaigns || []).length > 0
    }

    function votedFigureId(office) {
        var votes = sessionStore.myVotes || {}
        if (votes[office]) return votes[office]
        if (selectedVotes[office]) return selectedVotes[office]
        return 0
    }

    function selectCandidate(office, figureId) {
        var next = {}
        var keys = Object.keys(selectedVotes || {})
        for (var i = 0; i < keys.length; i++) {
            next[keys[i]] = selectedVotes[keys[i]]
        }
        next[office] = figureId
        root.selectedVotes = next
    }

    function resultForOffice(office) {
        var results = sessionStore.populationElectionResults || []
        for (var i = 0; i < results.length; i++) {
            if (results[i].office === office) return results[i]
        }
        return null
    }

    function scoreForCandidate(figureId, office) {
        if (!sessionStore.populationResolved) return undefined
        var results = sessionStore.populationElectionResults || []
        for (var i = 0; i < results.length; i++) {
            if (results[i].office !== office) continue
            var candidates = results[i].candidates || []
            for (var j = 0; j < candidates.length; j++) {
                if (candidates[j].figure_id === figureId) return candidates[j].score
            }
        }
        return undefined
    }

    function influenceText(rows) {
        if (!rows || rows.length === 0) return "Optimates -- · Populares -- · Equites --"
        var parts = []
        for (var i = 0; i < rows.length; i++) {
            parts.push((rows[i].short_name || factionShort(rows[i].name)) + " " + rows[i].total_influence)
        }
        return parts.join(" · ")
    }

    ColumnLayout {
        objectName: "populationStageRoot"
        anchors.fill: parent
        spacing: 10

        Rectangle {
            id: announcement
            objectName: "populationAnnouncement"
            Layout.fillWidth: true
            Layout.preferredHeight: 88
            color: "#FFF9EC"
            radius: 6
            border.color: "#D4A574"
            border.width: 1

            ColumnLayout {
                anchors.fill: parent
                anchors.margins: 12
                spacing: 5

                Text {
                    text: sessionStore.populationResolved ? "✨ 选举已完成！" : "📢 今年举行庆典？→ 广场阶段已投票决定：是"
                    color: "#2C1E12"
                    font.pixelSize: 13
                    font.bold: sessionStore.populationResolved
                }
                Text {
                    text: sessionStore.populationResolved
                        ? "📊 选举后派系影响力：" + influenceText(sessionStore.populationInfluenceAfter)
                        : "📊 选举前派系影响力：" + influenceText(sessionStore.populationInfluenceBefore)
                    color: "#2C1E12"
                    font.pixelSize: 12
                    font.bold: true
                    wrapMode: Text.Wrap
                    Layout.fillWidth: true
                }
                Text {
                    visible: sessionStore.populationResolved
                    text: "✅ 结果已更新到候选人信息表"
                    color: "#1E7A2D"
                    font.pixelSize: 12
                    font.bold: true
                }
            }
        }

        // ---------- 战场指挥官转换结果（只读展示） ----------
        Rectangle {
            id: conversionBanner
            objectName: "populationCommanderConversion"
            visible: sessionStore.populationResolved && sessionStore.populationConversionResult.total > 0
            Layout.fillWidth: true
            Layout.preferredHeight: conversionInner.implicitHeight + 16
            color: "#F0F0E0"
            radius: 6
            border.color: "#B8A880"
            border.width: 1

            ColumnLayout {
                id: conversionInner
                anchors.fill: parent
                anchors.margins: 10
                spacing: 4

                Text {
                    text: "🔄 战场指挥官转换"
                    color: "#5A4A2E"
                    font.pixelSize: 13
                    font.bold: true
                }

                Repeater {
                    model: sessionStore.populationConversionResult.converted || []
                    delegate: Text {
                        text: {
                            var item = modelData
                            var oldName = item.old_office === "consul" ? "执政官" : "大法官"
                            var newName = item.new_office === "proconsul" ? "代执政官" : "代大法官"
                            var warInfo = item.war_id ? "（战争 " + item.war_id + "）" : ""
                            return "• " + item.name + "：" + oldName + " → " + newName + "，继续指挥" + warInfo
                        }
                        color: "#2C1E12"
                        font.pixelSize: 12
                        wrapMode: Text.WordWrap
                        Layout.fillWidth: true
                    }
                }
            }
        }

        Text {
            text: "🏛 候选人信息"
            color: "#681B07"
            font.pixelSize: 14
            font.bold: true
            Layout.fillWidth: true
        }

        Rectangle {
            id: candidateTable
            objectName: "populationCandidateTable"
            Layout.fillWidth: true
            Layout.preferredHeight: 206
            clip: true
            color: "transparent"

            ColumnLayout {
                anchors.fill: parent
                spacing: 3

                RowLayout {
                    Layout.fillWidth: true
                    Layout.preferredHeight: 20
                    spacing: 0
                    Text { text: "官职"; color: "#766652"; font.pixelSize: 11; Layout.preferredWidth: 172 }
                    Text { text: "候选人"; color: "#766652"; font.pixelSize: 11; Layout.preferredWidth: 220 }
                    Text { text: "军略"; color: "#766652"; font.pixelSize: 11; horizontalAlignment: Text.AlignHCenter; Layout.preferredWidth: 64 }
                    Text { text: "智略"; color: "#766652"; font.pixelSize: 11; horizontalAlignment: Text.AlignHCenter; Layout.preferredWidth: 64 }
                    Text { text: "魅力"; color: "#766652"; font.pixelSize: 11; horizontalAlignment: Text.AlignHCenter; Layout.preferredWidth: 64 }
                    Text { text: "热忱"; color: "#766652"; font.pixelSize: 11; horizontalAlignment: Text.AlignHCenter; Layout.preferredWidth: 64 }
                    Text { text: "影响力"; color: "#766652"; font.pixelSize: 11; horizontalAlignment: Text.AlignHCenter; Layout.preferredWidth: 72 }
                    Text { text: "派系"; color: "#766652"; font.pixelSize: 11; Layout.preferredWidth: 78 }
                    Text { text: "选举结果"; color: "#766652"; font.pixelSize: 11; Layout.fillWidth: true }
                }

                Flickable {
                    Layout.fillWidth: true
                    Layout.fillHeight: true
                    clip: true
                    contentWidth: width
                    contentHeight: candidateRows.implicitHeight
                    boundsBehavior: Flickable.StopAtBounds

                    ScrollBar.vertical: ScrollBar {
                        policy: ScrollBar.AsNeeded
                    }

                    ColumnLayout {
                        id: candidateRows
                        width: parent.width
                        spacing: 3

                Repeater {
                    model: root.offices
                    delegate: Rectangle {
                        Layout.fillWidth: true
                        Layout.preferredHeight: Math.max(36, candidatesColumn.implicitHeight + 12)
                        color: "#FFF5E6"
                        radius: 4
                        border.color: "#D9B77A"
                        border.width: 1

                        property var rows: root.candidatesForOffice(modelData)
                        property var result: root.resultForOffice(modelData)

                        RowLayout {
                            anchors.fill: parent
                            anchors.leftMargin: 10
                            anchors.rightMargin: 10
                            spacing: 0

                            Text {
                                text: root.officeIcon(modelData) + " " + root.officeName(modelData)
                                color: "#2C1E12"
                                font.pixelSize: 12
                                font.bold: true
                                Layout.preferredWidth: 162
                            }

                            Column {
                                id: candidatesColumn
                                Layout.preferredWidth: 220
                                Repeater {
                                    model: rows
                                    Text {
                                        text: {
                                            var name = modelData.name
                                            if (!sessionStore.populationResolved) return name
                                            var score = root.scoreForCandidate(modelData.id, modelData.office)
                                            return score !== undefined ? (name + " · " + score) : name
                                        }
                                        color: "#1F1A12"
                                        font.pixelSize: 12
                                        font.bold: sessionStore.populationResolved && root.scoreForCandidate(modelData.id, modelData.office) !== undefined
                                    }
                                }
                                Text {
                                    visible: rows.length === 0
                                    text: "无候选人（空缺）"
                                    color: "#B88976"
                                    font.pixelSize: 12
                                    font.italic: true
                                }
                            }

                            Column { Layout.preferredWidth: 64; Repeater { model: rows; Text { text: modelData.martial || 0; color: "#2C1E12"; font.pixelSize: 12; horizontalAlignment: Text.AlignHCenter; width: 64 } } }
                            Column { Layout.preferredWidth: 64; Repeater { model: rows; Text { text: modelData.intelligence || 0; color: "#2C1E12"; font.pixelSize: 12; horizontalAlignment: Text.AlignHCenter; width: 64 } } }
                            Column { Layout.preferredWidth: 64; Repeater { model: rows; Text { text: modelData.charisma || 0; color: "#2C1E12"; font.pixelSize: 12; horizontalAlignment: Text.AlignHCenter; width: 64 } } }
                            Column { Layout.preferredWidth: 64; Repeater { model: rows; Text { text: modelData.zeal || 0; color: "#2C1E12"; font.pixelSize: 12; horizontalAlignment: Text.AlignHCenter; width: 64 } } }
                            Column { Layout.preferredWidth: 72; Repeater { model: rows; Text { text: modelData.influence || 0; color: "#2C1E12"; font.pixelSize: 12; horizontalAlignment: Text.AlignHCenter; width: 72 } } }
                            Column {
                                Layout.preferredWidth: 78
                                Repeater {
                                    model: rows
                                    Text {
                                        text: root.factionShort(modelData.faction_name)
                                        color: factionStyle.factionColor(modelData.faction_name)
                                        font.pixelSize: 12
                                        font.bold: true
                                    }
                                }
                            }

                            Text {
                                text: result ? ("✅ " + result.figure_name) : "—"
                                color: result ? "#008000" : "#2C1E12"
                                font.pixelSize: 12
                                font.bold: !!result
                                elide: Text.ElideRight
                                Layout.fillWidth: true
                            }
                        }
                    }
                }
                    }
                }
            }
        }

        RowLayout {
            Layout.fillWidth: true
            Layout.fillHeight: true
            spacing: 12

            Rectangle {
                id: campaignPanel
                objectName: "populationCampaignPanel"
                Layout.fillWidth: true
                Layout.fillHeight: true
                color: "#FFF5E6"
                radius: 6
                border.color: "#D4A574"
                border.width: 1

                ColumnLayout {
                    anchors.fill: parent
                    spacing: 0

                    Rectangle {
                        Layout.fillWidth: true
                        Layout.preferredHeight: 36
                        radius: 5
                        color: "#8B2500"
                        Text {
                            anchors.verticalCenter: parent.verticalCenter
                            anchors.left: parent.left
                            anchors.leftMargin: 12
                            text: "① 庆典赞助"
                            color: "#FFF2CC"
                            font.pixelSize: 13
                            font.bold: true
                        }
                    }

                    Flickable {
                        id: campaignFlickable
                        objectName: "populationCampaignFlickable"
                        Layout.fillWidth: true
                        Layout.fillHeight: true
                        clip: true
                        contentWidth: width
                        contentHeight: campaignRows.implicitHeight + 10

                        ScrollBar.vertical: ScrollBar {
                            objectName: "populationCampaignScrollBar"
                            height: campaignFlickable.height
                            size: campaignFlickable.visibleArea.heightRatio
                            position: campaignFlickable.visibleArea.yPosition
                            policy: ScrollBar.AsNeeded
                        }

                        ColumnLayout {
                            id: campaignRows
                            width: parent.width
                            spacing: 4
                            anchors.margins: 10

                            RowLayout {
                                Layout.fillWidth: true
                                Layout.topMargin: 8
                                Text { text: "候选人"; color: "#766652"; font.pixelSize: 11; Layout.fillWidth: true }
                                Text { text: "竞选官职"; color: "#766652"; font.pixelSize: 11; Layout.preferredWidth: 90 }
                                Text { text: "个人财富"; color: "#766652"; font.pixelSize: 11; Layout.preferredWidth: 76 }
                                Text { text: "赞助金额"; color: "#766652"; font.pixelSize: 11; Layout.preferredWidth: 82 }
                            }

                            Repeater {
                                id: campaignRepeater
                                model: root.myCandidateRows()
                                delegate: Rectangle {
                                    Layout.fillWidth: true
                                    Layout.preferredHeight: 36
                                    color: "#FFF9EC"
                                    radius: 4
                                    border.color: "#E0BE80"
                                    border.width: 1

                                    property int figureId: modelData.id
                                    property int amount: sponsorInput.text === "" ? 0 : parseInt(sponsorInput.text)

                                    RowLayout {
                                        anchors.fill: parent
                                        anchors.leftMargin: 10
                                        anchors.rightMargin: 10
                                        spacing: 8
                                        Text {
                                            text: modelData.name + " " + root.factionShort(modelData.faction_name)
                                            color: "#2C1E12"
                                            font.pixelSize: 12
                                            font.bold: true
                                            elide: Text.ElideRight
                                            Layout.fillWidth: true
                                        }
                                        Text { text: root.officeIcon(modelData.office) + " " + root.officeName(modelData.office); color: "#2C1E12"; font.pixelSize: 12; Layout.preferredWidth: 90 }
                                        Text { text: (modelData.wealth || 0) + " T"; color: "#8B2500"; font.pixelSize: 12; font.bold: true; Layout.preferredWidth: 76 }
                                        TextField {
                                            id: sponsorInput
                                            text: Math.min(5, modelData.wealth || 0).toString()
                                            enabled: sessionStore.canCampaign && !sessionStore.populationResolved
                                            validator: IntValidator { bottom: 0; top: Math.max(0, modelData.wealth || 0) }
                                            horizontalAlignment: TextInput.AlignHCenter
                                            font.pixelSize: 12
                                            Layout.preferredWidth: 64
                                            Layout.preferredHeight: 26
                                        }
                                    }
                                }
                            }
                        }
                    }

                    Rectangle {
                        Layout.fillWidth: true
                        Layout.preferredHeight: 44
                        color: "transparent"
                        border.color: "#D4A574"
                        border.width: 0

                        Rectangle {
                            id: campaignButton
                            property bool hovered: false
                            property bool buttonEnabled: sessionStore.canCampaign && !campaignSubmitted()
                            anchors.left: parent.left
                            anchors.right: parent.right
                            anchors.verticalCenter: parent.verticalCenter
                            anchors.leftMargin: 12
                            anchors.rightMargin: 12
                            height: 26
                            radius: 4
                            opacity: buttonEnabled ? 1.0 : 0.35
                            border.color: "#D4A574"
                            border.width: 1
                            gradient: Gradient {
                                orientation: Gradient.Vertical
                                GradientStop { position: 0.0; color: campaignButton.hovered && campaignButton.buttonEnabled ? root.actionButtonHover : root.actionButtonTop }
                                GradientStop { position: 1.0; color: root.actionButtonBottom }
                            }

                            Text {
                                anchors.centerIn: parent
                                text: campaignSubmitted() ? "⬻️ 庆典已完成" : "⬻️ 完成庆典"
                                color: "#2C1E12"
                                font.pixelSize: 12
                                font.bold: true
                            }

                            MouseArea {
                                anchors.fill: parent
                                enabled: campaignButton.buttonEnabled
                                hoverEnabled: true
                                cursorShape: Qt.PointingHandCursor
                                onEntered: campaignButton.hovered = true
                                onExited: campaignButton.hovered = false
                                onClicked: {
                                var entries = []
                                for (var i = 0; i < campaignRepeater.count; i++) {
                                    var item = campaignRepeater.itemAt(i)
                                    if (item && item.amount > 0) {
                                        entries.push({"figure_id": item.figureId, "amount": item.amount})
                                    }
                                }
                                // WP-03 L5 (P2-02 Option A): 零花费庆典也提交（空 entries = 合法 no-op 完成）
                                var result = sessionStore.doBatchCampaign(entries)
                                if (!result.success) {
                                    root.forceActiveFocus()
                                }
                            }
                            }
                        }
                    }
                }
            }

            Rectangle {
                id: votePanel
                objectName: "populationVotePanel"
                Layout.fillWidth: true
                Layout.fillHeight: true
                color: "#FFF5E6"
                radius: 6
                border.color: "#D4A574"
                border.width: 1

                ColumnLayout {
                    anchors.fill: parent
                    spacing: 0

                    Rectangle {
                        Layout.fillWidth: true
                        Layout.preferredHeight: 36
                        radius: 5
                        color: campaignSubmitted() ? "#8B2500" : "#B88976"
                        Text {
                            anchors.verticalCenter: parent.verticalCenter
                            anchors.left: parent.left
                            anchors.leftMargin: 12
                            text: "② 投票选举"
                            color: "#FFF2CC"
                            font.pixelSize: 13
                            font.bold: true
                        }
                    }

                    Item {
                        Layout.fillWidth: true
                        Layout.fillHeight: true

                        Flickable {
                            id: voteFlickable
                            objectName: "populationVoteFlickable"
                            anchors.fill: parent
                            anchors.margins: 10
                            clip: true
                            contentWidth: width
                            contentHeight: voteRows.implicitHeight + 12
                            boundsBehavior: Flickable.StopAtBounds
                            opacity: campaignSubmitted() ? 1.0 : 0.28

                            ScrollBar.vertical: ScrollBar {
                                objectName: "populationVoteScrollBar"
                                height: voteFlickable.height
                                size: voteFlickable.visibleArea.heightRatio
                                position: voteFlickable.visibleArea.yPosition
                                policy: ScrollBar.AsNeeded
                            }

                            Column {
                                id: voteRows
                                width: parent.width
                                spacing: 6

                                Repeater {
                                    model: root.offices
                                    delegate: Column {
                                        width: parent.width
                                        spacing: 2
                                        property var rows: root.candidatesForOffice(modelData)
                                        Text {
                                            text: root.officeIcon(modelData) + " " + root.officeName(modelData)
                                            color: "#2C1E12"
                                            font.pixelSize: 12
                                            font.bold: true
                                        }
                                        Repeater {
                                            model: rows
                                            delegate: RadioButton {
                                                objectName: "populationVoteCandidate_" + modelData.office + "_" + modelData.id
                                                text: modelData.name + " (" + root.factionShort(modelData.faction_name) + ")"
                                                checked: root.votedFigureId(modelData.office) === modelData.id
                                                enabled: sessionStore.canVote && campaignSubmitted() && !sessionStore.populationResolved && !sessionStore.myVotes[modelData.office]
                                                font.pixelSize: 12
                                                onClicked: root.selectCandidate(modelData.office, modelData.id)
                                            }
                                        }
                                        Text {
                                            visible: rows.length === 0
                                            text: "弃权（无候选人）"
                                            color: "#B88976"
                                            font.pixelSize: 12
                                            font.italic: true
                                        }
                                    }
                                }
                            }
                        }

                        Rectangle {
                            id: voteLock
                            objectName: "populationVoteLock"
                            visible: !campaignSubmitted()
                            anchors.centerIn: parent
                            width: 132
                            height: 34
                            radius: 5
                            color: "#B88976"
                            Text {
                                anchors.centerIn: parent
                                text: "⏳ 等待庆典完成"
                                color: "#FFF8F0"
                                font.pixelSize: 12
                                font.bold: true
                            }
                        }
                    }

                    Rectangle {
                        Layout.fillWidth: true
                        Layout.preferredHeight: 44
                        color: "transparent"

                        Rectangle {
                            id: resolveButton
                            objectName: "populationResolveButton"
                            property bool hovered: false
                            property bool buttonEnabled: sessionStore.canVote && campaignSubmitted()
                                && !sessionStore.populationResolved && !sessionStore.populationVoteSubmitting
                            anchors.left: parent.left
                            anchors.right: parent.right
                            anchors.verticalCenter: parent.verticalCenter
                            anchors.leftMargin: 12
                            anchors.rightMargin: 12
                            height: 26
                            radius: 4
                            opacity: buttonEnabled ? 1.0 : 0.35
                            border.color: "#D4A574"
                            border.width: 1
                            gradient: Gradient {
                                orientation: Gradient.Vertical
                                GradientStop { position: 0.0; color: resolveButton.hovered && resolveButton.buttonEnabled ? root.actionButtonHover : root.actionButtonTop }
                                GradientStop { position: 1.0; color: root.actionButtonBottom }
                            }

                            Text {
                                anchors.centerIn: parent
                                text: sessionStore.populationResolved ? "⬻️ 投票已完成" : "⬻️ 完成投票"
                                color: "#2C1E12"
                                font.pixelSize: 12
                                font.bold: true
                            }

                            MouseArea {
                                anchors.fill: parent
                                enabled: resolveButton.buttonEnabled
                                hoverEnabled: true
                                cursorShape: Qt.PointingHandCursor
                                onEntered: resolveButton.hovered = true
                                onExited: resolveButton.hovered = false
                                onClicked: {
                                var result = sessionStore.submitPopulationVotes(root.selectedVotes)
                                if (!result.success) {
                                    root.forceActiveFocus()
                                }
                            }
                            }
                        }
                    }
                }
            }
        }
    }
}
