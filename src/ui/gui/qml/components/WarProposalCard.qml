import QtQuick 2.15
import QtQuick.Controls 2.15
import QtQuick.Layouts 1.15

// R5（SA §2.1/§5.1，DA-5）：统一 War Proposal Card（单卡模型）。
// 只消费 DTO（WarCardView：war_id / war_name / classification / allowed_modes /
// peace_capability / commander_candidates / defaults）+ 本地 draft；零 lifecycle 推导
// （A-I18/D-SC02/D-SC15）：不依 status/军事空位/军团数/名称等推测分类，
// 不本地计算 N 上限或部署门，不维护第二套默认真值（初值取 card.defaults）。
Rectangle {
    id: cardRoot

    property var card: ({})
    property var draft: ({})
    property var commanderCandidates: []
    // R6（SA §B.5，DA-2 B5）：卡级结构化错误（由 SenateStage 从
    // sessionStore.senateSubmitErrorsByWar[war_id] 注入；按 field 定位）。
    property var cardErrors: []
    property bool peaceCapable: false
    property bool editable: true

    signal draftEdited(string warId, var newDraft)

    readonly property string warId: (card && card.war_id !== undefined) ? String(card.war_id) : ""
    readonly property string mode: (draft && draft.mode) ? draft.mode : "command"
    readonly property bool isPeace: mode === "peace"
    readonly property bool checkedNow: draft ? !!draft.checked : false
    readonly property int nNow: (draft && draft.reinforcement_n !== undefined && draft.reinforcement_n !== null)
                                ? parseInt(draft.reinforcement_n, 10) : 0
    readonly property var currentTarget: (draft && draft.target_commander_id !== undefined)
                                         ? draft.target_commander_id : null

    // R7（SA §B.4，DA-R7 B3）：卡级 error 态 + 字段/控件高亮（canonical error 色）。
    // 卡集合由 SenateStage 从 Core 权威 senateSubmitErrorsByWar 注入（details.claims/
    // requests 关联）；此处仅回答「同一张已证实出错的卡上，红框落在哪个 widget」——
    // 展示路由，非校验推导（**不**建 UI-only duplicate-claims 推断模型）。
    readonly property bool hasError: cardRoot.cardErrors.length > 0
    function fieldError(field) {
        for (var i = 0; i < cardRoot.cardErrors.length; i++) {
            if (String(cardRoot.cardErrors[i].field || "") === field) return true
        }
        return false
    }
    function codeError(code) {
        for (var i = 0; i < cardRoot.cardErrors.length; i++) {
            if (String(cardRoot.cardErrors[i].code || "") === code) return true
        }
        return false
    }
    // N 字段：field 权威直指（reinforcement_n）或池超限 code（池超限属 N 输入相关）
    readonly property bool nFieldError: cardRoot.fieldError("reinforcement_n") || cardRoot.codeError("LEGION_POOL_EXCEEDED")
    // Commander 字段：包级 duplicate（field=None）→ 由 code 决定高亮哪个控件（展示路由）
    readonly property bool commanderFieldError: cardRoot.codeError("COMMANDER_CLAIM_DUPLICATE")

    // R6（SA §A.2）：authority route 唯一来源 = card.authority_by_mode[draft.mode]；
    // QML 只渲染、零推断（不得据 classification/status/名字/是否有将领推导 route）。
    readonly property var authorityMap: (card && card.authority_by_mode) ? card.authority_by_mode : ({})
    readonly property string authority: (authorityMap[mode] !== undefined) ? String(authorityMap[mode]) : ""
    readonly property bool routeReady: authority === "senate_vote" || authority === "consul_direct"

    function authorityLabel() {
        // R8（SA §5.2 C-01/C-02，D-R8-01）：proposal 期路由文案——**禁**含「决定」；
        // direct 路由 = 身份词（不提前呈现决定词）。
        if (authority === "senate_vote") return "元老院表决"
        if (authority === "consul_direct") return "执政官直接行动"
        return ""
    }

    Layout.fillWidth: true
    implicitHeight: col.implicitHeight + 12
    radius: 4
    color: "#FFF6E6"
    // R7（SA §B.4，DA-R7 B3）：错误态 → canonical error 色红框（优先于 peace/candidate 色）
    border.color: cardRoot.hasError ? theme.statusError : (isPeace ? "#7FA05A" : "#E0B56C")
    border.width: cardRoot.hasError ? 2 : 1

    function classificationLabel() {
        var c = cardRoot.card ? cardRoot.card.classification : ""
        if (c === "active_declaration") return "可宣战候选"
        if (c === "passive_declaration") return "新爆发战争"
        if (c === "pending_peace") return "停战待决战争"
        if (c === "ongoing") return "进行中战争"
        return "战争信息待更新"
    }

    function emitDraft(patch) {
        // R6（SA §A.2）fail-closed：缺 route 的卡禁止提交（不 fallback direct）。
        if (!cardRoot.routeReady && patch && patch.checked) {
            return
        }
        var next = {}
        if (cardRoot.draft) {
            for (var k in cardRoot.draft) {
                if (cardRoot.draft.hasOwnProperty(k)) next[k] = cardRoot.draft[k]
            }
        }
        for (var p in patch) {
            if (patch.hasOwnProperty(p)) next[p] = patch[p]
        }
        cardRoot.draftEdited(cardRoot.warId, next)
    }

    function candidateIndex() {
        for (var i = 0; i < commanderCandidates.length; i++) {
            if (String(commanderCandidates[i].figure_id) === String(cardRoot.currentTarget)) return i
        }
        return -1
    }

    // R6（SA §D.2，DA-4 B4）：指挥官完整身份可读——绑定面（RENDER 归 SO）。
    // 不猜名字：只取候选 label 或 Core 提供的 current/冻结 label；两者皆无 → 明示不可用。
    readonly property bool commandSelected: cardRoot.checkedNow && !cardRoot.isPeace
    readonly property bool identityIsCandidate: cardRoot.candidateIndex() >= 0
    readonly property string candidateIdentityLabel: {
        var idx = cardRoot.candidateIndex()
        if (idx < 0) return ""
        return cardRoot.labelOf(commanderCandidates[idx])
    }
    readonly property string coreIdentityLabel: (card && card.current_commander_label !== undefined
                                                 && card.current_commander_label !== null)
                                                ? String(card.current_commander_label) : ""
    // 提交后只读摘要的完整冻结身份（Core 快照 `target_commander_label`；只读态 = !editable）
    readonly property string frozenIdentityLabel: (card && card.target_commander_label !== undefined
                                                   && card.target_commander_label !== null)
                                                  ? String(card.target_commander_label) : ""

    function labelOf(entry) {
        if (!entry) return ""
        if (entry.label !== undefined && entry.label !== null) return String(entry.label)
        return ""
    }

    readonly property string identityText: {
        if (!cardRoot.commandSelected) return ""
        if (cardRoot.identityIsCandidate && cardRoot.candidateIdentityLabel !== "")
            return cardRoot.candidateIdentityLabel
        // R8（SA §5.3，FC-UI-04）：非候选 → Core current/冻结 label + **人话**不可选提示
        // （**不**露 raw ID、不猜名字）。
        var base = cardRoot.coreIdentityLabel !== "" ? cardRoot.coreIdentityLabel
                                                     : "指挥官身份暂不可用"
        return base + "（当前指挥官不在候选，不可选，请刷新候选名单）"
    }

    // R6（SA §B.5，DA-2 B5）：卡级错误渲染（code + 按 field 定位 + pool 三值）。
    function cardErrorText(item) {
        // R8（SA §5.3，FC-UI-04，D-R8-04）：卡级错误人话化——code 作内部查表键，
        // **禁** machine code / field token（诊断留 Store / 日志）。
        var code = (item && item.code) ? String(item.code) : ""
        if (code === "REINFORCEMENT_INVALID") return "增援军团数量不符合要求，请修改数量。"
        if (code === "LEGION_POOL_EXCEEDED") return "增援请求超过可用军团，请减少增援军团数量。"
        if (code === "COMMANDER_CLAIM_DUPLICATE") return "同一指挥官不能同时指挥这些战争，请为涉事战争选择不同指挥官。"
        if (code === "COMMANDER_TARGET_INVALID") return "所选指挥官不可用，请重新选择指挥官。"
        if (code === "COMMANDER_INELIGIBLE") return "所选人物不符合指挥官资格，请另行选择。"
        if (code === "PACKAGE_ALREADY_SUBMITTED") return "本会期已提交，请查看已提交内容。"
        return "此项配置不符合要求，请检查后修改。"
    }
    function poolLine(item) {
        // R6（SA §B.5，DA-4 B5）：pool 三值显示必须读 **Core 权威 details 键**
        // （`requested_total` / `available_total` / `reduce_by`，见 political_system
        // LEGION_POOL_EXCEEDED 生产者）；兼容 `requested`/`available` 旧别名。
        var d = (item && item.details) ? item.details : ({});
        var requested = (d.requested !== undefined) ? d.requested : d.requested_total
        var available = (d.available !== undefined) ? d.available : d.available_total
        if (requested === undefined && available === undefined && d.reduce_by === undefined) return ""
        return "请求 " + ((requested !== undefined) ? requested : "-")
             + " / 可用 " + ((available !== undefined) ? available : "-")
             + " / 需削减 " + ((d.reduce_by !== undefined) ? d.reduce_by : "-")
    }

    ColumnLayout {
        id: col
        anchors.fill: parent
        anchors.margins: 6
        spacing: 4

        RowLayout {
            Layout.fillWidth: true
            spacing: 6

            CheckBox {
                id: checkBox
                enabled: cardRoot.editable && cardRoot.routeReady
                checked: cardRoot.checkedNow
                onToggled: cardRoot.emitDraft({"checked": checked})
                // WP-J Group C G7 Test R4 Delta（delta v1.9 / FC-C31）：**移除** R3 方案甲（FC-C28）
                // 自绘框 `indicator` ⇒ 回落**平台默认样式**指示器（系统勾选框）。状态机
                // （enabled/checked/onToggled/emitDraft）逐字不变。
            }

            Text {
                text: (cardRoot.card ? (cardRoot.card.war_name || cardRoot.card.war_id) : "")
                      + "  ·  " + cardRoot.classificationLabel()
                color: "#2C1E12"
                font.pixelSize: 12
                font.bold: true
                Layout.fillWidth: true
                elide: Text.ElideRight
            }

            // R6（SA §A.2）：authority 只读渲染（route 唯一来源 = card.authority_by_mode[mode]）
            Text {
                visible: cardRoot.routeReady
                text: cardRoot.authorityLabel()
                color: "#6B4E00"
                font.pixelSize: 11
                font.bold: true
            }
        }

        // R6（SA §A.2）fail-closed：缺 route → 提示数据不可用 + 禁本卡提交（不 fallback direct）
        Text {
            Layout.fillWidth: true
            visible: !cardRoot.routeReady
            text: "⚠ 路由数据不可用：请刷新后重试（此卡暂不可提交）"
            color: theme.statusError
            font.pixelSize: 11
            wrapMode: Text.Wrap
        }

        // R6（SA §B.5，DA-2 B5）：卡级 `cardErrors`（按 field 定位）+ pool 三值
        // （requested / available / reduce_by）+ 人话错误消息（R8：去 machine 展开面）。
        // R7（SA §B.3.3，DA-R7 B2）：**bounded**（maxHeight ≤120 + clip + 内滚）
        // —— 长文不撑高卡片；既有内容语义（code 定位 / pool 三值 / 可展开 details）保留。
        Rectangle {
            objectName: "warCardErrorBlock"
            Layout.fillWidth: true
            visible: cardRoot.cardErrors.length > 0
            Layout.maximumHeight: 120
            Layout.preferredHeight: Math.min(120, cardErrInner.implicitHeight + 8)
            clip: true
            color: Qt.rgba(theme.statusError.r, theme.statusError.g, theme.statusError.b, 0.06)
            radius: 3
            ScrollView {
                anchors.fill: parent
                clip: true
                contentWidth: availableWidth
                ColumnLayout {
                    id: cardErrInner
                    width: parent.width
                    spacing: 2

                    Text {
                        Layout.fillWidth: true
                        text: "⚠ 此卡错误"
                        color: theme.statusError
                        font.pixelSize: 11
                        font.bold: true
                    }

                    Repeater {
                        model: cardRoot.cardErrors
                        delegate: ColumnLayout {
                            Layout.fillWidth: true
                            spacing: 1
                            Text {
                                Layout.fillWidth: true
                                text: cardRoot.cardErrorText(modelData)
                                color: theme.statusError
                                font.pixelSize: 11
                                wrapMode: Text.Wrap
                                elide: Text.ElideRight
                                maximumLineCount: 2
                            }
                            Text {
                                Layout.fillWidth: true
                                visible: cardRoot.poolLine(modelData) !== ""
                                text: cardRoot.poolLine(modelData)
                                color: "#8A5A00"
                                font.pixelSize: 11
                                elide: Text.ElideRight
                                maximumLineCount: 1
                            }
                        }
                    }
                }
            }
        }

        // 悬置和约时（peace_capable）的互斥模式 Radio；默认 command（DTO defaults.mode）
        RowLayout {
            Layout.fillWidth: true
            spacing: 10
            visible: cardRoot.checkedNow && cardRoot.peaceCapable

            RadioButton {
                text: "继续 / 作战"
                enabled: cardRoot.editable
                checked: !cardRoot.isPeace
                onClicked: cardRoot.emitDraft({"mode": "command"})
            }

            RadioButton {
                text: "停战"
                enabled: cardRoot.editable
                checked: cardRoot.isPeace
                onClicked: cardRoot.emitDraft({"mode": "peace"})
            }
        }

        RowLayout {
            Layout.fillWidth: true
            spacing: 6
            visible: cardRoot.checkedNow && !cardRoot.isPeace

            Text {
                text: "指挥官"
                color: "#2C1E12"
                font.pixelSize: 11
                Layout.preferredWidth: 52
            }

            // R7（SA §B.4，DA-R7 B3）：Commander 字段 error 态——wrapper 承载红框
            // （不改 ComboBox 主题）；duplicate-Commander → 全部涉事卡此字段高亮。
            Rectangle {
                objectName: "warCardCommanderField"
                Layout.fillWidth: true
                implicitHeight: commanderCombo.implicitHeight + 4
                color: "transparent"
                radius: 3
                border.color: cardRoot.commanderFieldError ? theme.statusError : "transparent"
                border.width: cardRoot.commanderFieldError ? 2 : 0
                ComboBox {
                    id: commanderCombo
                    objectName: "warCardCommanderCombo"
                    anchors.fill: parent
                    anchors.margins: 2
                    enabled: cardRoot.editable
                    model: cardRoot.commanderCandidates
                    textRole: "label"
                    valueRole: "figure_id"
                    currentIndex: cardRoot.candidateIndex()
                    onActivated: cardRoot.emitDraft({"target_commander_id": model[currentIndex].figure_id})
                    // R6（SA §D.2，DA-4 B4）：hover/focus tooltip 提供完整 label
                    ToolTip.delay: 250
                    ToolTip.text: cardRoot.identityIsCandidate ? cardRoot.candidateIdentityLabel
                                                              : cardRoot.identityText
                    ToolTip.visible: commanderCombo.hovered || commanderCombo.activeFocus
                    // R6（SA §D.2，DA-4 B4）：候选 delegate 提供完整 label（避免只选中后才可识别）
                    delegate: ItemDelegate {
                        id: commanderComboDelegate
                        width: commanderCombo.width
                        contentItem: Text {
                            text: cardRoot.labelOf(modelData)
                            color: "#2C1E12"
                            font.pixelSize: 12
                            // 完整 label（换行、不截断）
                            wrapMode: Text.Wrap
                            elide: Text.ElideNone
                        }
                        ToolTip.delay: 250
                        ToolTip.text: cardRoot.labelOf(modelData)
                        ToolTip.visible: commanderComboDelegate.hovered
                    }
                }
            }

            Text {
                text: "征召"
                color: "#2C1E12"
                font.pixelSize: 11
            }

            // R7（SA §B.4，DA-R7 B3）：N 字段 error 态——wrapper 承载红框（不改 SpinBox 主题）
            Rectangle {
                objectName: "warCardNField"
                implicitWidth: 70 + 4
                implicitHeight: nBox.implicitHeight + 4
                color: "transparent"
                radius: 3
                border.color: cardRoot.nFieldError ? theme.statusError : "transparent"
                border.width: cardRoot.nFieldError ? 2 : 0
                SpinBox {
                    id: nBox
                    anchors.fill: parent
                    anchors.margins: 2
                    enabled: cardRoot.editable
                    // 静态 UI 值域（0…99）——非池推导上限；N 的真实约束由 Core Submit 校验（A-I18）
                    from: 0
                    to: 99
                    value: cardRoot.nNow
                    editable: true
                    onValueModified: cardRoot.emitDraft({"reinforcement_n": value})
                }
            }
        }

        // R6（SA §D.2，DA-4 B4）：ComboBox 下的**完整身份**（仅 command 已选时可见；
        // wrap、**不 elide**；绑定当前 candidate label；非候选 ID → Core current/冻结
        // label + 不可选提示，**不猜名字**）。RENDER/键盘焦点验证归 SO（帧
        // `r6-war-card-long-commander`〔r〕）。
        Text {
            id: commanderIdentity
            objectName: "warCardCommanderIdentity"
            Layout.fillWidth: true
            visible: cardRoot.commandSelected
            text: cardRoot.identityText
            color: cardRoot.identityIsCandidate ? "#2C1E12" : theme.statusError
            font.pixelSize: 11
            wrapMode: Text.Wrap
            elide: Text.ElideNone
            activeFocusOnTab: true
            ToolTip.delay: 250
            ToolTip.text: cardRoot.identityText
            ToolTip.visible: identityHover.hovered || commanderIdentity.activeFocus
            MouseArea {
                id: identityHover
                anchors.fill: parent
                hoverEnabled: true
                acceptedButtons: Qt.NoButton
            }
        }

        // R6（SA §D.2，DA-4 B4）：提交后**只读摘要**——完整 frozen
        // `target_commander_label`（Core 快照；wrap 不 elide；只读态 = !editable）。
        ColumnLayout {
            Layout.fillWidth: true
            spacing: 1
            visible: !cardRoot.editable && cardRoot.frozenIdentityLabel !== ""
            Text {
                text: "已提交指挥官（只读）"
                color: "#6B4E00"
                font.pixelSize: 11
                font.bold: true
            }
            Text {
                objectName: "warCardFrozenCommanderLabel"
                Layout.fillWidth: true
                text: cardRoot.frozenIdentityLabel
                color: "#2C1E12"
                font.pixelSize: 11
                wrapMode: Text.Wrap
                elide: Text.ElideNone
            }
        }
    }
}
