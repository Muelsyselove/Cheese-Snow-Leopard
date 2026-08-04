// GlassCheckBox — 玻璃复选框（可选带文字标签）
import QtQuick
import "../theme"

Item {
    id: root

    property bool checked: false
    property string text: ""
    signal toggled(bool checked)

    implicitWidth: box.implicitWidth + (text !== "" ? Theme.spaceS + label.implicitWidth : 0)
    implicitHeight: Math.max(box.implicitHeight, label.implicitHeight)

    GlassPanel {
        id: box
        anchors.left: parent.left
        anchors.verticalCenter: parent.verticalCenter
        width: 20
        height: 20
        radius: 6
        specularOpacity: 0.4
        fillTop: root.checked ? Qt.alpha(Theme.accent, 0.45) : Qt.alpha("#FFFFFF", 0.10)
        fillBottom: root.checked ? Qt.alpha(Theme.accent, 0.20) : Qt.alpha("#FFFFFF", 0.04)
        borderTop: root.checked ? Qt.alpha(Theme.accent, 0.7) : Theme.glassBorderTop

        Text {
            anchors.centerIn: parent
            text: "✓"
            color: Theme.textPrimary
            font.pixelSize: Theme.fontS
            font.bold: true
            opacity: root.checked ? 1 : 0
            scale: root.checked ? 1 : 0.5
            Behavior on opacity { NumberAnimation { duration: Theme.animFast } }
            Behavior on scale { NumberAnimation { duration: Theme.animFast; easing.type: Easing.OutBack } }
        }
    }

    Text {
        id: label
        anchors.left: box.right
        anchors.leftMargin: Theme.spaceS
        anchors.verticalCenter: parent.verticalCenter
        visible: root.text !== ""
        text: root.text
        color: Theme.textPrimary
        font.pixelSize: Theme.fontM
        elide: Text.ElideRight
    }

    MouseArea {
        anchors.fill: parent
        cursorShape: Qt.PointingHandCursor
        onClicked: root.toggled(!root.checked)
    }
}
