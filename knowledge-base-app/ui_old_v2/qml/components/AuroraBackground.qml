// AuroraBackground — 柔和智能渐变背景（不透明）
//
// 深空午夜蓝基底 + 三团缓慢流动的环境光斑（有机形态）+ 顶部微高光。
// 作为整个窗口的最底层，所有玻璃面板叠加其上产生折射感。
// 不透明设计，符合用户"背景不要透明"的要求。
import QtQuick
import Qt5Compat.GraphicalEffects as FX
import "../theme"

Rectangle {
    id: root

    // 窗口最大化时直角，否则圆角（与 DWM 圆角配合）
    property bool rounded: true

    radius: rounded ? Theme.radiusWindow : 0
    clip: true

    gradient: Gradient {
        GradientStop { position: 0.0; color: Theme.bgTop }
        GradientStop { position: 0.45; color: Theme.bgMid }
        GradientStop { position: 1.0; color: Theme.bgBottom }
    }

    // ---- 环境光斑：青（大而柔和，缓慢漂移） ----
    FX.RadialGradient {
        id: blobCyan
        width: Math.max(parent.width * 0.70, 520)
        height: width
        x: parent.width * 0.05
        y: -height * 0.30
        opacity: 0.42
        gradient: Gradient {
            GradientStop { position: 0.0; color: Qt.alpha(Theme.blobCyan, 0.68) }
            GradientStop { position: 0.4; color: Qt.alpha(Theme.blobCyan, 0.22) }
            GradientStop { position: 1.0; color: "transparent" }
        }
        SequentialAnimation {
            loops: Animation.Infinite
            running: root.visible
            XAnimator { target: blobCyan; from: root.width * 0.05; to: root.width * 0.32
                        duration: 19000; easing.type: Easing.InOutSine }
            XAnimator { target: blobCyan; from: root.width * 0.32; to: root.width * 0.05
                        duration: 21000; easing.type: Easing.InOutSine }
        }
        SequentialAnimation {
            loops: Animation.Infinite
            running: root.visible
            YAnimator { target: blobCyan; from: -blobCyan.height * 0.30; to: root.height * 0.15
                        duration: 23000; easing.type: Easing.InOutSine }
            YAnimator { target: blobCyan; from: root.height * 0.15; to: -blobCyan.height * 0.30
                        duration: 25000; easing.type: Easing.InOutSine }
        }
    }

    // ---- 环境光斑：紫（右侧，稍小） ----
    FX.RadialGradient {
        id: blobViolet
        width: Math.max(parent.width * 0.62, 480)
        height: width
        x: parent.width * 0.52
        y: parent.height * 0.02
        opacity: 0.38
        gradient: Gradient {
            GradientStop { position: 0.0; color: Qt.alpha(Theme.blobViolet, 0.65) }
            GradientStop { position: 0.45; color: Qt.alpha(Theme.blobViolet, 0.20) }
            GradientStop { position: 1.0; color: "transparent" }
        }
        SequentialAnimation {
            loops: Animation.Infinite
            running: root.visible
            XAnimator { target: blobViolet; from: root.width * 0.52; to: root.width * 0.28
                        duration: 22000; easing.type: Easing.InOutSine }
            XAnimator { target: blobViolet; from: root.width * 0.28; to: root.width * 0.52
                        duration: 20000; easing.type: Easing.InOutSine }
        }
        SequentialAnimation {
            loops: Animation.Infinite
            running: root.visible
            YAnimator { target: blobViolet; from: root.height * 0.02; to: root.height * 0.48
                        duration: 26000; easing.type: Easing.InOutSine }
            YAnimator { target: blobViolet; from: root.height * 0.48; to: root.height * 0.02
                        duration: 24000; easing.type: Easing.InOutSine }
        }
    }

    // ---- 环境光斑：粉（底部，极淡，营造空间感） ----
    FX.RadialGradient {
        id: blobPink
        width: Math.max(parent.width * 0.55, 420)
        height: width
        x: parent.width * 0.30
        y: parent.height * 0.58
        opacity: 0.26
        gradient: Gradient {
            GradientStop { position: 0.0; color: Qt.alpha(Theme.blobPink, 0.55) }
            GradientStop { position: 0.5; color: Qt.alpha(Theme.blobPink, 0.15) }
            GradientStop { position: 1.0; color: "transparent" }
        }
        SequentialAnimation {
            loops: Animation.Infinite
            running: root.visible
            XAnimator { target: blobPink; from: root.width * 0.30; to: root.width * 0.62
                        duration: 27000; easing.type: Easing.InOutSine }
            XAnimator { target: blobPink; from: root.width * 0.62; to: root.width * 0.30
                        duration: 29000; easing.type: Easing.InOutSine }
        }
    }

    // ---- 顶部微高光（模拟环境光源从上方照射） ----
    Rectangle {
        anchors.left: parent.left
        anchors.right: parent.right
        anchors.top: parent.top
        height: parent.height * 0.28
        radius: root.radius
        gradient: Gradient {
            GradientStop { position: 0.0; color: Qt.alpha("#FFFFFF", 0.07) }
            GradientStop { position: 0.5; color: Qt.alpha("#FFFFFF", 0.02) }
            GradientStop { position: 1.0; color: "transparent" }
        }
    }

    // ---- 底部暗角（增强深度，让面板有"浮起"感） ----
    Rectangle {
        anchors.left: parent.left
        anchors.right: parent.right
        anchors.bottom: parent.bottom
        height: parent.height * 0.22
        radius: root.radius
        gradient: Gradient {
            GradientStop { position: 0.0; color: "transparent" }
            GradientStop { position: 1.0; color: Qt.alpha("#000000", 0.18) }
        }
    }
}
