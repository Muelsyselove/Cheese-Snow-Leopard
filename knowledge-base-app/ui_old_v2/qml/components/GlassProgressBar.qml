// GlassProgressBar — 玻璃进度条
//
// value 0..1；indeterminate 时流光往返滑动（未知进度任务）。
import QtQuick
import "../theme"

Item {
    id: root

    property real value: 0.0            // 0..1
    property bool indeterminate: false
    property string text: ""            // 右侧附加文本（可为空）

    implicitHeight: Theme.spaceS + 10

    GlassPanel {
        id: track
        anchors.left: parent.left
        anchors.right: parent.right
        anchors.verticalCenter: parent.verticalCenter
        height: 10
        radius: 5
        specularOpacity: 0.25
        fillTop: Qt.alpha("#FFFFFF", 0.08)
        fillBottom: Qt.alpha("#FFFFFF", 0.03)

        Item {
            anchors.fill: parent
            anchors.margins: 2
            clip: true

            // 确定进度填充
            Rectangle {
                visible: !root.indeterminate
                width: Math.max(parent.width * root.value, height)
                height: parent.height
                radius: height / 2
                gradient: Gradient {
                    orientation: Gradient.Horizontal
                    GradientStop { position: 0.0; color: Theme.accent }
                    GradientStop { position: 1.0; color: Theme.accentViolet }
                }
                Behavior on width { NumberAnimation { duration: Theme.animMed } }
            }

            // 不定进度流光
            Rectangle {
                id: shimmer
                visible: root.indeterminate
                width: parent.width * 0.35
                height: parent.height
                radius: height / 2
                gradient: Gradient {
                    orientation: Gradient.Horizontal
                    GradientStop { position: 0.0; color: "transparent" }
                    GradientStop { position: 0.5; color: Theme.accent }
                    GradientStop { position: 1.0; color: "transparent" }
                }
                SequentialAnimation on x {
                    loops: Animation.Infinite
                    running: root.indeterminate && root.visible
                    NumberAnimation { from: -shimmer.width; to: track.width
                                      duration: 1200; easing.type: Easing.InOutQuad }
                }
            }
        }
    }

    Text {
        visible: root.text !== ""
        anchors.left: parent.left
        anchors.top: track.bottom
        anchors.topMargin: Theme.spaceXS
        text: root.text
        color: Theme.textMuted
        font.pixelSize: Theme.fontXS
        elide: Text.ElideRight
        width: parent.width
    }
}
