import QtQuick 2.15
import QtQuick.Controls 2.15
import QtQuick.Layouts 1.15


Rectangle {
    id: root
    color: "#CC000000"
    visible: false

    property string title: "确认"
    property string message: ""
    property string confirmText: "确认"
    property string cancelText: "取消"

    signal confirmed
    signal cancelled

    function show(title, message) {
        root.title = title
        root.message = message
        root.visible = true
    }

    MouseArea {
        anchors.fill: parent
        onClicked: {} // 阻止点击穿透
    }

    Rectangle {
        anchors.centerIn: parent
        width: 360
        height: contentLayout.height + 48
        color: theme.bgSurface1
        radius: theme.radius
        border.color: theme.borderStrong
        border.width: 1

        ColumnLayout {
            id: contentLayout
            anchors.top: parent.top
            anchors.left: parent.left
            anchors.right: parent.right
            anchors.margins: 24
            spacing: 16

            Text {
                text: root.title
                color: theme.textPrimary
                font.pixelSize: 16
                font.bold: true
            }
            Text {
                text: root.message
                color: theme.textSecondary
                font.pixelSize: 12
                wrapMode: Text.Wrap
                Layout.fillWidth: true
            }
            RowLayout {
                spacing: 12
                Layout.alignment: Qt.AlignRight
                AppButton {
                    text: root.cancelText
                    type: "secondary"
                    onClicked: {
                        root.visible = false
                        root.cancelled()
                    }
                }
                AppButton {
                    text: root.confirmText
                    type: "primary"
                    onClicked: {
                        root.visible = false
                        root.confirmed()
                    }
                }
            }
        }
    }
}
