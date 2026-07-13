import QtQuick 2.15
import QtQuick.Controls 2.15
import QtQuick.Layouts 1.15

import "../components"
import "../i18n"

/*!
 * \brief RevenueStage — Phase 2: Revenue Stage content area.
 *
 * Fills StageDesktop.stageContentSlot only.
 * Layout: National Income (L) || National Expenditure (R)
 *         Faction Treasury (L) || Private Land Income (R)
 *         Net Treasury Change (golden border, bottom)
 *
 * Layout contract: GUI_LAYOUT_CONTRACT_Phase1_v3.25.1.md §4
 *   StageContentSlot: phase-specific content area
 */
Rectangle {
    id: root
    objectName: "revenueStage"
    color: "transparent"

    property var _resultData: (sessionStore.revenueSettledData || {}).data
        || sessionStore.revenueSettledData
        || {}

    // Convenience helpers for settled data
    property bool _isSettled: (sessionStore.revenueResult || {}).success
        || !!sessionStore.revenueView.settled_data

    ColumnLayout {
        anchors.fill: parent
        spacing: 10

        // ---- Before settlement: instruction card ----
        Rectangle {
            visible: !_isSettled
            Layout.fillWidth: true
            Layout.preferredHeight: promptText.implicitHeight + 26
            color: "#B8FFF9EC"
            border.color: "#85A8753B"
            border.width: 1
            radius: theme.radius

            Text {
                id: promptText
                anchors.fill: parent
                anchors.margins: 13
                text: "💰 点击下方「确认收入结算」按钮，执行国家收入结算。\n包含：战争赔款、公地收益、合同收入、运营费、军团维护、国库净变化。"
                color: "#2E251B"
                font.pixelSize: theme.bodySize
                wrapMode: Text.Wrap
            }
        }

        // ---- Section 1: National Income (L) || National Expenditure (R) ----
        RowLayout {
            visible: _isSettled
            Layout.fillWidth: true
            spacing: 12

            // Left: National Income
            Rectangle {
                Layout.fillWidth: true
                Layout.preferredHeight: incomeCol.implicitHeight + 20
                color: "#FBF1DC"
                border.color: "#A8753B"
                border.width: 1
                radius: 4

                ColumnLayout {
                    id: incomeCol
                    anchors.fill: parent
                    anchors.margins: 10
                    spacing: 6

                    Text {
                        text: "🏛️ 国家收入"
                        color: "#681B07"
                        font.pixelSize: 14
                        font.bold: true
                    }

                    // 战争赔款
                    RowLayout {
                        Layout.fillWidth: true
                        visible: (_resultData.indemnities || []).length > 0
                        Text { text: "  战争赔款收入"; color: "#2E251B"; font.pixelSize: 12; Layout.fillWidth: true }
                        Text {
                            text: {
                                var total = 0
                                var rows = _resultData.indemnities || []
                                for (var i = 0; i < rows.length; i++) {
                                    if (rows[i].kind === "income") total += rows[i].amount
                                }
                                return "+" + total + " Talents"
                            }
                            color: "#2C7A2C"; font.pixelSize: 12; font.bold: true
                        }
                    }

                    // 公地收益
                    RowLayout {
                        Layout.fillWidth: true
                        visible: _resultData.public_land_income && _resultData.public_land_income.amount !== undefined
                        Text { text: "  公地收益"; color: "#2E251B"; font.pixelSize: 12; Layout.fillWidth: true }
                        Text {
                            text: "+" + (_resultData.public_land_income ? _resultData.public_land_income.amount : 0) + " Talents"
                            color: "#2C7A2C"; font.pixelSize: 12; font.bold: true
                        }
                    }

                    // 包税合同收入
                    RowLayout {
                        Layout.fillWidth: true
                        visible: (_resultData.contract_rows || []).length > 0
                        Text { text: "  包税合同收入"; color: "#2E251B"; font.pixelSize: 12; Layout.fillWidth: true }
                        Text {
                            text: {
                                var total = 0
                                var rows = _resultData.contract_rows || []
                                for (var i = 0; i < rows.length; i++) {
                                    if (rows[i].type === "tax_farming") total += rows[i].treasury_gain || 0
                                }
                                return "+" + total + " Talents"
                            }
                            color: "#2C7A2C"; font.pixelSize: 12; font.bold: true
                        }
                    }

                    // Treaty income (positive indemnity)
                    Repeater {
                        model: {
                            var rows = _resultData.indemnities || []
                            var inc = []
                            for (var i = 0; i < rows.length; i++) {
                                if (rows[i].kind === "income") inc.push(rows[i])
                            }
                            return inc
                        }
                        delegate: RowLayout {
                            Layout.fillWidth: true
                            Text { text: "  赔款: " + modelData.name; color: "#2E251B"; font.pixelSize: 12; Layout.fillWidth: true }
                            Text { text: "+" + modelData.amount + " Talents"; color: "#2C7A2C"; font.pixelSize: 12; font.bold: true }
                        }
                    }
                }
            }

            // Right: National Expenditure
            Rectangle {
                Layout.fillWidth: true
                Layout.preferredHeight: expenseCol.implicitHeight + 20
                color: "#FBF1DC"
                border.color: "#A8753B"
                border.width: 1
                radius: 4

                ColumnLayout {
                    id: expenseCol
                    anchors.fill: parent
                    anchors.margins: 10
                    spacing: 6

                    Text {
                        text: "💰 国家支出"
                        color: "#681B07"
                        font.pixelSize: 14
                        font.bold: true
                    }

                    // 国家运营费
                    RowLayout {
                        Layout.fillWidth: true
                        visible: _resultData.national_opex && _resultData.national_opex.amount !== undefined && _resultData.national_opex.amount > 0
                        Text { text: "  国家运营费"; color: "#2E251B"; font.pixelSize: 12; Layout.fillWidth: true }
                        Text {
                            text: "-" + (_resultData.national_opex ? _resultData.national_opex.amount : 0) + " Talents"
                            color: "#C45151"; font.pixelSize: 12; font.bold: true
                        }
                    }

                    // 军团维护费
                    RowLayout {
                        Layout.fillWidth: true
                        visible: _resultData.maintenance && _resultData.maintenance.military && _resultData.maintenance.military.total
                        Text { text: "  军团维护费"; color: "#2E251B"; font.pixelSize: 12; Layout.fillWidth: true }
                        Text {
                            text: "-" + (_resultData.maintenance && _resultData.maintenance.military ? _resultData.maintenance.military.total : 0) + " Talents"
                            color: "#C45151"; font.pixelSize: 12; font.bold: true
                        }
                    }

                    // 舰队维护费
                    RowLayout {
                        Layout.fillWidth: true
                        visible: _resultData.maintenance && _resultData.maintenance.naval && _resultData.maintenance.naval.total
                        Text { text: "  舰队维护费"; color: "#2E251B"; font.pixelSize: 12; Layout.fillWidth: true }
                        Text {
                            text: "-" + (_resultData.maintenance && _resultData.maintenance.naval ? _resultData.maintenance.naval.total : 0) + " Talents"
                            color: "#C45151"; font.pixelSize: 12; font.bold: true
                        }
                    }

                    // Expense indemnities
                    Repeater {
                        model: {
                            var rows = _resultData.indemnities || []
                            var exp = []
                            for (var i = 0; i < rows.length; i++) {
                                if (rows[i].kind === "expense") exp.push(rows[i])
                            }
                            return exp
                        }
                        delegate: RowLayout {
                            Layout.fillWidth: true
                            Text { text: "  赔款: " + modelData.name; color: "#2E251B"; font.pixelSize: 12; Layout.fillWidth: true }
                            Text { text: "-" + Math.abs(modelData.amount) + " Talents"; color: "#C45151"; font.pixelSize: 12; font.bold: true }
                        }
                    }
                }
            }
        }

        // ---- Section 2: Faction Treasury (L) || Private Land Income (R) ----
        RowLayout {
            visible: _isSettled
            Layout.fillWidth: true
            spacing: 12

            // Left: Faction Treasury
            Rectangle {
                Layout.fillWidth: true
                Layout.preferredHeight: factionCol.implicitHeight + 20
                color: "#FBF1DC"
                border.color: "#A8753B"
                border.width: 1
                radius: 4

                ColumnLayout {
                    id: factionCol
                    anchors.fill: parent
                    anchors.margins: 10
                    spacing: 6

                    Text {
                        text: "🏛️ 派系财政"
                        color: "#681B07"
                        font.pixelSize: 14
                        font.bold: true
                    }

                    Repeater {
                        model: {
                            var map = _resultData.faction_rows || {}
                            var keys = Object.keys(map)
                            var items = []
                            for (var i = 0; i < keys.length; i++) {
                                var item = map[keys[i]]
                                item.faction_id = keys[i]
                                items.push(item)
                            }
                            return items
                        }
                        delegate: Rectangle {
                            Layout.fillWidth: true
                            height: 24
                            color: "transparent"
                            RowLayout {
                                anchors.fill: parent
                                Text { text: "  " + modelData.faction_id; color: "#2E251B"; font.pixelSize: 12; Layout.fillWidth: true }
                                Text {
                                    text: "+" + (modelData.stipend + modelData.tax) + " Talents"
                                    color: "#2C7A2C"; font.pixelSize: 12; font.bold: true
                                }
                            }
                        }
                    }
                }
            }

            // Right: Private Land Income
            Rectangle {
                Layout.fillWidth: true
                Layout.preferredHeight: privateCol.implicitHeight + 20
                color: "#FBF1DC"
                border.color: "#A8753B"
                border.width: 1
                radius: 4

                ColumnLayout {
                    id: privateCol
                    anchors.fill: parent
                    anchors.margins: 10
                    spacing: 6

                    Text {
                        text: "🌾 地主收入"
                        color: "#681B07"
                        font.pixelSize: 14
                        font.bold: true
                    }

                    Repeater {
                        model: _resultData.private_land_rows || []
                        delegate: RowLayout {
                            Layout.fillWidth: true
                            Text {
                                text: "  " + (modelData.name || ("人物#" + modelData.figure_id))
                                color: "#2E251B"
                                font.pixelSize: 12
                                Layout.fillWidth: true
                                elide: Text.ElideRight
                            }
                            Text {
                                text: "+" + (modelData.income || 0) + " Talents"
                                color: "#2C7A2C"
                                font.pixelSize: 12
                                font.bold: true
                            }
                        }
                    }
                }
            }
        }

        // ---- Section 3: Net Treasury Change (golden border) ----
        Rectangle {
            visible: _isSettled
            Layout.fillWidth: true
            Layout.preferredHeight: 46
            color: "#FFF9EC"
            border.color: "#D9AF63"
            border.width: 2
            radius: 4

            RowLayout {
                anchors.centerIn: parent
                spacing: 20

                Text {
                    text: "国库净变化: " + (_resultData.treasury_delta >= 0 ? "+" : "") + (_resultData.treasury_delta || 0) + " Talents"
                    color: (_resultData.treasury_delta || 0) >= 0 ? "#2C7A2C" : "#C45151"
                    font.pixelSize: 15
                    font.bold: true
                }

                Rectangle {
                    width: 1; height: 24
                    color: "#D9AF63"
                }

                Text {
                    text: "新余额: " + (_resultData.ending_treasury || sessionStore.treasury) + " Talents"
                    color: "#2E251B"
                    font.pixelSize: 15
                    font.bold: true
                }
            }
        }

        // Spacer
        Item {
            Layout.fillWidth: true
            Layout.fillHeight: true
        }
    }

    // Forward feedback to parent context panel
    function showFeedback(type, message) {
        var cp = root.parent
        while (cp && cp.objectName !== "contextPanel") {
            cp = cp.parent
        }
        if (cp && cp.showFeedback) {
            cp.showFeedback(type, message)
        }
    }
}
