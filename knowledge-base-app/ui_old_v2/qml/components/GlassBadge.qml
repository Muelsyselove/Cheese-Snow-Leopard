// GlassBadge — 状态徽标（小型玻璃胶囊）
//
// tone: "info" | "success" | "warning" | "danger" | "muted"
import QtQuick
import "../theme"

Item {
    id: root

    property string text: ""
    property string tone: "muted"

    implicitWidth: label.implicitWidth + Theme.spaceM * 2
    implicitHeight: label.implicitHeight + Theme.spaceXS * 2

    readonly property color toneColor: tone === "info" ? Theme.accent
                                     : tone === "success" ? Theme.success
                                     : tone === "warning" ? Theme.warning
                                     : tone === "danger" ? Theme.danger
                                     : Theme.textMuted

    GlassPanel {
        anchors.fill: parent
        radius: height / 2
        specularOpacity: 0.3
        shadow: false      // 小型胶囊不需要悬浮投影
        sheen: false
        edgeLight: false
        fillTop: Qt.alpha(root.toneColor, 0.22)
        fillBottom: Qt.alpha(root.toneColor, 0.08)
        borderTop: Qt.alpha(root.toneColor, 0.45)
        borderBottom: Qt.alpha(root.toneColor, 0.15)

        Text {
            id: label
            anchors.centerIn: parent
            text: root.text
            color: root.toneColor
            font.pixelSize: Theme.fontS
        }
    }
}
