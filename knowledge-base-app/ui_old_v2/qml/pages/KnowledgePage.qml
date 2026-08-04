// KnowledgePage — 知识库页
//
// 上：知识分类玻璃列表（分类名 + 知识块数）
// 下：向量库维护区（重建按钮 + 进度条）
import QtQuick
import QtQuick.Layouts
import "../theme"
import "../components"

Item {
    id: root

    property real rebuildValue: -1
    property string rebuildText: ""

    Connections {
        target: knowledgeBridge
        function onRebuildProgress(percent, msg) {
            root.rebuildValue = percent / 100.0
            root.rebuildText = msg + " (" + percent + "%)"
        }
        function onRebuildingChanged() {
            if (!knowledgeBridge.rebuilding) root.rebuildValue = -1
        }
        function onRebuildFinishedOk(success) {
            resultDlg.singleButton = true
            resultDlg.dangerConfirm = !success
            resultDlg.openCustom(success
                ? (i18n.language, i18n.tr("common.success"))
                : (i18n.language, i18n.tr("common.failed")))
            resultDlg.message = success
                ? (i18n.language, i18n.tr("knowledge.rebuildDone"))
                : (i18n.language, i18n.tr("knowledge.rebuildFailed"))
        }
    }

    ColumnLayout {
        anchors.fill: parent
        spacing: Theme.spaceM

        // ---- 顶栏 ----
        RowLayout {
            Layout.fillWidth: true
            spacing: Theme.spaceM
            Text {
                text: (i18n.language, i18n.tr("knowledge.title"))
                color: Theme.textPrimary
                font.pixelSize: Theme.fontXL
                font.bold: true
            }
            Item { Layout.fillWidth: true }
            GlassIconButton {
                glyph: "⟳"
                tip: (i18n.language, i18n.tr("common.refresh"))
                size: Theme.inputHeight
                onClicked: knowledgeBridge.refresh()
            }
        }

        // ---- 分类列表 ----
        GlassPanel {
            Layout.fillWidth: true
            Layout.fillHeight: true
            radius: Theme.radiusXL
            specularOpacity: 0.25

            ColumnLayout {
                anchors.fill: parent
                anchors.margins: Theme.spaceL
                spacing: Theme.spaceS

                Text {
                    text: (i18n.language, i18n.tr("knowledge.categories"))
                    color: Theme.textSecondary
                    font.pixelSize: Theme.fontM
                    font.bold: true
                }

                ListView {
                    id: catView
                    Layout.fillWidth: true
                    Layout.fillHeight: true
                    clip: true
                    spacing: Theme.spaceS
                    model: knowledgeBridge.categories
                    boundsBehavior: Flickable.StopAtBounds

                    delegate: Item {
                        width: catView.width
                        height: 46

                        GlassPanel {
                            anchors.fill: parent
                            radius: Theme.radiusM
                            specularOpacity: 0.3
                            opacity: catMouse.containsMouse ? 1 : 0.55
                            fillTop: Qt.alpha("#FFFFFF", catMouse.containsMouse ? 0.13 : 0.07)
                            fillBottom: Qt.alpha("#FFFFFF", 0.03)
                            Behavior on opacity { NumberAnimation { duration: Theme.animFast } }
                        }
                        RowLayout {
                            anchors.fill: parent
                            anchors.leftMargin: Theme.spaceL
                            anchors.rightMargin: Theme.spaceL
                            spacing: Theme.spaceM
                            Text {
                                Layout.fillWidth: true
                                text: modelData.name
                                color: Theme.textPrimary
                                font.pixelSize: Theme.fontM
                                elide: Text.ElideRight
                            }
                            GlassBadge {
                                text: modelData.chunkCount
                                tone: "info"
                            }
                        }
                        MouseArea {
                            id: catMouse
                            anchors.fill: parent
                            hoverEnabled: true
                            acceptedButtons: Qt.NoButton
                        }
                    }
                }

                Text {
                    visible: catView.count === 0
                    Layout.alignment: Qt.AlignHCenter
                    text: (i18n.language, i18n.tr("knowledge.empty"))
                    color: Theme.textMuted
                    font.pixelSize: Theme.fontM
                }
            }
        }

        // ---- 向量库维护 ----
        GlassPanel {
            Layout.fillWidth: true
            Layout.preferredHeight: maintCol.implicitHeight + Theme.spaceL * 2
            radius: Theme.radiusXL
            specularOpacity: 0.3

            ColumnLayout {
                id: maintCol
                anchors.left: parent.left
                anchors.right: parent.right
                anchors.top: parent.top
                anchors.margins: Theme.spaceL
                spacing: Theme.spaceS

                Text {
                    text: (i18n.language, i18n.tr("knowledge.maintenance"))
                    color: Theme.textSecondary
                    font.pixelSize: Theme.fontM
                    font.bold: true
                }
                Text {
                    Layout.fillWidth: true
                    text: (i18n.language, i18n.tr("knowledge.maintenanceHint"))
                    color: Theme.textMuted
                    font.pixelSize: Theme.fontS
                    wrapMode: Text.Wrap
                    lineHeight: 1.3
                }
                RowLayout {
                    Layout.fillWidth: true
                    spacing: Theme.spaceM
                    GlassButton {
                        variant: "danger"
                        enabled: !knowledgeBridge.rebuilding
                        text: (i18n.language, i18n.tr("knowledge.rebuild"))
                        onClicked: rebuildDlg.openConfirm(
                            (i18n.language, i18n.tr("knowledge.rebuild")),
                            (i18n.language, i18n.tr("knowledge.rebuildConfirm")),
                            function() { knowledgeBridge.rebuild() },
                            true)
                    }
                    GlassProgressBar {
                        Layout.fillWidth: true
                        visible: knowledgeBridge.rebuilding
                        value: root.rebuildValue >= 0 ? root.rebuildValue : 0
                        indeterminate: root.rebuildValue < 0
                        text: root.rebuildText
                    }
                }
            }
        }
    }

    GlassDialog { id: rebuildDlg }
    GlassDialog { id: resultDlg }
}
