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

    Layout.fillWidth: true
    implicitHeight: col.implicitHeight + 12
    radius: 4
    color: "#FFF6E6"
    border.color: isPeace ? "#7FA05A" : "#E0B56C"
    border.width: 1

    function classificationLabel() {
        var c = cardRoot.card ? cardRoot.card.classification : ""
        if (c === "active_declaration") return "可宣战候选"
        if (c === "passive_declaration") return "新爆发战争"
        if (c === "pending_peace") return "停战待决战争"
        if (c === "ongoing") return "进行中战争"
        return c || ""
    }

    function emitDraft(patch) {
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
                enabled: cardRoot.editable
                checked: cardRoot.checkedNow
                onToggled: cardRoot.emitDraft({"checked": checked})
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

            ComboBox {
                id: commanderCombo
                Layout.fillWidth: true
                enabled: cardRoot.editable
                model: cardRoot.commanderCandidates
                textRole: "label"
                valueRole: "figure_id"
                currentIndex: cardRoot.candidateIndex()
                onActivated: cardRoot.emitDraft({"target_commander_id": model[currentIndex].figure_id})
            }

            Text {
                text: "征召"
                color: "#2C1E12"
                font.pixelSize: 11
            }

            SpinBox {
                id: nBox
                enabled: cardRoot.editable
                // 静态 UI 值域（0…99）——非池推导上限；N 的真实约束由 Core Submit 校验（A-I18）
                from: 0
                to: 99
                value: cardRoot.nNow
                editable: true
                Layout.preferredWidth: 70
                onValueModified: cardRoot.emitDraft({"reinforcement_n": value})
            }
        }
    }
}
