// GlassIconButton — 小型玻璃图标按钮（文字符号作图标）
//
// 用于标题栏窗口按钮、列表行内操作等紧凑场景。
import QtQuick
import "../theme"

Item {
    id: root

    property string glyph: ""
    property string tip: ""
    property bool danger: false
    property int size: 30
    signal clicked()

    enabled: true
    implicitWidth: size
    implicitHeight: size
    opacity: enabled ? 1.0 : 0.4

    GlassPanel {
        anchors.fill: parent
        radius: Theme.radiusS
        specularOpacity: 0.4
        shadow: false      // 紧凑图标按钮不需要悬浮投影
        sheen: false
        edgeLight: false
        fillTop: mouse.containsMouse
                 ? (root.danger ? Qt.alpha(Theme.danger, 0.35) : Qt.alpha("#FFFFFF", 0.20))
                 : Qt.alpha("#FFFFFF", 0.08)
        fillBottom: "transparent"
        borderTop: mouse.containsMouse && root.danger
                   ? Qt.alpha(Theme.danger, 0.6) : Theme.glassBorderTop

        Text {
            anchors.centerIn: parent
            text: root.glyph
            color: mouse.containsMouse && root.danger ? Theme.danger : Theme.textSecondary
            font.pixelSize: Theme.fontM
        }
    }

    MouseArea {
        id: mouse
        anchors.fill: parent
        hoverEnabled: true
        cursorShape: root.enabled ? Qt.PointingHandCursor : Qt.ArrowCursor
        onClicked: if (root.enabled) root.clicked()
    }

    // 悬停提示（自绘轻量 tooltip，避免依赖平台样式）
    GlassPanel {
        id: tipBubble
        visible: root.tip !== "" && mouse.containsMouse
        anchors.top: parent.bottom
        anchors.topMargin: Theme.spaceXS
        anchors.horizontalCenter: parent.horizontalCenter
        width: tipText.implicitWidth + Theme.spaceM * 2
        height: tipText.implicitHeight + Theme.spaceS
        radius: Theme.radiusS
        specularOpacity: 0.2
        shadow: false
        sheen: false
        edgeLight: false
        z: 100
        Text {
            id: tipText
            anchors.centerIn: parent
            text: root.tip
            color: Theme.textSecondary
            font.pixelSize: Theme.fontS
        }
    }
}
