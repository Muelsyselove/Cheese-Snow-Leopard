// GlassButton — 玻璃按钮
//
// variant: "primary"（青色玻璃，悬停辉光）/ "ghost"（中性玻璃）/ "danger"（红色玻璃）
// 按下微缩回弹，悬停时填充加亮。
import QtQuick
import "../theme"

Item {
    id: root

    property string text: ""
    property string variant: "primary"        // primary | ghost | danger
    property int horizontalPadding: Theme.spaceL
    signal clicked()

    enabled: true
    implicitWidth: label.implicitWidth + horizontalPadding * 2
    implicitHeight: Theme.buttonHeight
    opacity: enabled ? 1.0 : 0.45

    GlassPanel {
        anchors.fill: parent
        radius: Theme.radiusM
        specularOpacity: 0.55
        shadow: false      // 按钮紧贴面板，不需要悬浮投影
        glow: mouse.containsMouse && root.enabled && root.variant !== "ghost"
        glowColor: root.variant === "danger" ? Theme.danger : Theme.accent
        causticColor: root.variant === "danger" ? Theme.danger : Theme.accent
        fillTop: root.variant === "primary" ? Qt.alpha(Theme.accent, mouse.containsMouse ? 0.34 : 0.26)
               : root.variant === "danger"  ? Qt.alpha(Theme.danger, mouse.containsMouse ? 0.34 : 0.24)
               : Qt.alpha("#FFFFFF", mouse.containsMouse ? 0.16 : 0.10)
        fillBottom: root.variant === "primary" ? Qt.alpha(Theme.accent, 0.12)
                  : root.variant === "danger"  ? Qt.alpha(Theme.danger, 0.10)
                  : Qt.alpha("#FFFFFF", 0.05)
        borderTop: root.variant === "ghost" ? Theme.glassBorderTop
                 : Qt.alpha(root.variant === "danger" ? Theme.danger : Theme.accent, 0.55)
        borderBottom: Theme.glassBorderBottom

        Text {
            id: label
            anchors.centerIn: parent
            text: root.text
            color: Theme.textPrimary
            font.pixelSize: Theme.fontM
        }
    }

    scale: mouse.pressed ? 0.96 : 1.0
    Behavior on scale { NumberAnimation { duration: Theme.animFast; easing.type: Easing.OutQuad } }

    MouseArea {
        id: mouse
        anchors.fill: parent
        hoverEnabled: true
        cursorShape: root.enabled ? Qt.PointingHandCursor : Qt.ArrowCursor
        onClicked: if (root.enabled) root.clicked()
    }
}
