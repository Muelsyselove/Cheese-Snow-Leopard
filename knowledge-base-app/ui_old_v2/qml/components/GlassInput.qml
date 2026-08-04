// GlassInput — 单行玻璃输入框（聚焦时辉光）
import QtQuick
import "../theme"

Item {
    id: root

    property alias text: field.text
    property string placeholder: ""
    property alias echoMode: field.echoMode
    property bool readOnly: false
    signal accepted()
    signal textEdited()

    implicitHeight: Theme.inputHeight

    GlassPanel {
        anchors.fill: parent
        radius: Theme.radiusM
        specularOpacity: 0.35
        glow: field.activeFocus
        glowColor: Theme.accent

        Text {
            anchors.left: parent.left
            anchors.leftMargin: Theme.spaceM
            anchors.verticalCenter: parent.verticalCenter
            visible: field.text === "" && !field.activeFocus
            text: root.placeholder
            color: Theme.textMuted
            font.pixelSize: Theme.fontM
        }

        TextInput {
            id: field
            anchors.fill: parent
            anchors.leftMargin: Theme.spaceM
            anchors.rightMargin: Theme.spaceM
            verticalAlignment: TextInput.AlignVCenter
            color: Theme.textPrimary
            font.pixelSize: Theme.fontM
            clip: true
            readOnly: root.readOnly
            selectByMouse: true
            selectedTextColor: Theme.textPrimary
            selectionColor: Qt.alpha(Theme.accent, 0.45)
            onAccepted: root.accepted()
            onTextEdited: root.textEdited()
        }
    }
}
