// ElectionResultView.qml — v2.0 只读选举结果展示组件
// NOT_USED: 2026-08-09 AC-12 M2-BUG2 — 选举结果展示已内嵌至 PopulationStage candidateTable；
//   本文件保留为归档参考。如需恢复独立选举结果区，反注此标记并重新实例化。
//   原注册入口: app.py L107 os.path.join("stages", "ElectionResultView.qml")
// 用于展示 populationResolved 后的完整选举结果（含 per-candidate scores）
// 数据源：results 属性绑定 sessionStore.populationElectionResults

import QtQuick 2.15
import QtQuick.Layouts 1.15

Rectangle {
    id: root
    property var results: []  // sessionStore.populationElectionResults
    color: "transparent"

    ColumnLayout {
        anchors.fill: parent
        spacing: 10

        // Header
        Text {
            text: "🏆 选举结果"
            color: "#681B07"
            font.pixelSize: 14
            font.bold: true
        }

        // Per-office result cards
        ListView {
            Layout.fillWidth: true
            Layout.fillHeight: true
            clip: true
            spacing: 8
            model: root.results || []
            delegate: resultCard
        }
    }

    Component {
        id: resultCard
        Rectangle {
            width: parent ? parent.width : 200
            height: resultContent.implicitHeight + 24
            color: "#FFF9EC"
            radius: 6
            border.color: "#D4A574"
            border.width: 1

            // Captures the outer election result entry for per-candidate winner check
            property var parentWinner: modelData

            ColumnLayout {
                id: resultContent
                anchors.fill: parent
                anchors.margins: 8
                spacing: 4

                // Office + Winner
                RowLayout {
                    Text {
                        text: {
                            var names = {consul: "🛡 执政官", censor: "📜 监察官",
                                        praetor: "⚖ 大法官", quaestor: "💰 财务官",
                                        tribune: "🛡 保民官"}
                            return names[modelData.office] || modelData.office
                        }
                        font.bold: true
                        font.pixelSize: 12
                    }
                    Item { Layout.fillWidth: true }
                    Text {
                        text: "✅ 当选：" + modelData.figure_name
                        color: "#008000"
                        font.bold: true
                        font.pixelSize: 13
                    }
                }

                // Score per candidate (LOW-07 AC-06/FV-15)
                Repeater {
                    model: modelData.candidates || []
                    delegate: RowLayout {
                        Text {
                            text: "  " + modelData.figure_name
                            font.pixelSize: 10
                            color: "#2C1E12"
                            Layout.preferredWidth: 190
                        }
                        Text {
                            text: modelData.faction_id  // faction short name
                            font.pixelSize: 10
                            color: "#766652"
                            Layout.preferredWidth: 60
                        }
                        Text {
                            text: "得分：" + modelData.score
                            font.pixelSize: 11
                            font.bold: modelData.figure_id === parentWinner.figure_id
                            color: modelData.figure_id === parentWinner.figure_id ? "#8B2500" : "#2C1E12"
                            Layout.preferredWidth: 80
                        }
                    }
                }
            }
        }
    }
}
