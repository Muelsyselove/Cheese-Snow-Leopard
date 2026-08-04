// GlassComboBox — 玻璃下拉选择框
//
// model: [{label: "...", ...}] 或字符串数组；currentIndex 绑定当前项。
// 下拉弹出层为玻璃列表，选中发出 activated(index, item)。
import QtQuick
import QtQuick.Controls as QC
import "../theme"

Item {
    id: root

    property var model: []
    property int currentIndex: -1
    property string placeholder: ""
    property string displayRole: "label"
    signal activated(int index, var item)

    implicitWidth: 160
    implicitHeight: Theme.inputHeight
    enabled: true
    opacity: enabled ? 1.0 : 0.45

    function itemLabel(item) {
        if (item === undefined || item === null) return ""
        if (typeof item === "string") return item
        return item[root.displayRole] !== undefined ? item[root.displayRole] : ""
    }

    readonly property string currentText:
        currentIndex >= 0 && currentIndex < model.length
        ? itemLabel(model[currentIndex]) : placeholder

    GlassPanel {
        anchors.fill: parent
        radius: Theme.radiusM
        specularOpacity: 0.4
        glow: popup.visible
        fillTop: mouse.containsMouse ? Qt.alpha("#FFFFFF", 0.16) : Theme.glassFillTop
        fillBottom: Theme.glassFillBottom

        Text {
            anchors.left: parent.left
            anchors.leftMargin: Theme.spaceM
            anchors.right: arrow.left
            anchors.rightMargin: Theme.spaceS
            anchors.verticalCenter: parent.verticalCenter
            text: root.currentText
            color: root.currentIndex >= 0 ? Theme.textPrimary : Theme.textMuted
            font.pixelSize: Theme.fontM
            elide: Text.ElideRight
        }
        Text {
            id: arrow
            anchors.right: parent.right
            anchors.rightMargin: Theme.spaceM
            anchors.verticalCenter: parent.verticalCenter
            text: "▾"
            color: Theme.textSecondary
            font.pixelSize: Theme.fontS
            rotation: popup.visible ? 180 : 0
            Behavior on rotation { NumberAnimation { duration: Theme.animFast } }
        }
    }

    MouseArea {
        id: mouse
        anchors.fill: parent
        hoverEnabled: true
        cursorShape: root.enabled ? Qt.PointingHandCursor : Qt.ArrowCursor
        onClicked: if (root.enabled) popup.open()
    }

    QC.Popup {
        id: popup
        y: root.height + Theme.spaceXS
        width: Math.max(root.width, 140)
        height: Math.min(list.contentHeight + Theme.spaceS * 2, 280)
        padding: Theme.spaceS
        modal: true
        focus: true
        closePolicy: QC.Popup.CloseOnEscape | QC.Popup.CloseOnPressOutside

        background: GlassPanel {
            radius: Theme.radiusM
            specularOpacity: 0.35
            fillTop: Qt.alpha("#1B2242", 0.92)
            fillBottom: Qt.alpha("#12172E", 0.92)
        }

        contentItem: ListView {
            id: list
            clip: true
            model: root.model
            implicitHeight: contentHeight
            delegate: Item {
                width: list.width
                height: Theme.inputHeight

                GlassPanel {
                    anchors.fill: parent
                    anchors.margins: 1
                    radius: Theme.radiusS
                    specularOpacity: 0.25
                    opacity: (index === root.currentIndex || itemMouse.containsMouse) ? 1 : 0
                    fillTop: index === root.currentIndex ? Theme.accentSoft : Qt.alpha("#FFFFFF", 0.12)
                    fillBottom: "transparent"
                    borderTop: index === root.currentIndex ? Qt.alpha(Theme.accent, 0.5)
                                                           : Theme.glassBorderTop
                    Behavior on opacity { NumberAnimation { duration: Theme.animFast } }
                }
                Text {
                    anchors.left: parent.left
                    anchors.leftMargin: Theme.spaceM
                    anchors.right: parent.right
                    anchors.rightMargin: Theme.spaceS
                    anchors.verticalCenter: parent.verticalCenter
                    text: root.itemLabel(modelData)
                    color: index === root.currentIndex ? Theme.accent : Theme.textPrimary
                    font.pixelSize: Theme.fontM
                    elide: Text.ElideRight
                }
                MouseArea {
                    id: itemMouse
                    anchors.fill: parent
                    hoverEnabled: true
                    cursorShape: Qt.PointingHandCursor
                    onClicked: {
                        popup.close()
                        root.activated(index, modelData)
                    }
                }
            }
        }
    }
}
