// GlassDialog — 玻璃模态对话框
//
// 基本用法（确认框）：
//   dlg.openConfirm("标题", "内容", function() { ... })
// 自定义内容：设置 dialogWidth/dialogHeight 并向默认属性塞入内容，
//   再调用 openCustom("标题")；按钮区可通过 hideButtons 关闭。
import QtQuick
import QtQuick.Controls as QC
import "../theme"

QC.Popup {
    id: root

    property string title: ""
    property string message: ""
    property string confirmText: ""
    property string cancelText: ""
    property bool dangerConfirm: false
    property bool hideButtons: false
    property bool singleButton: false       // true 时仅显示确认按钮
    property int dialogWidth: 460
    property int dialogHeight: -1            // -1 = 按内容自适应

    property var _onAccept: null

    default property alias customContent: customHost.data

    function openConfirm(title, message, onAccept, danger) {
        root.title = title
        root.message = message
        root.dangerConfirm = danger === true
        root.hideButtons = false
        root._onAccept = onAccept || null
        root.open()
    }

    function openCustom(title) {
        root.title = title
        root.message = ""
        root._onAccept = null
        root.open()
    }

    anchors.centerIn: parent
    width: dialogWidth
    height: dialogHeight > 0 ? dialogHeight : contentCol.implicitHeight + padding * 2
    padding: Theme.spaceL
    modal: true
    focus: true
    closePolicy: QC.Popup.CloseOnEscape

    enter: Transition {
        NumberAnimation { property: "opacity"; from: 0; to: 1; duration: Theme.animMed }
        NumberAnimation { property: "scale"; from: 0.92; to: 1; duration: Theme.animMed
                          easing.type: Easing.OutBack }
    }
    exit: Transition {
        NumberAnimation { property: "opacity"; from: 1; to: 0; duration: Theme.animFast }
    }

    background: GlassPanel {
        radius: Theme.radiusL
        specularOpacity: 0.5
        fillTop: Qt.alpha("#1D2447", 0.94)
        fillBottom: Qt.alpha("#12172E", 0.94)
        borderTop: Theme.glassBorderTop
    }

    contentItem: Column {
        id: contentCol
        spacing: Theme.spaceM

        Text {
            visible: root.title !== ""
            text: root.title
            color: Theme.textPrimary
            font.pixelSize: Theme.fontL
            font.bold: true
            width: parent.width
            wrapMode: Text.Wrap
        }

        Text {
            visible: root.message !== ""
            text: root.message
            color: Theme.textSecondary
            font.pixelSize: Theme.fontM
            width: parent.width
            wrapMode: Text.Wrap
            lineHeight: 1.35
        }

        Item {
            id: customHost
            visible: children.length > 0
            width: parent.width
            height: childrenRect.height
        }

        Row {
            visible: !root.hideButtons
            anchors.right: parent.right
            spacing: Theme.spaceM

            GlassButton {
                visible: !root.singleButton
                variant: "ghost"
                text: root.cancelText !== "" ? root.cancelText
                                             : (i18n.language, i18n.tr("common.cancel"))
                onClicked: root.close()
            }
            GlassButton {
                variant: root.dangerConfirm ? "danger" : "primary"
                text: root.confirmText !== "" ? root.confirmText
                                              : (i18n.language, i18n.tr("common.confirm"))
                onClicked: {
                    root.close()
                    if (root._onAccept) root._onAccept()
                }
            }
        }
    }
}
