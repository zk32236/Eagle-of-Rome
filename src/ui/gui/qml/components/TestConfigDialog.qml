import QtQuick 2.15
import QtQuick.Controls 2.15
import QtQuick.Layouts 1.15

/*!
  \brief WP-G-R5 DA-6（SA-Design §5.5 / Owner §20 #44）— Configure/Test force 控件宿主。

  暴露**两个独立**的确定性战斗结果控件（互不穿透；D7 非缺陷——land/naval 分离）：
    - Force Land Result  → sessionStore.forceBattleResult  → testing.force_battle_result
    - Force Naval Result → sessionStore.forceNavalResult   → testing.force_naval_result

  空值（「正常结算」）= 清除 override → 消费点回落既有 canonical 正常结算。
  用途 = 让 G7 确定性构造：
    ① naval block（naval = stalemate/defeat → Land 不执行）
    ② naval 成功 + land 失败（naval = victory，land = defeat/disaster）
    ③ 普通 land VICTORY（land = victory）

  **不是新战斗规则**：QML 只消费 Store 只读属性/选项列表与写 Slot（零推导，A-I18）；
  消费点仍为 `combat_api:516`（land/CRT）/ `naval_system:750`（naval），语义未变。
  两键**不合并**为单一跨阶段 override。
*/
Dialog {
    id: root
    objectName: "testConfigDialog"
    modal: true
    focus: true
    dim: true
    width: Math.min(560, parent ? parent.width - 80 : 560)
    x: parent ? Math.max(0, (parent.width - width) / 2) : 0
    y: parent ? Math.max(0, (parent.height - height) / 2) : 0
    closePolicy: Popup.CloseOnEscape
    title: "⚙️ 测试配置 — 战斗结果强制"

    property string statusText: ""

    function optionToken(combo) {
        return combo.currentIndex === 0 ? "" : combo.currentText
    }

    function report(result) {
        if (result && result.success) {
            root.statusText = "已应用：" + (result.message || "")
        } else {
            root.statusText = "应用失败：" + ((result && result.message) || "未知错误")
        }
        landCombo.syncFromStore()
        navalCombo.syncFromStore()
    }

    onOpened: {
        landCombo.syncFromStore()
        navalCombo.syncFromStore()
        root.statusText = ""
    }

    background: Rectangle {
        color: "#FFF9EC"
        border.color: "#BD8F52"
        border.width: 1
        radius: 8
    }

    contentItem: ColumnLayout {
        spacing: 10

        // ── Land 控件（独立） ──
        RowLayout {
            Layout.fillWidth: true
            spacing: 8

            Text {
                text: "Force Land Result"
                color: "#2E251B"
                font.pixelSize: 13
                font.bold: true
                Layout.preferredWidth: 150
            }

            ComboBox {
                id: landCombo
                objectName: "forceLandResultCombo"
                Layout.fillWidth: true
                model: sessionStore.forceBattleResultOptions
                displayText: currentIndex === 0 ? "正常结算" : currentText

                function syncFromStore() {
                    var v = sessionStore.forceBattleResult || ""
                    var idx = 0
                    for (var i = 0; i < model.length; i++) {
                        if (model[i] === v) { idx = i; break }
                    }
                    currentIndex = idx
                }
            }

            Button {
                objectName: "applyForceLandResultButton"
                text: "应用"
                onClicked: root.report(sessionStore.doSetForceBattleResult(root.optionToken(landCombo)))
            }
        }

        Text {
            text: "→ testing.force_battle_result（空 = 正常 2d6 CRT 结算）"
            color: "#766652"
            font.pixelSize: 11
            Layout.fillWidth: true
        }

        Rectangle { Layout.fillWidth: true; Layout.preferredHeight: 1; color: "#D9C29B" }

        // ── Naval 控件（独立） ──
        RowLayout {
            Layout.fillWidth: true
            spacing: 8

            Text {
                text: "Force Naval Result"
                color: "#2E251B"
                font.pixelSize: 13
                font.bold: true
                Layout.preferredWidth: 150
            }

            ComboBox {
                id: navalCombo
                objectName: "forceNavalResultCombo"
                Layout.fillWidth: true
                model: sessionStore.forceNavalResultOptions
                displayText: currentIndex === 0 ? "正常结算" : currentText

                function syncFromStore() {
                    var v = sessionStore.forceNavalResult || ""
                    var idx = 0
                    for (var i = 0; i < model.length; i++) {
                        if (model[i] === v) { idx = i; break }
                    }
                    currentIndex = idx
                }
            }

            Button {
                objectName: "applyForceNavalResultButton"
                text: "应用"
                onClicked: root.report(sessionStore.doSetForceNavalResult(root.optionToken(navalCombo)))
            }
        }

        Text {
            text: "→ testing.force_naval_result（空 = 正常海战随机结算）"
            color: "#766652"
            font.pixelSize: 11
            Layout.fillWidth: true
        }

        Rectangle { Layout.fillWidth: true; Layout.preferredHeight: 1; color: "#D9C29B" }

        Text {
            objectName: "testConfigStatusText"
            text: root.statusText
            color: "#766652"
            font.pixelSize: 11
            Layout.fillWidth: true
            wrapMode: Text.WordWrap
        }

        RowLayout {
            Layout.fillWidth: true

            Item { Layout.fillWidth: true }

            Button {
                objectName: "closeTestConfigButton"
                text: "关闭"
                onClicked: root.close()
            }
        }
    }
}
