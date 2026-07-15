import QtQuick 2.15
import QtQuick.Controls 2.15
import QtQuick.Layouts 1.15

Rectangle {
    id: root
    objectName: "populationStageRoot"
    color: "transparent"

    property var offices: ["consul", "censor", "praetor", "quaestor", "tribune"]
    property var selectedVotes: ({})

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
        if (name === "Optimates") return "Opt"
        if (name === "Populares") return "Pop"
        if (name === "Equites") return "Equ"
        return name || ""
    }

    function factionColor(name) {
        if (name === "Optimates" || name === "Opt") return "#8B0000"
        if (name === "Populares" || name === "Pop") return "#006400"
        if (name === "Equites" || name === "Equ") return "#00008B"
        return "#681B07"
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

    function resultForOffice(office) {
        var results = sessionStore.populationElectionResults || []
        for (var i = 0; i < results.length; i++) {
            if (results[i].office === office) return results[i]
        }
        return null
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
                                        text: modelData.name
                                        color: "#1F1A12"
                                        font.pixelSize: 12
                                    }
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
                                        color: root.factionColor(modelData.faction_name)
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
                        Layout.fillWidth: true
                        Layout.fillHeight: true
                        clip: true
                        contentWidth: width
                        contentHeight: campaignRows.implicitHeight + 10

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

                        Button {
                            anchors.left: parent.left
                            anchors.right: parent.right
                            anchors.verticalCenter: parent.verticalCenter
                            anchors.leftMargin: 12
                            anchors.rightMargin: 12
                            height: 26
                            text: campaignSubmitted() ? "↠ 庆典已完成" : "↠ 完成庆典"
                            enabled: sessionStore.canCampaign && !campaignSubmitted()
                            onClicked: {
                                var ok = true
                                for (var i = 0; i < campaignRepeater.count; i++) {
                                    var item = campaignRepeater.itemAt(i)
                                    if (item && item.amount > 0) {
                                        var result = sessionStore.doCampaign(item.figureId, item.amount)
                                        if (!result.success) {
                                            ok = false
                                            break
                                        }
                                    }
                                }
                                if (!ok) {
                                    root.forceActiveFocus()
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
                            anchors.fill: parent
                            anchors.margins: 10
                            clip: true
                            contentWidth: width
                            contentHeight: voteRows.implicitHeight + 12
                            opacity: campaignSubmitted() ? 1.0 : 0.28

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
                                                text: modelData.name + " (" + root.factionShort(modelData.faction_name) + ")"
                                                checked: root.votedFigureId(modelData.office) === modelData.id
                                                enabled: sessionStore.canVote && campaignSubmitted() && !sessionStore.populationResolved && !sessionStore.myVotes[modelData.office]
                                                font.pixelSize: 12
                                                onClicked: {
                                                    root.selectedVotes[modelData.office] = modelData.id
                                                }
                                            }
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

                        Button {
                            id: resolveButton
                            objectName: "populationResolveButton"
                            anchors.left: parent.left
                            anchors.right: parent.right
                            anchors.verticalCenter: parent.verticalCenter
                            anchors.leftMargin: 12
                            anchors.rightMargin: 12
                            height: 26
                            text: sessionStore.populationResolved ? "↠ 投票已完成" : "↠ 完成投票"
                            enabled: sessionStore.canVote && campaignSubmitted() && !sessionStore.populationResolved
                            onClicked: {
                                var offices = root.offices
                                for (var i = 0; i < offices.length; i++) {
                                    var office = offices[i]
                                    var selected = root.votedFigureId(office)
                                    if (selected > 0 && !sessionStore.myVotes[office]) {
                                        sessionStore.doVote(office, selected)
                                    }
                                }
                                sessionStore.doResolveElection()
                            }
                        }
                    }
                }
            }
        }
    }
}
