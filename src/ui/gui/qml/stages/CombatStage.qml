import QtQuick 2.15
import QtQuick.Controls 2.15
import QtQuick.Layouts 1.15

import "../i18n"

Rectangle {
    id: root
    color: "transparent"

    // ── QML Helper Functions ──
    function hasCommander(war) {
        return war && war.has_commander === true && war.commander_id >= 0
    }

    function attackEnabled() {
        return root.combatStep === "action"
    }

    readonly property string combatStep: sessionStore.combatCurrentStep
    readonly property var selectedWarData: root.findSelectedWar()

    function findSelectedWar() {
        var wars = sessionStore.combatActiveWars || []
        var selectedId = sessionStore.combatSelectedWarId
        for (var i = 0; i < wars.length; i++) {
            if (wars[i].war_id === selectedId) return wars[i]
        }
        return null
    }

    function resultColor(item) {
        if (!item) return "#2C1E12"
        var r = item.result || ""
        if (r === "triumph") return "#2E9D4D"
        if (r === "victory") return "#228B22"
        if (r === "draw" || r === "standoff") return "#FF8C00"
        if (r === "defeat") return "#B3261E"
        if (r === "disaster") return "#8B0000"
        if (r === "surrender") return "#888888"
        if (r === "withdraw") return "#AAAAAA"
        return "#2C1E12"
    }

    function isWarResolved(warId) {
        var resolved = sessionStore.combatResolvedWarIds || []
        return resolved.indexOf(warId) >= 0
    }

    // INV-C6: presentation_state 真值（L2 卡构建层产出，唯一状态源）。
    // 兼容旧数据缺失字段时按 status + 本回合已战推断（防 TRUCE 卡被误当可攻）。
    function warPresentationState(war, isEmptySlot) {
        if (isEmptySlot || war === null || war === undefined) return "EMPTY"
        if (war.presentation_state) return war.presentation_state
        if (root.isWarResolved(war.war_id)) return "CURRENT_TURN_RESULT"
        if (war.status === "truce") return "TRUCE_LOCKED"
        return "ACTIVE_ACTIONABLE"
    }

    // ── Content ──
    ColumnLayout {
        anchors.fill: parent
        anchors.topMargin: 14
        anchors.bottomMargin: 14
        anchors.leftMargin: 12
        anchors.rightMargin: 12
        spacing: 10

        // ── H1: 共和国军力总览 — compact single-line summary (P6-R8-02) ──
        Rectangle {
            id: militaryOverviewBar
            visible: root.combatStep !== "result"
            Layout.fillWidth: true
            Layout.preferredHeight: 56
            color: "#F0E6D0"
            border.color: "#D4A574"
            border.width: 1
            radius: 6

            readonly property int activeWarsCount: (sessionStore.combatActiveWars || []).length
            readonly property int availableLegions: {
                var total = 0
                var wars = sessionStore.combatActiveWars || []
                for (var i = 0; i < wars.length; i++) {
                    total += (wars[i].legion_count || 0)
                }
                return total
            }
            readonly property int fleetCount: sessionStore.combatFleetCount || 0
            readonly property int availableLegionCount: sessionStore.combatAvailableLegions || 0
            readonly property int treasury: sessionStore.treasury || 0

            ColumnLayout {
                anchors.fill: parent
                anchors.margins: 8
                spacing: 2

                Text {
                    text: "🏛️ 共和国军力总览"
                    color: "#2C1E12"
                    font.pixelSize: theme.statLabelSize
                    font.bold: true
                    Layout.fillWidth: true
                }

                RowLayout {
                    Layout.fillWidth: true
                    spacing: 6

                    CompactField { icon: "⚔️"; label: "激活战争"; value: militaryOverviewBar.activeWarsCount }
                    CompactField { icon: "🏛️"; label: "已动员军团"; value: militaryOverviewBar.availableLegions }
                    CompactField { icon: "⚓"; label: "舰队"; value: militaryOverviewBar.fleetCount }
                    CompactField { icon: "💰"; label: "国库"; value: militaryOverviewBar.treasury }
                    CompactField { icon: "📯"; label: "可动员"; value: militaryOverviewBar.availableLegionCount }
                }
            }
        }

        // ══════════════════════════════════════════════════════════════════
        // Sequential layout: war grid (fillHeight) + confirm area (fixedHeight)
        // P6-R9-03: result/advance moved from overlay to sequential child below warGrid
        // ══════════════════════════════════════════════════════════════════
        Item {
            id: warGridContainer
            Layout.fillWidth: true
            Layout.fillHeight: true

            // INV-C5/C6: ≤3 卡保持既有三槽布局（前三卡尺寸不变）；>3 卡横向单行追加
            // （横向 Flickable 滚动），禁第二行换行/纵向压缩、禁 [:3] 截断
            Flickable {
                id: warGridFlickable
                anchors.fill: parent
                clip: true
                flickableDirection: Flickable.HorizontalFlick
                boundsBehavior: Flickable.StopAtBounds
                contentWidth: Math.max(warGridFlickable.width, warGrid.implicitWidth)
                contentHeight: warGridFlickable.height

                GridLayout {
                    id: warGrid
                    width: Math.max(warGridFlickable.width, implicitWidth)
                    height: warGridFlickable.height
                    columns: Math.max(3, (sessionStore.combatAllWarCards || []).length)
                    columnSpacing: 10
                    rowSpacing: 10

                    Repeater {
                        model: Math.max(3, (sessionStore.combatAllWarCards || []).length)

                        delegate: WarCard {
                            cardIndex: index
                            readonly property var _warData: (sessionStore.combatAllWarCards || [])[index]

                            Layout.fillWidth: true
                            Layout.fillHeight: true
                            Layout.minimumWidth: 140
                            warData: _warData
                            isEmptySlot: _warData === undefined || _warData === null
                            presentationState: root.warPresentationState(_warData, isEmptySlot)
                            selectable: false
                            attackable: (root.combatStep === "select" || root.combatStep === "action")
                                && presentationState === "ACTIVE_ACTIONABLE"
                            onSelected: {
                                if (_warData && _warData.war_id) {
                                    sessionStore.doSelectWar(_warData.war_id)
                                }
                            }
                            onAttackRequested: {
                                if (_warData && _warData.war_id) {
                                    sessionStore.doCombatAction(_warData.war_id, "attack")
                                }
                            }
                        }
                    }
                }
            }
        }

        // ── H3: Confirm area (result) — sequential, below warGrid, no overlap ──
        Rectangle {
            id: confirmArea
            visible: root.combatStep === "result"
            Layout.fillWidth: true
            Layout.preferredHeight: 300
            color: "transparent"
            clip: true

            // Result content
            Rectangle {
                id: resultBox
                anchors.fill: parent
                visible: root.combatStep === "result"
                color: "#FFF7E9"
                border.color: "#2E9D4D"
                border.width: 1
                radius: 6
                clip: true

                property var result: sessionStore.combatBattleResultDetail

                ColumnLayout {
                    anchors.fill: parent
                    anchors.margins: 12
                    spacing: 6

                    // Result header
                    Text {
                        text: resultBox.result ? (resultBox.result.result_label || "") : ""
                        color: root.resultColor(resultBox.result)
                        font.pixelSize: theme.titleSize
                        font.bold: true
                        Layout.fillWidth: true
                        wrapMode: Text.WordWrap
                        elide: Text.ElideRight
                    }

                    // Battle stats
                    Text {
                        text: "🎲 骰子: " + (resultBox.result ? resultBox.result.dice || 0 : "") + " / 12"
                            + "  |  攻击总值: " + (resultBox.result ? resultBox.result.total_attack || 0 : 0)
                            + "  vs  敌军防御: " + (resultBox.result ? resultBox.result.enemy_defence || 0 : 0)
                            + "  =  " + (resultBox.result ? resultBox.result.total_score || 0 : 0)
                        color: "#2C1E12"
                        font.pixelSize: theme.bodySize
                        Layout.fillWidth: true
                        wrapMode: Text.WordWrap
                    }

                    // Loot breakdown table
                    Rectangle {
                        visible: resultBox.result && resultBox.result.loot > 0
                        Layout.fillWidth: true
                        Layout.preferredHeight: 150
                        color: "#FFF6E6"
                        radius: 4
                        border.color: "#D9AF63"
                        border.width: 1

                        ColumnLayout {
                            anchors.fill: parent
                            anchors.margins: 10
                            spacing: 3

                            Text {
                                text: "📦 战利品分配"
                                font.bold: true
                                color: "#2C1E12"
                                font.pixelSize: theme.bodySize
                            }

                            LootRow { label: "总额"; value: resultBox.result ? resultBox.result.loot : 0; bold: true }
                            LootRow { label: "国库"; value: resultBox.result ? resultBox.result.treasury_share : 0; textColor: "#8B2500" }
                            LootRow {
                                visible: resultBox.result && resultBox.result.commander_share > 0
                                label: "指挥官私库"
                                value: resultBox.result ? resultBox.result.commander_share : 0
                            }
                            LootRow {
                                visible: resultBox.result && resultBox.result.faction_share > 0
                                label: "派系金库"
                                value: resultBox.result ? resultBox.result.faction_share : 0
                            }
                            LootRow { label: "士兵份额"; value: resultBox.result ? resultBox.result.soldier_share : 0 }
                            LootRow {
                                visible: resultBox.result && resultBox.result.losses > 0
                                label: "💀 军团损失"
                                value: resultBox.result ? resultBox.result.losses : 0
                                textColor: "#B3261E"
                            }
                        }
                    }

                    // No-loot info
                    Text {
                        visible: resultBox.result && resultBox.result.loot <= 0
                        text: {
                            var r = resultBox.result ? resultBox.result.result : ""
                            if (r === "disaster") return "💀 惨败：全军覆没，无战利品"
                            if (r === "defeat") return "😞 战败：被迫撤退，未获得战利品"
                            if (r === "draw") return "🤝 僵持：未能突破敌军防线"
                            return "⚔️ 战斗结束"
                        }
                        color: "#766652"
                        font.pixelSize: theme.bodySize
                        Layout.topMargin: 4
                        Layout.fillWidth: true
                        wrapMode: Text.WordWrap
                    }

                    // Confirm button
                    ActionButton {
                        text: "✓ 确认战果"
                        Layout.alignment: Qt.AlignHCenter
                        Layout.preferredWidth: 180
                        onTriggered: {
                            sessionStore.doConfirmBattleResult()
                        }
                    }
                }
            }
        }
    }

    // ═══════════════════════════════════════════════════════════════
    // 组件定义
    // ═══════════════════════════════════════════════════════════════

    // --- Compact field for military summary (P6-R8-02) ---
    component CompactField: RowLayout {
        property string icon: "⚔️"
        property string label: ""
        property var value: 0
        property bool warning: false

        spacing: 3
        Layout.fillWidth: true

        Text {
            text: icon
            color: "#766652"
            font.pixelSize: theme.statLabelSize
        }
        Text {
            text: label + ":"
            color: "#766652"
            font.pixelSize: theme.statLabelSize
            elide: Text.ElideRight
        }
        Text {
            text: value
            color: warning ? "#B3261E" : "#2C1E12"
            font.pixelSize: theme.statValueSize
            font.bold: true
        }
    }

    // H2+H4: Upgraded WarCard with threat borders, power bar, isResolved indicator
    component WarCard: Rectangle {
        property var warData: null
        property bool selectable: false
        property int cardIndex: 0         // T05.7: slot 0/1/2 → I/II/III
        property bool isEmptySlot: false         // T05.5: empty placeholder slot
        property bool attackable: false         // FC-1: single attack entry in action step
        property string presentationState: "EMPTY"   // INV-C6: L2 presentation 真值（ACTIVE_ACTIONABLE/TRUCE_LOCKED/CURRENT_TURN_RESULT/EMPTY）
        signal selected(string warId)
        signal attackRequested(string warId)

        // INV-C6：卡面状态由 presentation_state 派生（替代 delegate 层 root.isWarResolved 直查）
        readonly property bool isResolved: !isEmptySlot && presentationState === "CURRENT_TURN_RESULT"
        readonly property bool isTruceLocked: !isEmptySlot && presentationState === "TRUCE_LOCKED"

        // T05.7 + D-4: 罗马数字徽章（前三 I/II/III 不变；overflow 第 4+ 卡扩展 IV/V/…）
        readonly property string cardNumber: {
            var numerals = ["I", "II", "III", "IV", "V", "VI", "VII", "VIII", "IX", "X"]
            return numerals[cardIndex] !== undefined ? numerals[cardIndex] : ("#" + (cardIndex + 1))
        }

        // AC-4.3: per-war result object (穿透自 combatAllWarCards[].result)
        readonly property var cardResult: (warData && warData.result) ? warData.result : null
        // AC-4.3: result color (presentation only; mirrors root.resultColor, scoped to card)
        readonly property string cardResultColor: {
            var r = cardResult ? (cardResult.result || "") : ""
            if (r === "triumph") return "#2E9D4D"
            if (r === "victory") return "#228B22"
            if (r === "draw" || r === "standoff") return "#FF8C00"
            if (r === "defeat") return "#B3261E"
            if (r === "disaster") return "#8B0000"
            if (r === "surrender") return "#888888"
            if (r === "withdraw") return "#AAAAAA"
            return "#2C1E12"
        }

        // H2: Threat-colored border (T05.5 preserved) + INV-C6 TRUCE 锁定边框
        readonly property string threatBorderColor: {
            if (isResolved) return "#B0B0B0"
            if (isTruceLocked) return "#8E8EA6"
            var level = (warData && warData.threat_level) || 0
            if (level >= 8) return "#B3261E"
            if (level >= 5) return "#E8B84B"
            return "#2E9D4D"
        }

        color: isEmptySlot ? "#F5F0E8" : (isResolved ? "#E8E4DF" : (isTruceLocked ? "#ECEBF2" : "#FFF6E6"))
        radius: 6
        border.color: isEmptySlot ? "#D4D0C8" : threatBorderColor
        border.width: isEmptySlot ? 1 : ((isResolved || isTruceLocked) ? 1 : 2)
        opacity: isEmptySlot ? 1.0 : (isResolved ? 0.6 : (isTruceLocked ? 0.75 : 1.0))
        clip: true

        // ── Full visual shell (always rendered) ──
        // T05.7: Unified BattleCard Framework — deep red title bar, card number, content area, bottom
        ColumnLayout {
            anchors.fill: parent
            spacing: 0

            // Deep red title bar with card number I/II/III
            Rectangle {
                Layout.fillWidth: true
                Layout.preferredHeight: 28
                color: "#7A1E0A"
                radius: 4

                RowLayout {
                    anchors.fill: parent
                    anchors.leftMargin: 6
                    anchors.rightMargin: 6
                    spacing: 6

                    // Card number badge (I/II/III)
                    Rectangle {
                        color: "#5A1500"
                        radius: 3
                        Layout.preferredWidth: 22
                        Layout.preferredHeight: 18
                        Text {
                            anchors.centerIn: parent
                            text: cardNumber
                            color: "#FFFFFF"
                            font.pixelSize: theme.smallSize
                            font.bold: true
                        }
                    }

                    // Title text: war name or "暂无战争"
                    Text {
                        text: isEmptySlot ? "暂无战争" : (warData ? warData.name : "未知战争")
                        color: "#FFFFFF"
                        font.pixelSize: theme.bodySize
                        font.bold: true
                        elide: Text.ElideRight
                        Layout.fillWidth: true
                    }

                    // H4: "已行动" badge (T05.5 preserved)
                    Rectangle {
                        visible: !isEmptySlot && isResolved
                        color: "#2EA44F"
                        radius: 3
                        Layout.preferredWidth: resolvedLabel.implicitWidth + 6
                        Layout.preferredHeight: 16
                        Text {
                            id: resolvedLabel
                            anchors.centerIn: parent
                            text: "✓ 已行动"
                            color: "#FFFFFF"
                            font.pixelSize: theme.smallSize
                            font.bold: true
                        }
                    }

                    // INV-C6: TRUCE 锁定徽章（可见 + 不可攻）
                    Rectangle {
                        visible: !isEmptySlot && isTruceLocked
                        color: "#5B5B76"
                        radius: 3
                        Layout.preferredWidth: truceLabel.implicitWidth + 6
                        Layout.preferredHeight: 16
                        Text {
                            id: truceLabel
                            anchors.centerIn: parent
                            text: "🔒 停战中"
                            color: "#FFFFFF"
                            font.pixelSize: theme.smallSize
                            font.bold: true
                        }
                    }
                }
            }

            // ── Empty state: centered placeholder ──
            Text {
                visible: isEmptySlot
                Layout.fillWidth: true
                Layout.fillHeight: true
                verticalAlignment: Text.AlignVCenter
                horizontalAlignment: Text.AlignHCenter
                text: "暂无战争"
                color: "#A09080"
                font.pixelSize: theme.titleSize
                font.bold: false
            }

            // ── Active state: combat stats ──
            // Commander info
            Text {
                visible: !isEmptySlot && !isResolved
                text: "🎖️ " + (warData ? (warData.commander_name || "无指挥官") : "")
                color: isResolved ? "#999999" : "#766652"
                font.pixelSize: theme.smallSize
                elide: Text.ElideRight
                Layout.fillWidth: true
                Layout.leftMargin: 8
                Layout.rightMargin: 8
                Layout.topMargin: 4
            }

            // H2: Power comparison bar (T05.5 preserved)
            Rectangle {
                visible: !isEmptySlot && !isResolved
                Layout.fillWidth: true
                Layout.preferredHeight: 14
                Layout.leftMargin: 8
                Layout.rightMargin: 8
                Layout.topMargin: 2
                color: "#E0D6C5"
                radius: 3

                Rectangle {
                    readonly property var p: warData ? (warData.total_power || 0) : 0
                    readonly property var e: warData ? (warData.enemy_power || 0) : 1
                    readonly property real ratio: (p + e) > 0 ? p / (p + e) : 0.5

                    width: parent.width * ratio
                    height: parent.height
                    radius: 3
                    color: ratio >= 0.6 ? "#2E9D4D" : (ratio >= 0.4 ? "#E8B84B" : "#B3261E")
                }

                Text {
                    anchors.centerIn: parent
                    text: "⚔ " + (warData ? warData.total_power || 0 : 0)
                        + " vs 🐉 " + (warData ? (warData.enemy_name || warData.name || "敌军") : "敌军")
                        + " (" + (warData ? warData.enemy_power || 0 : 0) + ")"
                    color: "#FFFFFF"
                    font.pixelSize: theme.smallSize
                    font.bold: true
                    elide: Text.ElideRight
                }
            }

            // H2: Threat level indicator (T05.5 preserved)
            Text {
                visible: !isEmptySlot && !isResolved
                text: {
                    var level = (warData && warData.threat_level) || 0
                    if (level >= 8) return "🔴 高威胁"
                    if (level >= 5) return "🟡 中等威胁"
                    return "🟢 低威胁"
                }
                color: threatBorderColor
                font.pixelSize: theme.smallSize
                font.bold: true
                Layout.leftMargin: 8
                Layout.rightMargin: 8
                Layout.topMargin: 2
            }

            // FC-3: 军团番号（DTO legion_numbers，不重算）
            Text {
                visible: !isEmptySlot && !isResolved
                    && (warData && warData.legion_numbers ? warData.legion_numbers.length > 0 : false)
                text: "🏛️ 军团: " + (warData && warData.legion_numbers ? "[" + warData.legion_numbers.join(", ") + "]" : "")
                color: "#766652"
                font.pixelSize: theme.smallSize
                Layout.leftMargin: 8
                Layout.rightMargin: 8
                Layout.topMargin: 2
            }

            // ── AC-4.3: Resolved state — per-war result summary (result left in card) ──
            ColumnLayout {
                visible: !isEmptySlot && isResolved
                Layout.fillWidth: true
                Layout.leftMargin: 8
                Layout.rightMargin: 8
                Layout.topMargin: 4
                spacing: 2

                // Result label (胜/败/平)
                Text {
                    text: cardResult ? (cardResult.result_label || "") : ""
                    color: cardResultColor
                    font.pixelSize: theme.bodySize
                    font.bold: true
                    Layout.fillWidth: true
                    wrapMode: Text.WordWrap
                    elide: Text.ElideRight
                }

                // Battle stats: 骰子 X/12 · 攻击总值 A vs 敌军防御 B = C
                Text {
                    text: cardResult
                        ? "🎲 骰子: " + (cardResult.dice || 0) + " / 12"
                          + "  攻击总值: " + (cardResult.total_attack || 0)
                          + " vs 敌军防御: " + (cardResult.enemy_defence || 0)
                          + " = " + (cardResult.total_score || 0)
                        : ""
                    color: "#2C1E12"
                    font.pixelSize: theme.smallSize
                    Layout.fillWidth: true
                    wrapMode: Text.WordWrap
                }

                // Loot: 战利品 L T
                Text {
                    visible: cardResult && (cardResult.loot || 0) > 0
                    text: "📦 战利品: " + (cardResult ? (cardResult.loot || 0) : 0) + " T"
                    color: "#766652"
                    font.pixelSize: theme.smallSize
                    Layout.fillWidth: true
                }
            }

            // Spacer
            Item { Layout.fillHeight: true }

            // ── Bottom action area — P1-02: restored full height button area ──
            Rectangle {
                visible: !isEmptySlot
                Layout.fillWidth: true
                Layout.preferredHeight: 30
                color: "#F0E6D0"
                radius: 3

                Text {
                    anchors.centerIn: parent
                    text: attackable ? "⚔️ 发动进攻" : (isResolved ? "✓ 已结算" : (isTruceLocked ? "🔒 停战中" : ""))
                    color: attackable ? "#B3261E" : "#766652"
                    font.pixelSize: theme.smallSize
                    font.bold: attackable
                }
            }
        }

        MouseArea {
            anchors.fill: parent
            enabled: (selectable || attackable) && !isResolved && !isEmptySlot && !isTruceLocked
            cursorShape: Qt.PointingHandCursor
            onClicked: {
                if (parent.warData && parent.warData.war_id) {
                    if (parent.attackable) {
                        parent.attackRequested(parent.warData.war_id)
                    } else {
                        parent.selected(parent.warData.war_id)
                    }
                }
            }
        }
    }

    component ActionButton: Rectangle {
        property string text: ""
        signal triggered()

        Layout.preferredHeight: 28
        radius: 4
        opacity: enabled ? 1.0 : 0.45

        property bool hovered: false

        gradient: Gradient {
            GradientStop { position: 0.0; color: enabled ? "#D9AA52" : "#D8B16C" }
            GradientStop { position: 1.0; color: enabled ? "#BC7B28" : "#D8B16C" }
        }

        Rectangle {
            anchors.top: parent.top
            anchors.left: parent.left
            anchors.right: parent.right
            anchors.leftMargin: 4
            anchors.rightMargin: 4
            height: 1
            radius: 2
            gradient: Gradient {
                orientation: Gradient.Vertical
                GradientStop { position: 0.0; color: "#66FFFFFF" }
                GradientStop { position: 1.0; color: "transparent" }
            }
        }

        Text {
            anchors.centerIn: parent
            text: parent.text
            color: "#2C1E12"
            font.pixelSize: theme.buttonSize
            font.bold: true
        }

        MouseArea {
            anchors.fill: parent
            enabled: parent.enabled
            hoverEnabled: true
            cursorShape: Qt.PointingHandCursor
            onEntered: parent.hovered = true
            onExited: parent.hovered = false
            onClicked: parent.triggered()
        }
    }

    component LootRow: Rectangle {
        property string label: ""
        property int value: 0
        property string textColor: "#2C1E12"
        property bool bold: false

        color: "transparent"
        Layout.fillWidth: true
        Layout.preferredHeight: 18

        RowLayout {
            anchors.fill: parent
            Text {
                text: "• " + label + ":"
                color: "#766652"
                font.pixelSize: theme.smallSize
                font.bold: bold
                elide: Text.ElideRight
            }
            Item { Layout.fillWidth: true }
            Text {
                text: value + " T"
                color: textColor
                font.pixelSize: theme.smallSize
                font.bold: bold
            }
        }
    }
}
