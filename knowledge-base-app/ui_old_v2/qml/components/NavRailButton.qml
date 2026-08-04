// NavRailButton — 侧边导航按钮
//
// 激活态：主强调色玻璃 + 左侧光条；悬停：中性玻璃淡入。
import QtQuick
import "../theme"

Item {
    id: root

    property string icon: ""
    property string text: ""
    property bool active: false
    signal clicked()

    implicitHeight: 44

    // 激活光条
    Rectangle {
        anchors.left: parent.left
        anchors.verticalCenter: parent.verticalCenter
        width: 3
        height: root.active ? parent.height * 0.55 : 0
        radius: 2
        color: Theme.accent
        Behavior on height { NumberAnimation { duration: Theme.animMed; easing.type: Easing.OutCubic } }
    }

    GlassPanel {
        anchors.fill: parent
        anchors.leftMargin: Theme.spaceS
        radius: Theme.radiusM
        specularOpacity: 0.35
        shadow: false      // 导航条目不需要悬浮投影
        sheen: false
        opacity: root.active || mouse.containsMouse ? 1 : 0
        fillTop: root.active ? Qt.alpha(Theme.accent, 0.30) : Qt.alpha("#FFFFFF", 0.12)
        fillBottom: root.active ? Qt.alpha(Theme.accent, 0.10) : Qt.alpha("#FFFFFF", 0.05)
        borderTop: root.active ? Qt.alpha(Theme.accent, 0.55) : Theme.glassBorderTop
        Behavior on opacity { NumberAnimation { duration: Theme.animFast } }
    }

    Row {
        anchors.left: parent.left
        anchors.leftMargin: Theme.spaceL
        anchors.verticalCenter: parent.verticalCenter
        spacing: Theme.spaceM

        Text {
            text: root.icon
            font.pixelSize: Theme.fontL
            color: root.active ? Theme.accent : Theme.textSecondary
            anchors.verticalCenter: parent.verticalCenter
        }
        Text {
            text: root.text
            font.pixelSize: Theme.fontM
            color: root.active ? Theme.textPrimary : Theme.textSecondary
            anchors.verticalCenter: parent.verticalCenter
        }
    }

    MouseArea {
        id: mouse
        anchors.fill: parent
        hoverEnabled: true
        cursorShape: Qt.PointingHandCursor
        onClicked: root.clicked()
    }
}
