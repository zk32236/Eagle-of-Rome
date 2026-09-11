import QtQuick 2.15
import QtQuick.Controls 2.15
import QtQuick.Layouts 1.15

import "../components"
import "../i18n"

Rectangle {
    id: root
    color: "transparent"

    FactionStyle { id: factionStyle }

    // ── QML Helper Functions ──
    function hasCommander(war) {
        return war && war.has_commander === true && war.commander_id >= 0
    }

    function attackEnabled() {
        return root.combatStep === "action"
    }

    readonly property string combatStep: sessionStore.combatCurrentStep
    readonly property var selectedWarData: root.findSelectedWar()

    // P1-02：卡片基准宽度 = (可用宽 - 10×2 列间距) / 3，适配 3 卡布局；
    // N=3 → implicitWidth=W 零滚动；N=4 → implicitWidth=(4W+10)/3 > W 真溢出 + 水平滚动
    readonly property real cardBaseWidth: Math.max(140, (warGridFlickable.width - 20) / 3)

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
            objectName: "militaryOverviewBar"
            visible: root.combatStep !== "result"
            Layout.fillWidth: true
            Layout.preferredHeight: 56
            color: "#F0E6D0"
            border.color: "#D4A574"
            border.width: 1
            radius: 6

            readonly property int activeWarsCount: (sessionStore.combatActiveWars || []).length
            // WP-F R2-02（F-02B/F-02F）：已动员军团改读权威字段 combatMobilizedLegions
            // （= MilitarySystem.get_active_legions()，含 TRUCE 附着 ACTIVE）——替代本地
            // combatActiveWars 累加（排除 TRUCE 缺陷）；QML 零生命周期推断。
            readonly property int availableLegions: sessionStore.combatMobilizedLegions || 0
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

                            Layout.preferredWidth: root.cardBaseWidth
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

                // WP-G-R4 (SA v1.7 §5.5)：resultBox 与 WarCard.cardResult 共用同一
                // stage renderer（内联组件，纯 display）。固定 header + 可滚动阶段内容 +
                // 常驻确认钮（整次 action 一个确认钮可见可用；无第二确认）。
                ColumnLayout {
                    anchors.fill: parent
                    anchors.margins: 12
                    spacing: 6

                    // Result summary header（中性色；两阶段颜色由 StageResultBlock 内按阶段读 result）
                    Text {
                        text: resultBox.result ? (resultBox.result.result_label || "战果详情") : "战果详情"
                        color: "#2C1E12"
                        font.pixelSize: theme.titleSize
                        font.bold: true
                        Layout.fillWidth: true
                        wrapMode: Text.WordWrap
                        elide: Text.ElideRight
                    }

                    // 可滚动阶段内容区（内容自适应；高度超出时滚动，确认钮不被挤出）
                    Flickable {
                        id: resultScroll
                        Layout.fillWidth: true
                        Layout.fillHeight: true
                        clip: true
                        boundsBehavior: Flickable.StopAtBounds
                        contentWidth: resultScroll.width
                        contentHeight: resultCol.implicitHeight

                        ColumnLayout {
                            id: resultCol
                            width: resultScroll.width
                            spacing: 8

                            // 同一 stage renderer：Naval + Land 并列（executed 驱动）
                            StageResultBlock { envelope: resultBox.result }
                        }
                    }

                    // Confirm button（常驻底部，整次 action 一个确认钮）
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
        objectName: "warCard"

        // R1-G-08（WP-G-R1 v1.6 §2.8）：GUI consumer 只读透传——与 DTO war card 字段
        // （assigned_fleet_count/naval_ready）精确相等（离屏 QObject/property DATA 断言点）
        readonly property int assigned_fleet_count: (warData && warData.assigned_fleet_count) ? warData.assigned_fleet_count : 0
        readonly property bool naval_ready: (warData && warData.naval_ready) === true

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

                    // WP-E F7（E-G7-11）：和约剩余回合（DTO 直读；null → 不显示）
                    // WP-F F-R3-04：视觉强调 = 标签位 pill（停战同系色 + 边框 + 间距），禁本地计算
                    Rectangle {
                        visible: !isEmptySlot && isTruceLocked && warData && warData.truce_remaining_turns !== null && warData.truce_remaining_turns !== undefined
                        Layout.alignment: Qt.AlignRight
                        Layout.leftMargin: 6
                        color: "#ECEBF2"
                        border.color: "#8E8EA6"
                        border.width: 1
                        radius: 3
                        Layout.preferredWidth: truceRemainLabel.implicitWidth + 8
                        Layout.preferredHeight: 18
                        Text {
                            id: truceRemainLabel
                            anchors.centerIn: parent
                            text: "⏳ 和约剩余 " + warData.truce_remaining_turns + " 回合"
                            color: "#3A3A55"
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
                color: isResolved ? "#999999" : (warData && warData.commander_faction_id ? factionStyle.factionColor(warData.commander_faction_id) : "#766652")
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

            // R1-G-08（WP-G-R1 v1.6 §2.8）：舰队就绪指示——读 per-war DTO 权威字段
            // warData.assigned_fleet_count / warData.naval_ready（源 = get_combat_view war
            // card，sessionStore.combatAllWarCards 透传）；禁本地推断/镜像字段。
            Text {
                id: warCardFleetReadiness
                objectName: "warCardFleetReadiness"
                visible: !isEmptySlot && !isResolved
                    && (warData && warData.naval_required)
                text: (warData && warData.naval_ready)
                    ? "⚓ 舰队就绪: " + ((warData && warData.assigned_fleet_count) || 0) + " 艘"
                    : "⚓ 舰队未就绪"
                color: (warData && warData.naval_ready) ? "#2E9D4D" : "#8A6F52"
                font.pixelSize: theme.smallSize
                font.bold: (warData && warData.naval_ready)
                Layout.leftMargin: 8
                Layout.rightMargin: 8
                Layout.topMargin: 2
            }

            // R3-G-04（§4.5）：独立 naval 强度文字（nominal/effective base/有效战力）——
            // 读 warData 分层字段（fleet_nominal_strength/fleet_quality_adjusted_base/
            // fleet_effective_combat_strength），不复用陆战「总战力」（total_power）；
            // V04 joined 可见断言点（同 run DTO → Store → 可见值）。
            Text {
                id: warCardFleetStrength
                objectName: "warCardFleetStrength"
                visible: !isEmptySlot && !isResolved
                    && (warData && warData.naval_required)
                    && (warData && warData.assigned_fleet_count > 0)
                text: {
                    var nom = (warData && warData.fleet_nominal_strength) || 0
                    var base = (warData && warData.fleet_quality_adjusted_base) || 0
                    var eff = (warData && warData.fleet_effective_combat_strength) || 0
                    return "🌊 nominal " + nom + " / 质量基础 " + base + " / 有效战力 " + eff
                }
                color: "#2E251B"
                font.pixelSize: theme.smallSize
                Layout.leftMargin: 8
                Layout.rightMargin: 8
                Layout.topMargin: 2
            }

            // ── Resolved/TRUCE 卡结果区：同一 stage renderer（AC-4.3 result left in card；
            // SA v1.7 §5.5/§5.4：TRUCE_LOCKED 卡保留双结果块）──
            ColumnLayout {
                visible: !isEmptySlot && (isResolved || isTruceLocked)
                Layout.fillWidth: true
                Layout.leftMargin: 8
                Layout.rightMargin: 8
                Layout.topMargin: 4
                spacing: 2

                StageResultBlock { envelope: cardResult; compact: true }
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

    // WP-G-R4（SA v1.7 §5.5）：两个结果区（resultBox + WarCard.cardResult）共用的同一
    // stage renderer——纯 display，不执行业务/不重建规则（R4-03）。naval/land 并列读 v2
    // envelope（schema_version=2）:
    //   - Naval executed → 「海战: 大胜/胜利/僵持/战败/灾难」+ 舰队损失 + 海权阶段结果
    //   - Land executed → 「陆战: …」+ 骰子/攻击总值/敌军防御/分数 + 军团损失 + 战利品
    //   - Land 未执行（NAVAL_GATE_BLOCKED）→ 固定「陆战: 未执行 — 海战门未通过」
    //   - NOT_READY（naval.status==NOT_READY / reason NO_READY_ASSIGNED_FLEET）→ 「海军未就绪」，
    //     不出现任何 Land 数值行
    //   - Naval bypass（NOT_REQUIRED / SEA_CONTROL_ALREADY_ACQUIRED）→ 说明原因，不渲染作「海战胜利」
    // 未执行 stage 无数值行；executed 且字段缺失 → 「未记录」（暴露 DTO contract failure，不制造
    // 零，R4-05）；色彩/图标按阶段读 result（禁顶层 success 两阶段同绿、禁 final War.RESOLVED
    // 改写 Naval label）；readiness 渲染不读 API 的 attack 能力布尔位（stage.reason 驱动）。
    component StageResultBlock: ColumnLayout {
        property var envelope: null
        property bool compact: false

        spacing: compact ? 2 : 6
        Layout.fillWidth: true

        readonly property var naval: (envelope && envelope.naval) ? envelope.naval : null
        readonly property var land: (envelope && envelope.land) ? envelope.land : null
        readonly property bool navalExecuted: naval !== null && naval.executed === true
        readonly property bool landExecuted: land !== null && land.executed === true

        function hasField(obj, key) {
            return obj !== null && obj !== undefined
                && Object.prototype.hasOwnProperty.call(obj, key)
        }
        function stageWord(result) {
            var m = { "TRIUMPH": "大胜", "VICTORY": "胜利", "STALEMATE": "僵持",
                      "DEFEAT": "战败", "DISASTER": "灾难",
                      "triumph": "大胜", "victory": "胜利", "draw": "僵持",
                      "defeat": "战败", "disaster": "灾难" }
            return m[result] !== undefined ? m[result] : ""
        }
        function stageResultColor(result) {
            var m = { "TRIUMPH": "#2E9D4D", "VICTORY": "#228B22", "STALEMATE": "#FF8C00",
                      "DEFEAT": "#B3261E", "DISASTER": "#8B0000",
                      "triumph": "#2E9D4D", "victory": "#228B22", "draw": "#FF8C00",
                      "defeat": "#B3261E", "disaster": "#8B0000" }
            return m[result] !== undefined ? m[result] : "#2C1E12"
        }
        function navalTitle(n) {
            if (n === null || n === undefined) return ""
            if (n.executed === true) return "海战: " + stageWord(n.result)
            if (n.status === "NOT_READY") return "海军未就绪"
            if (n.reason === "NOT_REQUIRED") return "海战: 未执行 — 本战无需海军"
            if (n.reason === "SEA_CONTROL_ALREADY_ACQUIRED")
                return "海战: 未执行 — 已获取制海权，本场跳过海战"
            return "海战: 未执行"
        }
        function landTitle(l) {
            if (l === null || l === undefined) return ""
            if (l.executed === true) return "陆战: " + stageWord(l.result)
            if (l.reason === "NAVAL_GATE_BLOCKED") return "陆战: 未执行 — 海战门未通过"
            if (l.reason === "NAVAL_NOT_READY") return "陆战: 未执行"
            return "陆战: 未执行"
        }
        function valueText(stage, key, suffix) {
            if (hasField(stage, key)) return String(stage[key]) + (suffix || "")
            return "未记录"   // executed 但字段缺失：暴露 DTO contract failure，不制造零
        }

        // ── Naval stage ──
        Text {
            visible: !!naval
            text: navalTitle(naval)
            color: navalExecuted ? stageResultColor(naval.result) : "#5B5B76"
            font.pixelSize: compact ? theme.smallSize : theme.bodySize
            font.bold: true
            Layout.fillWidth: true
            wrapMode: Text.WordWrap
            elide: Text.ElideRight
        }
        // NOT_READY 说明（无任何 battle 数值行；reason 常量来自 API gate，非 attack 能力位）
        Text {
            visible: naval !== null && !navalExecuted && naval.status === "NOT_READY"
            text: naval && naval.reason === "NO_READY_ASSIGNED_FLEET"
                ? "未就绪：本战无已指派可用舰队" : "未就绪"
            color: "#8A6F52"
            font.pixelSize: compact ? theme.smallSize : theme.bodySize
            Layout.fillWidth: true
            wrapMode: Text.WordWrap
        }
        // Naval executed → 舰队损失（真实损失差集）+ 海权阶段结果（stage 快照）
        Text {
            visible: navalExecuted
            text: "⚓ 舰队损失: " + valueText(naval, "roman_losses", " 艘")
                  + (hasField(naval, "casualty_fleet_ids") && naval.casualty_fleet_ids.length > 0
                     ? "（损失舰号: " + naval.casualty_fleet_ids.join(", ") + "）" : "")
            color: "#2C1E12"
            font.pixelSize: compact ? theme.smallSize : theme.bodySize
            Layout.fillWidth: true
            wrapMode: Text.WordWrap
        }
        Text {
            visible: navalExecuted
            text: naval.sea_control_acquired === true
                ? "🌊 海权: 已获取制海权" : "🌊 海权: 未获取制海权"
            color: naval.sea_control_acquired === true ? "#1E6FA8" : "#766652"
            font.pixelSize: compact ? theme.smallSize : theme.bodySize
            Layout.fillWidth: true
        }

        // ── Land stage ──
        Text {
            visible: !!land
            text: landTitle(land)
            color: landExecuted ? stageResultColor(land.result) : "#766652"
            font.pixelSize: compact ? theme.smallSize : theme.bodySize
            font.bold: landExecuted
            Layout.fillWidth: true
            wrapMode: Text.WordWrap
            elide: Text.ElideRight
        }
        Text {
            visible: landExecuted
            text: "🎲 骰子: " + valueText(land, "dice", " / 12")
                + " | 攻击总值: " + valueText(land, "total_attack")
                + " vs 敌军防御: " + valueText(land, "enemy_defence")
                + " = " + valueText(land, "total_score")
            color: "#2C1E12"
            font.pixelSize: compact ? theme.smallSize : theme.bodySize
            Layout.fillWidth: true
            wrapMode: Text.WordWrap
        }
        Text {
            visible: landExecuted && hasField(land, "losses") && land.losses > 0
            text: "💀 军团损失: " + valueText(land, "losses")
            color: "#B3261E"
            font.pixelSize: compact ? theme.smallSize : theme.bodySize
            Layout.fillWidth: true
        }
        Text {
            visible: landExecuted && hasField(land, "loot") && land.loot > 0
            text: "📦 战利品: " + valueText(land, "loot", " T")
                  + (hasField(land, "soldier_share") ? "（士兵份额 " + land.soldier_share + "）" : "")
            color: "#766652"
            font.pixelSize: compact ? theme.smallSize : theme.bodySize
            Layout.fillWidth: true
            wrapMode: Text.WordWrap
        }
    }
}
