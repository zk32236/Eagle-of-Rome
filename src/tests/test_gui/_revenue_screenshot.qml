
import QtQuick 2.15
import QtQuick.Window 2.15
import QtQuick.Controls 2.15
import QtQuick.Layouts 1.15

Window {
    visible: false; width: 1440; height: 900; title: "Revenue Settlement"

    Flickable {
        anchors.fill: parent
        contentWidth: parent.width
        contentHeight: contentCol.implicitHeight + 30
        clip: true

        ColumnLayout {
            id: contentCol
            anchors.left: parent.left; anchors.right: parent.right
            anchors.top: parent.top; anchors.margins: 10
            spacing: 10

            Rectangle {
                Layout.fillWidth: true; Layout.preferredHeight: 40; color: "#681B07"; radius: 4
                Text { anchors.centerIn: parent; text: "💰 收入结算结果 — 国库净变化: -193 Talents"; color: "#FFFFFF"; font.pixelSize: 16; font.bold: true }
            }

            Rectangle {
                Layout.fillWidth: true; Layout.preferredHeight: incomeCol.implicitHeight + 20
                color: "#FBF1DC"; border.color: "#A8753B"; border.width: 1; radius: 4
                ColumnLayout {
                    id: incomeCol; anchors.fill: parent; anchors.margins: 10; spacing: 8
                    Text { text: "🏛️ 派系财政（展示使用派系展示名而非 raw ID）"; color: "#681B07"; font.pixelSize: 14; font.bold: true }
                    
        Rectangle {
            Layout.fillWidth: true; Layout.preferredHeight: 26; color: "transparent"
            RowLayout {
                anchors.fill: parent; spacing: 4
                Text { text: "  Optimates"; color: "#8B0000"; font.pixelSize: 12; font.bold: true; Layout.fillWidth: true }
                Text { text: "拨款 +10 · 会员 +1 · 合计 +11"; color: "#2C7A2C"; font.pixelSize: 11; font.bold: true }
            }
        }
        
        Rectangle {
            Layout.fillWidth: true; Layout.preferredHeight: 26; color: "transparent"
            RowLayout {
                anchors.fill: parent; spacing: 4
                Text { text: "  Populares"; color: "#006400"; font.pixelSize: 12; font.bold: true; Layout.fillWidth: true }
                Text { text: "拨款 +10 · 会员 +2 · 合计 +12"; color: "#2C7A2C"; font.pixelSize: 11; font.bold: true }
            }
        }
        
        Rectangle {
            Layout.fillWidth: true; Layout.preferredHeight: 26; color: "transparent"
            RowLayout {
                anchors.fill: parent; spacing: 4
                Text { text: "  Equites"; color: "#00008B"; font.pixelSize: 12; font.bold: true; Layout.fillWidth: true }
                Text { text: "拨款 +10 · 会员 +2 · 合计 +12"; color: "#2C7A2C"; font.pixelSize: 11; font.bold: true }
            }
        }
        
                }
            }

            Rectangle {
                Layout.fillWidth: true; Layout.preferredHeight: privateCol.implicitHeight + 20
                color: "#FBF1DC"; border.color: "#A8753B"; border.width: 1; radius: 4
                ColumnLayout {
                    id: privateCol; anchors.fill: parent; anchors.margins: 10; spacing: 8
                    Text { text: "🌾 地主收入"; color: "#681B07"; font.pixelSize: 14; font.bold: true }
                    
        RowLayout {
            Layout.fillWidth: true; Layout.preferredHeight: 24
            Text { text: "  Gaius·Marius·Arpinas"; color: "#2E251B"; font.pixelSize: 12; Layout.fillWidth: true; wrapMode: Text.WrapAnywhere }
            Text { text: "+14 Talents"; color: "#2C7A2C"; font.pixelSize: 12; font.bold: true }
        }
        
        RowLayout {
            Layout.fillWidth: true; Layout.preferredHeight: 24
            Text { text: "  Lucius·Cornelius·Sulla·Felix"; color: "#2E251B"; font.pixelSize: 12; Layout.fillWidth: true; wrapMode: Text.WrapAnywhere }
            Text { text: "+11 Talents"; color: "#2C7A2C"; font.pixelSize: 12; font.bold: true }
        }
        
        RowLayout {
            Layout.fillWidth: true; Layout.preferredHeight: 24
            Text { text: "  Marcus·Licinius·Crassus·Dives"; color: "#2E251B"; font.pixelSize: 12; Layout.fillWidth: true; wrapMode: Text.WrapAnywhere }
            Text { text: "+18 Talents"; color: "#2C7A2C"; font.pixelSize: 12; font.bold: true }
        }
        
        RowLayout {
            Layout.fillWidth: true; Layout.preferredHeight: 24
            Text { text: "  Gnaeus·Pompeius·Magnus·Pius"; color: "#2E251B"; font.pixelSize: 12; Layout.fillWidth: true; wrapMode: Text.WrapAnywhere }
            Text { text: "+9 Talents"; color: "#2C7A2C"; font.pixelSize: 12; font.bold: true }
        }
        
                }
            }

            Rectangle {
                Layout.fillWidth: true; Layout.preferredHeight: 46
                color: "#FFF9EC"; border.color: "#D9AF63"; border.width: 2; radius: 4
                RowLayout {
                    anchors.centerIn: parent; spacing: 20
                    Text { text: "国库净变化: -193 Talents"; color: "#C45151"; font.pixelSize: 15; font.bold: true }
                    Rectangle { width: 1; height: 24; color: "#D9AF63" }
                    Text { text: "新余额: 307 Talents"; color: "#2E251B"; font.pixelSize: 15; font.bold: true }
                }
            }
        }
    }
}
