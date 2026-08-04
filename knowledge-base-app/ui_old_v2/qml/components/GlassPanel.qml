// GlassPanel — 液态玻璃基础面板（真 3D 材质系统）
//
// 参考 Apple Liquid Glass（iOS 26）设计语言：
//   1. 悬浮深度 — 面板浮于背景之上，带柔和环境投影
//   2. 边缘透镜 — 顶部亮边弯折光线，底部焦散折射环境色
//   3. 内部发光 — 对角流光带 + 顶部镜面高光
//   4. 厚度感   — 底部内阴影模拟玻璃厚度
//
// 材质分层（底→顶）：
//   环境投影 → 折射描边 → 半透明基色 → 底部内阴影 → 底部焦散
//   → 对角流光 → 顶部镜面高光 → 顶部亮边 → 内容
//
// 可选 glow：聚焦/激活时的外部辉光描边。
// 子元素通过默认属性放入内容区（自动内缩避开描边）。
import QtQuick
import Qt5Compat.GraphicalEffects as FX
import "../theme"

Item {
    id: root

    // ---- 外观参数 ----
    property real radius: Theme.radiusL
    property color fillTop: Theme.glassFillTop
    property color fillBottom: Theme.glassFillBottom
    property color borderTop: Theme.glassBorderTop
    property color borderBottom: Theme.glassBorderBottom
    // 顶部镜面高光强度（0 = 关闭）
    property real specularOpacity: 0.45
    // 悬浮投影（3D 深度）
    property bool shadow: true
    // 对角流光（内部发光质感）
    property bool sheen: true
    // 边缘透镜光（顶部亮边 + 底部焦散）
    property bool edgeLight: true
    // 焦散色调（默认取主强调色，折射环境光）
    property color causticColor: Theme.accent
    // 辉光（聚焦/激活）
    property bool glow: false
    property color glowColor: Theme.accent

    // ---- 内容区 ----
    default property alias contentData: contentHost.data

    implicitWidth: 100
    implicitHeight: 60

    // 辉光（双层描边，外软内锐）
    Rectangle {
        anchors.fill: parent
        anchors.margins: -5
        radius: root.radius + 5
        color: "transparent"
        border.color: root.glowColor
        border.width: 3
        opacity: root.glow ? 0.22 : 0
        Behavior on opacity { NumberAnimation { duration: Theme.animMed } }
    }
    Rectangle {
        anchors.fill: parent
        anchors.margins: -2
        radius: root.radius + 2
        color: "transparent"
        border.color: root.glowColor
        border.width: 1
        opacity: root.glow ? 0.55 : 0
        Behavior on opacity { NumberAnimation { duration: Theme.animMed } }
    }

    // ---- 悬浮投影（面板浮于背景之上的深度感） ----
    FX.RectangularGlow {
        visible: root.shadow
        anchors.fill: body
        anchors.topMargin: 4          // 光源在上方，投影偏下
        glowRadius: 14
        spread: 0.12
        color: "#59000000"
        cornerRadius: body.radius + glowRadius * 0.5
        z: -1
    }

    // ---- 玻璃体 ----
    Item {
        id: body
        anchors.fill: parent

        // 层：折射描边（上亮下暗，模拟玻璃边缘聚光）
        Rectangle {
            anchors.fill: parent
            radius: root.radius
            gradient: Gradient {
                GradientStop { position: 0.0; color: root.borderTop }
                GradientStop { position: 0.5; color: Qt.alpha(root.borderBottom, 0.5) }
                GradientStop { position: 1.0; color: root.borderBottom }
            }
        }

        Item {
            id: inner
            anchors.fill: parent
            anchors.margins: 1
            clip: true

            // 层：半透明基色
            Rectangle {
                anchors.fill: parent
                radius: Math.max(root.radius - 1, 0)
                gradient: Gradient {
                    GradientStop { position: 0.0; color: root.fillTop }
                    GradientStop { position: 1.0; color: root.fillBottom }
                }
            }

            // 层：底部内阴影（玻璃厚度感，下缘暗部）
            Rectangle {
                visible: root.edgeLight
                anchors.left: parent.left
                anchors.right: parent.right
                anchors.bottom: parent.bottom
                height: Math.max(parent.height * 0.38, 12)
                radius: Math.max(root.radius - 1, 0)
                gradient: Gradient {
                    GradientStop { position: 0.0; color: "transparent" }
                    GradientStop { position: 1.0; color: Theme.glassInnerShadow }
                }
            }

            // 层：底部焦散（环境色在玻璃下缘的折射亮线）
            Rectangle {
                visible: root.edgeLight
                anchors.left: parent.left
                anchors.right: parent.right
                anchors.bottom: parent.bottom
                anchors.leftMargin: parent.width * 0.08
                anchors.rightMargin: parent.width * 0.08
                height: 3
                radius: 1.5
                opacity: 0.5
                gradient: Gradient {
                    orientation: Gradient.Horizontal
                    GradientStop { position: 0.0; color: "transparent" }
                    GradientStop { position: 0.5; color: Qt.alpha(root.causticColor, 0.55) }
                    GradientStop { position: 1.0; color: "transparent" }
                }
            }

            // 层：对角流光带（内部发光质感，随面板尺寸自适应角度）
            Rectangle {
                visible: root.sheen
                anchors.centerIn: parent
                width: parent.height * 2.4
                height: parent.height * 0.85
                rotation: -24
                opacity: 0.10
                gradient: Gradient {
                    orientation: Gradient.Horizontal
                    GradientStop { position: 0.35; color: "transparent" }
                    GradientStop { position: 0.5; color: "#BFFFFFFF" }
                    GradientStop { position: 0.65; color: "transparent" }
                }
            }

            // 层：顶部镜面高光（大面积柔和反射）
            Rectangle {
                anchors.left: parent.left
                anchors.right: parent.right
                anchors.top: parent.top
                anchors.margins: 1
                height: Math.max(parent.height * 0.45, 10)
                radius: Math.max(root.radius - 2, 0)
                visible: root.specularOpacity > 0
                opacity: root.specularOpacity
                gradient: Gradient {
                    GradientStop { position: 0.0; color: Theme.glassSpecular }
                    GradientStop { position: 1.0; color: "transparent" }
                }
            }

            // 层：顶部亮边（光线在玻璃上缘弯折形成的锐利高光线）
            Rectangle {
                visible: root.edgeLight
                anchors.left: parent.left
                anchors.right: parent.right
                anchors.top: parent.top
                anchors.leftMargin: parent.width * 0.06
                anchors.rightMargin: parent.width * 0.06
                height: 1.5
                radius: 0.75
                opacity: 0.8
                gradient: Gradient {
                    orientation: Gradient.Horizontal
                    GradientStop { position: 0.0; color: "transparent" }
                    GradientStop { position: 0.25; color: Qt.alpha("#FFFFFF", 0.75) }
                    GradientStop { position: 0.75; color: Qt.alpha("#FFFFFF", 0.75) }
                    GradientStop { position: 1.0; color: "transparent" }
                }
            }

            Item {
                id: contentHost
                anchors.fill: parent
            }
        }
    }
}
