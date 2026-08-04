// GlassAvatar — 悬浮玻璃头像
//
// role: "user"（青色调）/ "assistant"（紫色调）
// 圆形玻璃 + 角色文字，边缘带色调辉光环。
import QtQuick
import "../theme"

Item {
    id: root

    property string role: "assistant"     // user | assistant
    property string text: ""
    property int size: Theme.avatarSize

    implicitWidth: size
    implicitHeight: size

    readonly property color tone: role === "user" ? Theme.accent : Theme.accentViolet

    // 辉光环
    Rectangle {
        anchors.centerIn: parent
        width: parent.width + 6
        height: width
        radius: width / 2
        color: "transparent"
        border.color: root.tone
        border.width: 2
        opacity: 0.35
    }

    GlassPanel {
        anchors.fill: parent
        radius: width / 2
        specularOpacity: 0.6
        fillTop: Qt.alpha(root.tone, 0.42)
        fillBottom: Qt.alpha(root.tone, 0.16)
        borderTop: Qt.alpha(root.tone, 0.75)
        borderBottom: Qt.alpha(root.tone, 0.25)

        Text {
            anchors.centerIn: parent
            text: root.text
            color: Theme.textPrimary
            font.pixelSize: root.text.length <= 2 ? Theme.fontS : Theme.fontXS
            font.bold: true
        }
    }
}
