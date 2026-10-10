import QtQuick 2.15
import QtQuick.Controls 2.15
import QtQuick.Layouts 1.15

import "../components"
import "../i18n"

/*!
 * \brief MortalityStage — H0 streamlined: event content area only.
 *
 * H0 change: removed self-contained parallel slot structure
 * (header / instruction / action). Header, instruction bar, and
 * execute button are now distributed to StageDesktop's 4 slots
 * by GameShell. This component fills only StageDesktop.stageContentSlot.
 *
 * DEV-08: Death events display faction_name for each victim.
 *   - Iterates ALL impacts (PM G3 F-02)
 *   - QML-side traversal, no backend change (PM G3 F-01)
 *   - Only shows faction info for type === "figure_death"
 *   - Non-death events show no faction info
 *
 * Layout contract: GUI_LAYOUT_CONTRACT_Phase1_v3.25.1.md §4
 *   StageContentSlot: event area with info-box style
 */
Rectangle {
    id: root
    objectName: "mortalityStage"
    color: "transparent"

    FactionStyle { id: factionStyle }

    // Filter impacts for figure_death type (supports multiple victims per event).
    // WP-J J-AC-09 / FC-10: list-detection predicate. The authoritative payload arrives as a
    // Qt list (`QVariantList`), for which `Array.isArray(...)` is ALWAYS false in this runtime
    // (G1 §1.2 / diag-array-probe.json) → guarded to [] and the rows never rendered.
    // Consume the authoritative list iff it exposes a numeric `length`; never fabricate fields.
    function deathImpacts(impacts) {
        if (!impacts || typeof impacts.length !== "number") return []
        var result = []
        for (var i = 0; i < impacts.length; i++) {
            if (impacts[i].type === "figure_death") {
                result.push(impacts[i])
            }
        }
        return result
    }

    ColumnLayout {
        anchors.fill: parent
        spacing: 10

        // Before execution: instruction card.
        Rectangle {
            visible: (sessionStore.mortalityEvents || []).length === 0
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
                // WP-F S3-1（007-01）：删除伪事件预告「事件类型：猝死」，保留通用随机事件引导（007-02，R-11）
                text: "🎴 " + L10n.t("mortality.prompt.body")
                color: "#2E251B"
                font.pixelSize: theme.bodySize
                wrapMode: Text.Wrap
            }
        }

        // After execution: resolved status strip.
        Rectangle {
            visible: (sessionStore.mortalityEvents || []).length > 0
            Layout.fillWidth: true
            Layout.preferredHeight: 42
            color: "#EFFFF2"
            border.color: "#2FA03A"
            border.width: 1
            radius: 5

            Row {
                anchors.left: parent.left
                anchors.leftMargin: 14
                anchors.verticalCenter: parent.verticalCenter
                spacing: 7

                Text {
                    text: "✅"
                    font.pixelSize: 13
                    anchors.verticalCenter: parent.verticalCenter
                }
                Text {
                    text: GuiText.mortalityResolved
                    color: "#2E251B"
                    font.pixelSize: theme.bodySize
                    anchors.verticalCenter: parent.verticalCenter
                }
            }
        }

        Row {
            visible: (sessionStore.mortalityEvents || []).length > 0
            Layout.fillWidth: true
            spacing: 6

            Text {
                text: "🎴"
                font.pixelSize: 13
                anchors.verticalCenter: parent.verticalCenter
            }
            Text {
                text: GuiText.mortalityEventsTitle
                color: "#681B07"
                font.pixelSize: 13
                font.bold: true
                anchors.verticalCenter: parent.verticalCenter
            }
        }

        // Event items.
        // DEV-08: Each event shows faction_name from ALL figure_death impacts.
        Repeater {
            model: sessionStore.mortalityEvents || []
            delegate: Rectangle {
                Layout.fillWidth: true
                Layout.preferredHeight: _innerCol.implicitHeight + 16
                color: "#B8FFF9EC"
                border.color: "#85A8753B"
                border.width: 1
                radius: 4

                property var _deathList: root.deathImpacts(modelData.impacts)

                ColumnLayout {
                    id: _innerCol
                    anchors.fill: parent
                    anchors.leftMargin: 12
                    anchors.rightMargin: 12
                    anchors.topMargin: 8
                    anchors.bottomMargin: 8
                    spacing: 4

                    // Event header row: emoji + name + summary
                    RowLayout {
                        Layout.fillWidth: true
                        spacing: 7

                        Text {
                            text: modelData.effect === "death" ? "💀" : "⚡"
                            font.pixelSize: 13
                            Layout.alignment: Qt.AlignVCenter
                        }
                        Text {
                            text: (modelData.name || "") + (modelData.summary ? "  " + modelData.summary : "")
                            color: "#2E251B"
                            font.pixelSize: theme.bodySize
                            elide: Text.ElideRight
                            Layout.fillWidth: true
                            Layout.alignment: Qt.AlignVCenter
                        }
                        Text {
                            text: modelData.summary || ""
                            color: "#C45151"
                            font.pixelSize: theme.bodySize
                            visible: !!modelData.summary && _deathList.length === 0
                            elide: Text.ElideRight
                            Layout.maximumWidth: 360
                            Layout.alignment: Qt.AlignVCenter
                        }
                    }

                    // DEV-08: Display each death victim with faction_name.
                    // PM G3 F-02: Traverse ALL impacts — no "first item only" logic.
                    // PM G3 F-01: QML-side traversal, no backend DTO change.
                    Repeater {
                        model: _deathList

                        delegate: Rectangle {
                            Layout.fillWidth: true
                            Layout.preferredHeight: _deathCol.implicitHeight + 6
                            color: "transparent"

                            // WP-J Group-A R1 / FC-15（J-AC-13）：归公明细仅渲染。
                            // 字段存在且 ≥ 1 → 渲染子行；缺失 / 0 → 不渲染（**QML 禁重算/禁推导**）。
                            property var _wealth: modelData.wealth_confiscated
                            property var _land: modelData.land_confiscated
                            property bool _showWealth: _wealth !== undefined && _wealth !== null && _wealth >= 1
                            property bool _showLand: _land !== undefined && _land !== null && _land >= 1

                            ColumnLayout {
                                id: _deathCol
                                anchors.left: parent.left
                                anchors.right: parent.right
                                anchors.leftMargin: 20
                                anchors.verticalCenter: parent.verticalCenter
                                spacing: 2

                                RowLayout {
                                    Layout.fillWidth: true
                                    spacing: 6

                                    Text {
                                        text: "💀"
                                        font.pixelSize: 11
                                        Layout.alignment: Qt.AlignVCenter
                                    }
                                    Text {
                                        text: modelData.figure_name || ""
                                        color: factionStyle.factionColor(modelData.faction_id || modelData.faction_name)
                                        font.pixelSize: theme.bodySize
                                        font.bold: true
                                        Layout.alignment: Qt.AlignVCenter
                                    }
                                    Text {
                                        text: L10n.t("mortality.death.faction_suffix", { faction: modelData.faction_name || L10n.t("mortality.faction.none") })
                                        color: "#766652"
                                        font.pixelSize: theme.smallSize
                                        Layout.alignment: Qt.AlignVCenter
                                    }
                                }

                                // FC-15：归公财富（T）子行（仅 ≥ 1）。
                                Text {
                                    visible: _showWealth
                                    text: "💰 " + L10n.t("mortality.confiscate.wealth", { amount: _wealth })
                                    color: "#8B2500"
                                    font.pixelSize: theme.smallSize
                                    Layout.alignment: Qt.AlignVCenter
                                }
                                // FC-15：归公土地（C）子行（仅 ≥ 1）。
                                Text {
                                    visible: _showLand
                                    text: "🏞️ " + L10n.t("mortality.confiscate.land", { amount: _land })
                                    color: "#2E6B2E"
                                    font.pixelSize: theme.smallSize
                                    Layout.alignment: Qt.AlignVCenter
                                }
                            }
                        }
                    }
                }
            }
        }

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
