// GlassToast — 玻璃轻提示（顶部居中，自动消隐）
//
// 由宿主（Main.qml）放置并调用：
//   toast.show("保存成功")        信息样式
//   toast.show("失败", true)      错误样式
import QtQuick
import "../theme"

Item {
    id: root

    property int duration: 2800

    width: bubble.width
    height: bubble.height
    opacity: 0
    visible: opacity > 0

    function show(text, isError) {
        label.text = text
        bubble.isError = isError === true
        hideTimer.stop()
        appearAnim.restart()
        hideTimer.start()
    }

    GlassPanel {
        id: bubble
        property bool isError: false
        width: label.implicitWidth + Theme.spaceXL * 2
        height: label.implicitHeight + Theme.spaceM * 2
        radius: Theme.radiusM
        specularOpacity: 0.4
        fillTop: bubble.isError ? Qt.alpha(Theme.danger, 0.30) : Qt.alpha("#1D2447", 0.92)
        fillBottom: bubble.isError ? Qt.alpha(Theme.danger, 0.14) : Qt.alpha("#12172E", 0.92)
        borderTop: bubble.isError ? Qt.alpha(Theme.danger, 0.65) : Theme.glassBorderTop

        Text {
            id: label
            anchors.centerIn: parent
            color: Theme.textPrimary
            font.pixelSize: Theme.fontM
            wrapMode: Text.Wrap
        }
    }

    SequentialAnimation {
        id: appearAnim
        NumberAnimation { target: root; property: "opacity"; from: 0; to: 1
                          duration: Theme.animMed; easing.type: Easing.OutQuad }
    }
    NumberAnimation {
        id: disappearAnim
        target: root; property: "opacity"; to: 0
        duration: Theme.animSlow; easing.type: Easing.InQuad
    }
    Timer {
        id: hideTimer
        interval: root.duration
        onTriggered: disappearAnim.restart()
    }
}
