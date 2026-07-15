import QtQuick 2.15
import QtQuick.Controls 2.15
import QtQuick.Layouts 1.15
import Qt5Compat.GraphicalEffects

Rectangle {
    id: root
    objectName: "forumStage"
    color: "transparent"

    property bool marketUnlocked: sessionStore.forumCurrentStep !== "retirement" || sessionStore.forumResolved
    property int selectedMarketFigureId: sessionStore.forumAvailableFigures.length > 0 ? sessionStore.forumAvailableFigures[0].id : 0
    property int selectedOwnFigureId: sessionStore.forumMyFigures.length > 0 ? sessionStore.forumMyFigures[0].id : 0

    function showFeedback(type, message) {
        var cp = root.parent
        while (cp && cp.objectName !== "contextPanel") {
            cp = cp.parent
        }
        if (cp && cp.showFeedback) {
            cp.showFeedback(type, message)
        }
    }

    function callAndReport(result) {
        if (!result.success) {
            showFeedback("error", result.message)
        }
    }

    ColumnLayout {
        anchors.fill: parent
        spacing: 10

        Rectangle {
            Layout.fillWidth: true
            Layout.preferredHeight: 60
            color: "#D1FFF9EC"
            border.color: "#85A8753B"
            border.width: 1
            radius: 5

            ColumnLayout {
                anchors.fill: parent
                anchors.margins: 10
                spacing: 4

                Text {
                    text: "📣 广场阶段开始。第一布匿战争进行中。西西里包税合同待竞标。"
                    color: "#2E251B"
                    font.pixelSize: 13
                    font.bold: true
                    Layout.fillWidth: true
                    wrapMode: Text.Wrap
                }

                Text {
                    text: "※ 所有派系操作完毕后将在此公示：招募结果（不公开招募者）、合同竞标结果、土地认购结果、凯旋投票结果"
                    color: "#766652"
                    font.pixelSize: 12
                    Layout.fillWidth: true
                    wrapMode: Text.Wrap
                }
            }
        }

        RowLayout {
            Layout.fillWidth: true
            Layout.fillHeight: true
            spacing: 12

            Rectangle {
                Layout.fillWidth: true
                Layout.fillHeight: true
                color: "#F7EAD2"
                border.color: "#A8753B"
                border.width: 1
                radius: 5
                clip: true

                ColumnLayout {
                    anchors.fill: parent
                    spacing: 0

                    Rectangle {
                        Layout.fillWidth: true
                        Layout.preferredHeight: 36
                        gradient: Gradient {
                            orientation: Gradient.Vertical
                            GradientStop { position: 0.0; color: "#84250A" }
                            GradientStop { position: 1.0; color: "#671B07" }
                        }

                        RowLayout {
                            anchors.fill: parent
                            anchors.leftMargin: 10
                            anchors.rightMargin: 10
                            spacing: 8

                            Rectangle {
                                width: 20
                                height: 20
                                radius: 10
                                color: "#F2C14E"
                                Text {
                                    anchors.centerIn: parent
                                    text: "1"
                                    color: "#2C1E12"
                                    font.pixelSize: 11
                                    font.bold: true
                                }
                            }

                            Text {
                                text: "解雇成员"
                                color: "#F7D778"
                                font.pixelSize: 14
                                font.bold: true
                            }

                            Item { Layout.fillWidth: true }

                            Text {
                                visible: root.marketUnlocked
                                text: "已完成"
                                color: "#7CFF77"
                                font.pixelSize: 11
                                font.bold: true
                            }
                        }
                    }

                    Text {
                        Layout.fillWidth: true
                        Layout.leftMargin: 12
                        Layout.rightMargin: 12
                        Layout.topMargin: 10
                        text: "勾选要解雇的成员。解雇后进入人才市场，所有派系执行完毕后进入下一环节。"
                        color: "#766652"
                        font.pixelSize: 12
                        wrapMode: Text.Wrap
                    }

                    ScrollView {
                        id: retireListScroll
                        Layout.fillWidth: true
                        Layout.fillHeight: true
                        Layout.leftMargin: 0
                        Layout.rightMargin: 0
                        clip: true
                        ScrollBar.vertical.policy: ScrollBar.AsNeeded

                        Column {
                            id: retireListColumn
                            width: retireListScroll.availableWidth
                            spacing: 8
                            topPadding: 2
                            bottomPadding: 6

                            Repeater {
                                model: sessionStore.forumMyFigures

                                delegate: Rectangle {
                                    width: Math.max(0, retireListColumn.width - 24)
                                    height: 46
                                    x: 12
                                    color: modelData.can_retire ? "#FFF9EC" : "#EEE3D0"
                                    border.color: root.selectedOwnFigureId === modelData.id ? "#BD8F52" : "#55A8753B"
                                    border.width: root.selectedOwnFigureId === modelData.id ? 2 : 1
                                    radius: 4

                                    MouseArea {
                                        anchors.fill: parent
                                        enabled: modelData.can_retire
                                        onClicked: root.selectedOwnFigureId = modelData.id
                                    }

                                    Text {
                                        id: ownFigureName
                                        anchors.left: parent.left
                                        anchors.leftMargin: 10
                                        anchors.right: ownFigureMeta.left
                                        anchors.rightMargin: 8
                                        anchors.verticalCenter: parent.verticalCenter
                                        text: modelData.name
                                        color: "#2E251B"
                                        font.pixelSize: 12
                                        font.bold: true
                                        elide: Text.ElideRight
                                        verticalAlignment: Text.AlignVCenter
                                    }

                                    Text {
                                        id: ownFigureMeta
                                        anchors.right: retireButton.left
                                        anchors.rightMargin: 8
                                        anchors.verticalCenter: parent.verticalCenter
                                        width: 122
                                        text: modelData.class_label + " · 影响力 " + modelData.influence
                                        color: "#766652"
                                        font.pixelSize: 11
                                        elide: Text.ElideRight
                                        horizontalAlignment: Text.AlignRight
                                        verticalAlignment: Text.AlignVCenter
                                    }

                                    Rectangle {
                                        id: retireButton
                                        anchors.right: parent.right
                                        anchors.rightMargin: 8
                                        anchors.verticalCenter: parent.verticalCenter
                                        width: 56
                                        height: 24
                                        radius: 4
                                        color: modelData.can_retire ? "#84250A" : "#C89A80"
                                        opacity: sessionStore.canExecuteForum ? 1.0 : 0.70

                                        Text {
                                            anchors.centerIn: parent
                                            text: modelData.can_retire ? "解雇" : "锁定"
                                            color: "#F7D778"
                                            font.pixelSize: 11
                                            font.bold: true
                                        }

                                        MouseArea {
                                            anchors.fill: parent
                                            enabled: modelData.can_retire && sessionStore.canExecuteForum && !root.marketUnlocked
                                            cursorShape: Qt.PointingHandCursor
                                            onClicked: {
                                                root.selectedOwnFigureId = modelData.id
                                                root.callAndReport(sessionStore.doRetireFigure(modelData.id))
                                            }
                                        }
                                    }
                                }
                            }
                        }
                    }

                    Rectangle {
                        Layout.fillWidth: true
                        Layout.leftMargin: 12
                        Layout.rightMargin: 12
                        Layout.topMargin: 4
                        Layout.bottomMargin: 12
                        Layout.preferredHeight: 26
                        radius: 4
                        color: sessionStore.canExecuteForum && !root.marketUnlocked ? "#D6A357" : "#C89A80"
                        border.color: "#AA7C3B"
                        border.width: 1

                        Text {
                            anchors.centerIn: parent
                            text: root.marketUnlocked ? "✓ 已完成解雇" : "↪ 完成解雇"
                            color: root.marketUnlocked ? "#FFF4D1" : "#2C1E12"
                            font.pixelSize: 12
                            font.bold: true
                        }

                        MouseArea {
                            anchors.fill: parent
                            enabled: sessionStore.canExecuteForum && !root.marketUnlocked
                            cursorShape: Qt.PointingHandCursor
                            onClicked: root.callAndReport(sessionStore.doCompleteForumStep())
                        }
                    }
                }
            }

            Rectangle {
                Layout.fillWidth: true
                Layout.fillHeight: true
                color: "#F7EAD2"
                border.color: "#A8753B"
                border.width: 1
                radius: 5
                clip: true

                ColumnLayout {
                    anchors.fill: parent
                    spacing: 0

                    Rectangle {
                        Layout.fillWidth: true
                        Layout.preferredHeight: 36
                        color: root.marketUnlocked ? "#84250A" : "#A4654D"

                        RowLayout {
                            anchors.fill: parent
                            anchors.leftMargin: 10
                            anchors.rightMargin: 10
                            spacing: 8

                            Rectangle {
                                width: 20
                                height: 20
                                radius: 10
                                color: root.marketUnlocked ? "#F2C14E" : "#D8C6B4"
                                Text {
                                    anchors.centerIn: parent
                                    text: "2"
                                    color: "#2C1E12"
                                    font.pixelSize: 11
                                    font.bold: true
                                }
                            }

                            Text {
                                text: "市场（招募·竞标·认购·凯旋）"
                                color: "#F7D778"
                                font.pixelSize: 14
                                font.bold: true
                                Layout.fillWidth: true
                                elide: Text.ElideRight
                            }
                        }
                    }

                    ScrollView {
                        id: marketScroll
                        Layout.fillWidth: true
                        Layout.fillHeight: true
                        clip: true
                        ScrollBar.vertical.policy: ScrollBar.AsNeeded

                        ColumnLayout {
                            width: parent.width
                            spacing: 8
                            opacity: root.marketUnlocked ? 1.0 : 0.33

                            Text {
                                Layout.fillWidth: true
                                Layout.leftMargin: 12
                                Layout.rightMargin: 12
                                Layout.topMargin: 10
                                text: "👥 人才市场（列表排列，便于比较）"
                                color: "#681B07"
                                font.pixelSize: 13
                                font.bold: true
                            }

                            RowLayout {
                                Layout.fillWidth: true
                                Layout.leftMargin: 12
                                Layout.rightMargin: 12
                                spacing: 8

                                Repeater {
                                    model: ["姓名", "年龄", "智力", "魅力", "热忱", "阶级", "费用"]
                                    delegate: Text {
                                        text: modelData
                                        color: "#681B07"
                                        font.pixelSize: 11
                                        font.bold: true
                                        Layout.fillWidth: index === 0
                                    }
                                }
                            }

                            Repeater {
                                model: sessionStore.forumAvailableFigures

                                delegate: Rectangle {
                                    Layout.fillWidth: true
                                    Layout.leftMargin: 12
                                    Layout.rightMargin: 12
                                    Layout.preferredHeight: 34
                                    color: "#FFF9EC"
                                    border.color: root.selectedMarketFigureId === modelData.id ? "#BD8F52" : "#55A8753B"
                                    border.width: root.selectedMarketFigureId === modelData.id ? 2 : 1
                                    radius: 4

                                    RowLayout {
                                        anchors.fill: parent
                                        anchors.margins: 7
                                        spacing: 8

                                        Text { text: modelData.name; color: "#2E251B"; font.pixelSize: 11; font.bold: true; Layout.fillWidth: true; elide: Text.ElideRight }
                                        Text { text: modelData.martial; color: "#2E251B"; font.pixelSize: 11; width: 28 }
                                        Text { text: modelData.intellect; color: "#2E251B"; font.pixelSize: 11; width: 28 }
                                        Text { text: modelData.charisma; color: "#2E251B"; font.pixelSize: 11; width: 28 }
                                        Text { text: modelData.zeal; color: "#2E251B"; font.pixelSize: 11; width: 28 }
                                        Text { text: modelData.class_label; color: "#4E4E9B"; font.pixelSize: 11; width: 42; font.bold: true }
                                        Text { text: modelData.cost + " T"; color: "#681B07"; font.pixelSize: 11; font.bold: true; width: 34 }

                                        Rectangle {
                                            width: 48
                                            height: 22
                                            radius: 4
                                            color: "#84250A"

                                            Text {
                                                anchors.centerIn: parent
                                                text: "招募"
                                                color: "#F7D778"
                                                font.pixelSize: 10
                                                font.bold: true
                                            }

                                            MouseArea {
                                                anchors.fill: parent
                                                enabled: root.marketUnlocked && sessionStore.canExecuteForum
                                                cursorShape: Qt.PointingHandCursor
                                                onClicked: {
                                                    root.selectedMarketFigureId = modelData.id
                                                    root.callAndReport(sessionStore.doRecruitFigure(modelData.id, modelData.cost))
                                                }
                                            }
                                        }
                                    }
                                }
                            }

                            Text {
                                visible: sessionStore.forumAvailableFigures.length === 0
                                Layout.leftMargin: 12
                                Layout.rightMargin: 12
                                text: root.marketUnlocked ? "本回合暂无可招募人物。" : "解雇环节完成前，市场新人不会提前公开。"
                                color: "#766652"
                                font.pixelSize: 11
                            }

                            SectionTitle { title: "📜 合同竞标" }

                            Repeater {
                                model: sessionStore.forumPendingContracts

                                delegate: MarketActionRow {
                                    label: modelData.name
                                    value: modelData.status_label || ""
                                    actionText: modelData.can_bid ? "竞标" : "待预算"
                                    enabledAction: root.marketUnlocked && modelData.can_bid && sessionStore.canExecuteForum && root.selectedOwnFigureId > 0
                                    onTriggered: root.callAndReport(sessionStore.doPlaceBid(root.selectedOwnFigureId, modelData.id, modelData.base_cost))
                                }
                            }

                            MarketActionRow {
                                visible: sessionStore.forumPendingContracts.length === 0
                                label: "本回合暂无预算合同"
                                value: ""
                                actionText: "待定"
                                enabledAction: false
                            }

                            SectionTitle { title: "🏡 公地认购" }

                            MarketActionRow {
                                label: sessionStore.forumLandQuota > 0 ? ("出售 " + sessionStore.forumLandQuota + "C 国家公地") : "本回合暂无可认购公地"
                                value: sessionStore.forumLandQuota > 0 ? (sessionStore.forumLandQuota + " C") : ""
                                actionText: "认购"
                                enabledAction: root.marketUnlocked && sessionStore.canExecuteForum && sessionStore.forumLandQuota > 0 && root.selectedOwnFigureId > 0
                                onTriggered: root.callAndReport(sessionStore.doBuyLand(root.selectedOwnFigureId, 1))
                            }

                            SectionTitle { title: "🏆 凯旋投票" }

                            Repeater {
                                model: sessionStore.forumTriumphWars

                                delegate: MarketActionRow {
                                    label: modelData.name + " · " + modelData.commander_name
                                    value: "士兵份额 " + modelData.soldier_share
                                    actionText: "赞成"
                                    enabledAction: root.marketUnlocked && sessionStore.canExecuteForum
                                    onTriggered: root.callAndReport(sessionStore.doVoteTriumph(modelData.war_id, true))
                                }
                            }

                            MarketActionRow {
                                visible: sessionStore.forumTriumphWars.length === 0
                                label: "本回合暂无凯旋表决"
                                value: ""
                                actionText: "待定"
                                enabledAction: false
                            }

                            Rectangle {
                                visible: root.marketUnlocked && !sessionStore.forumResolved
                                Layout.fillWidth: true
                                Layout.leftMargin: 12
                                Layout.rightMargin: 12
                                Layout.topMargin: 4
                                Layout.bottomMargin: 12
                                Layout.preferredHeight: 28
                                radius: 4
                                color: "#84250A"

                                Text {
                                    anchors.centerIn: parent
                                    text: "⚖ 提交下注"
                                    color: "#F7D778"
                                    font.pixelSize: 12
                                    font.bold: true
                                }

                                MouseArea {
                                    anchors.fill: parent
                                    enabled: sessionStore.canExecuteForum
                                    cursorShape: Qt.PointingHandCursor
                                    onClicked: root.callAndReport(sessionStore.doResolveForum())
                                }
                            }

                            Rectangle {
                                visible: sessionStore.forumResolved
                                Layout.fillWidth: true
                                Layout.leftMargin: 12
                                Layout.rightMargin: 12
                                Layout.topMargin: 4
                                Layout.bottomMargin: 12
                                Layout.preferredHeight: 28
                                radius: 4
                                color: "#C89A80"
                                border.color: "#D9AF63"
                                border.width: 1

                                Text {
                                    anchors.centerIn: parent
                                    text: "✓ 完成下注"
                                    color: "#FFF4D1"
                                    font.pixelSize: 12
                                    font.bold: true
                                }
                            }
                        }
                    }

                    Rectangle {
                        visible: !root.marketUnlocked
                        anchors.centerIn: parent
                        width: waitLabel.implicitWidth + 34
                        height: 28
                        radius: 5
                        color: "#BF9B6D5C"
                        z: 10

                        Text {
                            id: waitLabel
                            anchors.centerIn: parent
                            text: "⌛ 等待子环节完成"
                            color: "#FFF4D1"
                            font.pixelSize: 12
                            font.bold: true
                        }
                    }
                }
            }
        }
    }

    component SectionTitle: Text {
        property string title: ""
        Layout.fillWidth: true
        Layout.leftMargin: 12
        Layout.rightMargin: 12
        text: title
        color: "#681B07"
        font.pixelSize: 13
        font.bold: true
    }

    component MarketActionRow: Rectangle {
        property string label: ""
        property string value: ""
        property string actionText: ""
        property bool enabledAction: false
        signal triggered()

        Layout.fillWidth: true
        Layout.leftMargin: 12
        Layout.rightMargin: 12
        Layout.preferredHeight: 34
        color: "#FFF9EC"
        border.color: "#55A8753B"
        border.width: 1
        radius: 4

        RowLayout {
            anchors.fill: parent
            anchors.margins: 7
            spacing: 8

            Text {
                text: label
                color: "#2E251B"
                font.pixelSize: 11
                Layout.fillWidth: true
                elide: Text.ElideRight
            }

            Text {
                visible: value.length > 0
                text: value
                color: "#681B07"
                font.pixelSize: 11
                font.bold: true
            }

            Rectangle {
                width: actionText.length > 3 ? 58 : 48
                height: 22
                radius: 4
                color: enabledAction ? "#84250A" : "#D6B985"
                opacity: enabledAction ? 1.0 : 0.65

                Text {
                    anchors.centerIn: parent
                    text: actionText
                    color: enabledAction ? "#F7D778" : "#766652"
                    font.pixelSize: 10
                    font.bold: true
                }

                MouseArea {
                    anchors.fill: parent
                    enabled: enabledAction
                    cursorShape: Qt.PointingHandCursor
                    onClicked: triggered()
                }
            }
        }
    }
}

