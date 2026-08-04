// GlassSwitch — 玻璃开关
//
// 开启时轨道泛出主强调色辉光，滑块平滑滑动。
import QtQuick
import "../theme"

Item {
    id: root

    property bool checked: false
    signal toggled(bool checked)

    implicitWidth: 44
    implicitHeight: 24

    GlassPanel {
        anchors.fill: parent
        radius: height / 2
        specularOpacity: 0.4
        glow: root.checked
        glowColor: Theme.accent
        fillTop: root.checked ? Qt.alpha(Theme.accent, 0.40) : Qt.alpha("#FFFFFF", 0.10)
        fillBottom: root.checked ? Qt.alpha(Theme.accent, 0.18) : Qt.alpha("#FFFFFF", 0.04)
        borderTop: root.checked ? Qt.alpha(Theme.accent, 0.6) : Theme.glassBorderTop
        Behavior on fillTop { ColorAnimation { duration: Theme.animMed } }
        Behavior on fillBottom { ColorAnimation { duration: Theme.animMed } }
    }

    // 滑块（玻璃球）
    Rectangle {
        id: knob
        width: root.height - 6
        height: width
        radius: width / 2
        y: 3
        x: root.checked ? root.width - width - 3 : 3
        gradient: Gradient {
            GradientStop { position: 0.0; color: "#F5FFFFFF" }
            GradientStop { position: 1.0; color: "#B8FFFFFF" }
        }
        Behavior on x { NumberAnimation { duration: Theme.animMed; easing.type: Easing.OutCubic } }
    }

    MouseArea {
        anchors.fill: parent
        cursorShape: Qt.PointingHandCursor
        onClicked: root.toggled(!root.checked)
    }
}
