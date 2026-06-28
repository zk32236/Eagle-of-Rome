import QtQuick 2.15
import QtQuick.Controls 2.15
import QtQuick.Layouts 1.15


Rectangle {
    id: root
    color: theme.bgSurface2
    radius: theme.radius
    border.color: theme.borderNormal
    border.width: 1

    property var columns: []
    property var modelData: []
    property int selectedRow: -1

    ColumnLayout {
        anchors.fill: parent
        spacing: 0

        // 表头
        Rectangle {
            Layout.fillWidth: true
            height: 40
            color: theme.bgSurface3
            radius: theme.radius
            RowLayout {
                anchors.fill: parent
                anchors.leftMargin: 12
                anchors.rightMargin: 12
                spacing: 0
                Repeater {
                    model: root.columns
                    delegate: Text {
                        text: modelData.title
                        color: theme.textMuted
                        font.pixelSize: 11
                        font.bold: true
                        Layout.preferredWidth: modelData.width
                    }
                }
            }
        }

        // 数据行
        ListView {
            Layout.fillWidth: true
            Layout.fillHeight: true
            clip: true
            model: root.modelData
            spacing: 1
            delegate: Rectangle {
                width: parent.width
                height: 44
                color: index === root.selectedRow ? theme.accentPrimary : theme.bgSurface2
                border.color: index === root.selectedRow ? theme.accentPrimaryDark : "transparent"
                border.width: 1

                MouseArea {
                    anchors.fill: parent
                    onClicked: root.selectedRow = index
                }

                RowLayout {
                    anchors.fill: parent
                    anchors.leftMargin: 12
                    anchors.rightMargin: 12
                    spacing: 0
                    Repeater {
                        model: root.columns
                        delegate: Text {
                            text: {
                                var role = modelData.role
                                var item = root.modelData[index]
                                return item ? (item[role] || "") : ""
                            }
                            color: index === root.selectedRow ? "white" : theme.textPrimary
                            font.pixelSize: 12
                            Layout.preferredWidth: modelData.width
                        }
                    }
                }
            }
        }
    }
}
