import QtQuick 2.15
import QtQuick.Controls 2.15
import QtQuick.Layouts 1.15


Rectangle {
    id: root
    height: 32
    width: 120
    radius: theme.radius
    color: theme.bgSurface2
    border.color: theme.borderNormal
    border.width: 1

    property int value: 10
    property int minValue: 1
    property int maxValue: 100
    property int step: 1

    RowLayout {
        anchors.fill: parent
        spacing: 0

        Rectangle {
            Layout.preferredWidth: 32
            Layout.fillHeight: true
            color: mouseAreaMinus.containsPress ? theme.bgSurface3 : "transparent"
            Text {
                anchors.centerIn: parent
                text: "−"
                color: theme.textPrimary
                font.pixelSize: 14
                font.bold: true
            }
            MouseArea {
                id: mouseAreaMinus
                anchors.fill: parent
                onClicked: {
                    if (root.value - root.step >= root.minValue)
                        root.value -= root.step
                }
            }
        }

        Rectangle {
            Layout.fillWidth: true
            Layout.fillHeight: true
            color: "transparent"
            TextInput {
                anchors.centerIn: parent
                text: root.value
                color: theme.textPrimary
                font.pixelSize: 12
                horizontalAlignment: Text.AlignHCenter
                validator: IntValidator { bottom: root.minValue; top: root.maxValue }
                onEditingFinished: {
                    var v = parseInt(text)
                    if (!isNaN(v)) root.value = v
                }
            }
        }

        Rectangle {
            Layout.preferredWidth: 32
            Layout.fillHeight: true
            color: mouseAreaPlus.containsPress ? theme.bgSurface3 : "transparent"
            Text {
                anchors.centerIn: parent
                text: "+"
                color: theme.textPrimary
                font.pixelSize: 14
                font.bold: true
            }
            MouseArea {
                id: mouseAreaPlus
                anchors.fill: parent
                onClicked: {
                    if (root.value + root.step <= root.maxValue)
                        root.value += root.step
                }
            }
        }
    }
}
