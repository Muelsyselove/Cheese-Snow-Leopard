// TitleBar — 自定义标题栏（拖动 / 双击最大化 / 最小化 / 最大化 / 关闭）
import QtQuick
import "../theme"

Item {
    id: root

    property var targetWindow: null
    property string title: ""

    implicitHeight: Theme.titleBarHeight

    // 拖动 / 双击最大化
    MouseArea {
        anchors.fill: parent
        anchors.rightMargin: buttonsRow.width
        onDoubleClicked: root.toggleMaximize()
        DragHandler {
            target: null
            acceptedButtons: Qt.LeftButton
            onActiveChanged: if (active && root.targetWindow) root.targetWindow.startSystemMove()
        }
    }

    function toggleMaximize() {
        if (!root.targetWindow) return
        if (root.targetWindow.visibility === 4 /* Window.Maximized */)
            root.targetWindow.showNormal()
        else
            root.targetWindow.showMaximized()
    }

    // 应用名
    Text {
        anchors.left: parent.left
        anchors.leftMargin: Theme.spaceM
        anchors.verticalCenter: parent.verticalCenter
        text: root.title
        color: Theme.textSecondary
        font.pixelSize: Theme.fontS
    }

    // 窗口控制按钮
    Row {
        id: buttonsRow
        anchors.right: parent.right
        anchors.rightMargin: Theme.spaceS
        anchors.verticalCenter: parent.verticalCenter
        spacing: Theme.spaceXS

        GlassIconButton {
            glyph: "—"
            tip: (i18n.language, i18n.tr("window.minimize"))
            size: 32
            onClicked: if (root.targetWindow) root.targetWindow.showMinimized()
        }
        GlassIconButton {
            glyph: root.targetWindow && root.targetWindow.visibility === 4 ? "❐" : "▢"
            tip: root.targetWindow && root.targetWindow.visibility === 4
                 ? (i18n.language, i18n.tr("window.restore"))
                 : (i18n.language, i18n.tr("window.maximize"))
            size: 32
            onClicked: root.toggleMaximize()
        }
        GlassIconButton {
            glyph: "✕"
            tip: (i18n.language, i18n.tr("window.closeTip"))
            size: 32
            danger: true
            onClicked: if (root.targetWindow) root.targetWindow.close()
        }
    }
}
