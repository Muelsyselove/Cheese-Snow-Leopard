// Main — 液态玻璃主窗口
//
// 无边框窗口 + DWM 亚克力背景（window_effects.py 应用）
// AuroraBackground 渐变光效基底 + TitleBar + 左侧导航 + 页面栈 + 状态栏 + Toast
// 边缘 6px 隐形缩放区（startSystemResize），最大化时去圆角去边距。
import QtQuick
import QtQuick.Controls
import QtQuick.Layouts
import "theme"
import "components"
import "pages"

ApplicationWindow {
    id: win

    visible: true
    width: 1240
    height: 800
    minimumWidth: 960
    minimumHeight: 620
    flags: Qt.Window | Qt.FramelessWindowHint
    // 不透明深色基底：圆角窗外区域不再透出桌面
    color: Theme.bgMid

    title: (i18n.language, i18n.tr("app.title"))

    property int page: 0
    readonly property bool maximized: visibility === Window.Maximized

    // ---------------------------------------------------------- 背景
    AuroraBackground {
        anchors.fill: parent
        rounded: !win.maximized
    }

    // ---------------------------------------------------------- 主体
    ColumnLayout {
        anchors.fill: parent
        anchors.margins: win.maximized ? 0 : Theme.windowMargin
        spacing: 0

        TitleBar {
            Layout.fillWidth: true
            targetWindow: win
            title: (i18n.language, i18n.tr("app.title"))
        }

        RowLayout {
            Layout.fillWidth: true
            Layout.fillHeight: true
            spacing: Theme.spaceM

            // ---- 导航栏 ----
            GlassPanel {
                Layout.preferredWidth: Theme.navWidth
                Layout.fillHeight: true
                radius: Theme.radiusXL

                ColumnLayout {
                    anchors.fill: parent
                    anchors.margins: Theme.spaceM
                    spacing: Theme.spaceXS

                    // 品牌区
                    RowLayout {
                        Layout.fillWidth: true
                        Layout.bottomMargin: Theme.spaceM
                        spacing: Theme.spaceM
                        GlassAvatar {
                            role: "assistant"
                            text: "🐆"
                            size: Theme.avatarSize + 4
                        }
                        Column {
                            spacing: 2
                            Text {
                                text: (i18n.language, i18n.tr("app.name"))
                                color: Theme.textPrimary
                                font.pixelSize: Theme.fontM
                                font.bold: true
                            }
                            Text {
                                text: (i18n.language, i18n.tr("app.name.en"))
                                color: Theme.textMuted
                                font.pixelSize: Theme.fontXS
                            }
                        }
                    }

                    Repeater {
                        model: [
                            { "icon": "💬", "key": "nav.chat" },
                            { "icon": "📁", "key": "nav.files" },
                            { "icon": "🏷️", "key": "nav.knowledge" },
                            { "icon": "⚙️", "key": "nav.settings" }
                        ]
                        NavRailButton {
                            Layout.fillWidth: true
                            icon: modelData.icon
                            text: (i18n.language, i18n.tr(modelData.key))
                            active: win.page === index
                            onClicked: win.page = index
                        }
                    }
                    Item { Layout.fillHeight: true }
                }
            }

            // ---- 页面栈 ----
            StackLayout {
                Layout.fillWidth: true
                Layout.fillHeight: true
                currentIndex: win.page

                ChatPage {
                    onRequestNavigate: function(page) { win.page = page }
                }
                FilesPage {}
                KnowledgePage {}
                SettingsPage {
                    onModelsSaved: chatBridge.reloadModels()
                }
            }
        }

        // ---- 状态栏 ----
        GlassPanel {
            Layout.fillWidth: true
            Layout.preferredHeight: Theme.statusBarHeight + Theme.spaceS
            Layout.topMargin: Theme.spaceS
            radius: Theme.radiusM
            specularOpacity: 0.15

            Text {
                anchors.left: parent.left
                anchors.leftMargin: Theme.spaceM
                anchors.right: parent.right
                anchors.rightMargin: Theme.spaceM
                anchors.verticalCenter: parent.verticalCenter
                text: statusText.text
                color: Theme.textMuted
                font.pixelSize: Theme.fontXS
                elide: Text.ElideRight
            }
        }
    }

    // 状态栏文本（默认就绪）
    Text {
        id: statusText
        visible: false
        text: (i18n.language, i18n.tr("status.ready"))
    }

    // ---------------------------------------------------------- Toast
    GlassToast {
        id: toast
        anchors.horizontalCenter: parent.horizontalCenter
        y: Theme.titleBarHeight + Theme.windowMargin + Theme.spaceS
        z: 1000
    }

    // ---------------------------------------------------------- 启动错误提示
    GlassDialog { id: startupDlg }

    Component.onCompleted: {
        if (typeof startupErrors !== "undefined" && startupErrors.length > 0) {
            startupDlg.singleButton = true
            startupDlg.openCustom((i18n.language, i18n.tr("common.warning")))
            startupDlg.message = (i18n.language, i18n.tr("app.startupWarning"))
                                 + "\n\n" + startupErrors.join("\n")
        }
    }

    // ---------------------------------------------------------- 桥接消息
    Connections {
        target: chatBridge
        function onInfoMessage(msg) { toast.show(msg, false) }
        function onStatusMessage(msg) { statusText.text = msg }
    }
    Connections {
        target: filesBridge
        function onInfoMessage(msg) { toast.show(msg, false) }
        function onErrorMessage(msg) { toast.show(msg, true) }
        function onStatusMessage(msg) { statusText.text = msg }
    }
    Connections {
        target: knowledgeBridge
        function onInfoMessage(msg) { toast.show(msg, false) }
        function onErrorMessage(msg) { toast.show(msg, true) }
        function onStatusMessage(msg) { statusText.text = msg }
    }
    Connections {
        target: settingsBridge
        function onInfoMessage(msg) { toast.show(msg, false) }
        function onErrorMessage(msg) { toast.show(msg, true) }
        function onStatusMessage(msg) { statusText.text = msg }
    }

    // ---------------------------------------------------------- 边缘缩放
    // 无边框窗口的系统级缩放（Windows Snap 兼容）
    component ResizeEdge: MouseArea {
        property int edge: 0
        hoverEnabled: true
        onPressed: function(mouse) {
            if (mouse.button === Qt.LeftButton) win.startSystemResize(edge)
        }
    }

    Item {
        anchors.fill: parent
        z: 999
        enabled: !win.maximized
        visible: !win.maximized

        readonly property int grip: 6

        ResizeEdge { edge: Qt.LeftEdge;  anchors.left: parent.left;  width: parent.grip; anchors.top: parent.top; anchors.bottom: parent.bottom; cursorShape: Qt.SizeHorCursor }
        ResizeEdge { edge: Qt.RightEdge; anchors.right: parent.right; width: parent.grip; anchors.top: parent.top; anchors.bottom: parent.bottom; cursorShape: Qt.SizeHorCursor }
        ResizeEdge { edge: Qt.TopEdge;   anchors.top: parent.top;    height: parent.grip; anchors.left: parent.left; anchors.right: parent.right; cursorShape: Qt.SizeVerCursor }
        ResizeEdge { edge: Qt.BottomEdge; anchors.bottom: parent.bottom; height: parent.grip; anchors.left: parent.left; anchors.right: parent.right; cursorShape: Qt.SizeVerCursor }
        ResizeEdge { edge: Qt.TopEdge | Qt.LeftEdge;     x: 0; y: 0; width: parent.grip * 2; height: parent.grip * 2; cursorShape: Qt.SizeFDiagCursor }
        ResizeEdge { edge: Qt.TopEdge | Qt.RightEdge;    x: parent.width - width; y: 0; width: parent.grip * 2; height: parent.grip * 2; cursorShape: Qt.SizeBDiagCursor }
        ResizeEdge { edge: Qt.BottomEdge | Qt.LeftEdge;  x: 0; y: parent.height - height; width: parent.grip * 2; height: parent.grip * 2; cursorShape: Qt.SizeBDiagCursor }
        ResizeEdge { edge: Qt.BottomEdge | Qt.RightEdge; x: parent.width - width; y: parent.height - height; width: parent.grip * 2; height: parent.grip * 2; cursorShape: Qt.SizeFDiagCursor }
    }
}
