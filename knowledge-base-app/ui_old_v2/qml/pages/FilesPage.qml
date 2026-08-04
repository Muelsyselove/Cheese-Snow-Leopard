// FilesPage — 文件页
//
// 顶栏（标题 + 刷新 + 导入）→ 导入进度条 → 文档玻璃列表
// 每行：文件名 / 状态徽标 / 页数 / 删除按钮（确认对话框）
import QtQuick
import QtQuick.Layouts
import "../theme"
import "../components"

Item {
    id: root

    // 导入进度（0..1，-1 = 空闲）
    property real importValue: -1
    property string importText: ""

    Connections {
        target: filesBridge
        function onImportProgress(percent, msg) {
            root.importValue = percent / 100.0
            root.importText = msg + " (" + percent + "%)"
        }
        function onImportRunningChanged() {
            if (!filesBridge.importRunning) root.importValue = -1
        }
    }

    function statusTone(status) {
        if (status === "completed") return "success"
        if (status === "failed") return "danger"
        if (status === "deleting") return "warning"
        return "info"
    }

    ColumnLayout {
        anchors.fill: parent
        spacing: Theme.spaceM

        // ---- 顶栏 ----
        RowLayout {
            Layout.fillWidth: true
            spacing: Theme.spaceM

            Text {
                text: (i18n.language, i18n.tr("files.title"))
                color: Theme.textPrimary
                font.pixelSize: Theme.fontXL
                font.bold: true
            }
            Item { Layout.fillWidth: true }
            GlassIconButton {
                glyph: "⟳"
                tip: (i18n.language, i18n.tr("common.refresh"))
                size: Theme.inputHeight
                onClicked: filesBridge.refresh()
            }
            GlassButton {
                text: "＋  " + (i18n.language, i18n.tr("files.import"))
                enabled: !filesBridge.importRunning
                onClicked: filesBridge.importFiles()
            }
        }

        // ---- 导入进度 ----
        GlassProgressBar {
            Layout.fillWidth: true
            visible: filesBridge.importRunning
            value: root.importValue >= 0 ? root.importValue : 0
            indeterminate: root.importValue < 0
            text: root.importText
        }

        // ---- 文档列表 ----
        GlassPanel {
            Layout.fillWidth: true
            Layout.fillHeight: true
            radius: Theme.radiusXL
            specularOpacity: 0.25

            ListView {
                id: docView
                anchors.fill: parent
                anchors.margins: Theme.spaceM
                clip: true
                spacing: Theme.spaceS
                model: filesBridge.documents
                boundsBehavior: Flickable.StopAtBounds

                delegate: Item {
                    id: docItem
                    width: docView.width
                    height: 52

                    GlassPanel {
                        anchors.fill: parent
                        radius: Theme.radiusM
                        specularOpacity: 0.3
                        opacity: rowMouse.containsMouse ? 1 : 0.6
                        fillTop: Qt.alpha("#FFFFFF", rowMouse.containsMouse ? 0.13 : 0.08)
                        fillBottom: Qt.alpha("#FFFFFF", 0.03)
                        Behavior on opacity { NumberAnimation { duration: Theme.animFast } }
                    }

                    RowLayout {
                        anchors.fill: parent
                        anchors.leftMargin: Theme.spaceL
                        anchors.rightMargin: Theme.spaceM
                        spacing: Theme.spaceM

                        Text {
                            Layout.fillWidth: true
                            text: modelData.fileName
                            color: Theme.textPrimary
                            font.pixelSize: Theme.fontM
                            elide: Text.ElideMiddle
                        }
                        GlassBadge {
                            text: (i18n.language, i18n.tr(modelData.statusKey))
                            tone: root.statusTone(modelData.status)
                        }
                        Text {
                            visible: modelData.pageCount !== ""
                            text: modelData.pageCount
                            color: Theme.textMuted
                            font.pixelSize: Theme.fontS
                        }
                        GlassIconButton {
                            glyph: "🗑"
                            danger: true
                            size: 30
                            tip: (i18n.language, i18n.tr("files.delete"))
                            onClicked: delDlg.openConfirm(
                                (i18n.language, i18n.tr("files.delete")),
                                (i18n.language, i18n.trf("files.deleteConfirm",
                                                         { "name": modelData.fileName })),
                                function() { filesBridge.deleteDocument(modelData.docId) },
                                true)
                        }
                    }

                    MouseArea {
                        id: rowMouse
                        anchors.fill: parent
                        anchors.rightMargin: 44
                        hoverEnabled: true
                        acceptedButtons: Qt.NoButton
                    }
                }
            }

            // 空状态
            Column {
                visible: docView.count === 0
                anchors.centerIn: parent
                spacing: Theme.spaceM
                Text {
                    anchors.horizontalCenter: parent.horizontalCenter
                    text: (i18n.language, i18n.tr("files.empty"))
                    color: Theme.textMuted
                    font.pixelSize: Theme.fontM
                }
                GlassButton {
                    anchors.horizontalCenter: parent.horizontalCenter
                    variant: "ghost"
                    text: "＋  " + (i18n.language, i18n.tr("files.import"))
                    onClicked: filesBridge.importFiles()
                }
            }
        }
    }

    GlassDialog { id: delDlg }
}
