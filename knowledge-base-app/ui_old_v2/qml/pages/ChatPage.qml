// ChatPage — 对话页
//
// 左：会话列表玻璃栏（新建 / 选择 / ⋯ 对话设置）
// 右：顶栏（模型选择 + 思考模式）、消息流、底部发光输入栏
// 空状态：标题 + 玻璃快捷提问按钮
import QtQuick
import QtQuick.Layouts
import "../theme"
import "../components"

Item {
    id: root

    signal requestNavigate(int page)

    // ---------------------------------------------------------- 消息模型
    ListModel { id: msgModel }

    function scrollToEnd() {
        msgView.positionViewAtEnd()
    }

    // ---------------------------------------------------------- 桥接信号
    Connections {
        target: chatBridge

        function onMessagesCleared() { msgModel.clear() }
        function onHistoryMessageAppended(role, content) {
            msgModel.append({ "role": role, "body": content, "reasoning": "",
                              "refs": [], "steps": [], "streaming": false, "isError": false })
        }
        function onUserMessageAppended(text) {
            msgModel.append({ "role": "user", "body": text, "reasoning": "",
                              "refs": [], "steps": [], "streaming": false, "isError": false })
            root.scrollToEnd()
        }
        function onAssistantMessageStarted() {
            msgModel.append({ "role": "assistant", "body": "", "reasoning": "",
                              "refs": [], "steps": [], "streaming": true, "isError": false })
            root.scrollToEnd()
        }
        function onReasoningChunk(t) {
            if (msgModel.count === 0) return
            var i = msgModel.count - 1
            msgModel.setProperty(i, "reasoning", msgModel.get(i).reasoning + t)
            root.scrollToEnd()
        }
        function onAnswerChunk(t) {
            if (msgModel.count === 0) return
            var i = msgModel.count - 1
            msgModel.setProperty(i, "body", msgModel.get(i).body + t)
            root.scrollToEnd()
        }
        function onReferencesAppended(refs) {
            if (msgModel.count === 0) return
            msgModel.setProperty(msgModel.count - 1, "refs", refs)
        }
        function onStepsUpdated(steps) {
            if (msgModel.count === 0) return
            msgModel.setProperty(msgModel.count - 1, "steps", steps)
        }
        function onStreamFinished() {
            if (msgModel.count === 0) return
            msgModel.setProperty(msgModel.count - 1, "streaming", false)
        }
        function onAssistantError(msg) {
            if (msgModel.count > 0 && msgModel.get(msgModel.count - 1).role === "assistant") {
                var i = msgModel.count - 1
                msgModel.setProperty(i, "body", msg)
                msgModel.setProperty(i, "streaming", false)
                msgModel.setProperty(i, "isError", true)
            } else {
                msgModel.append({ "role": "assistant", "body": msg, "reasoning": "",
                                  "refs": [], "steps": [], "streaming": false, "isError": true })
            }
        }
        function onCurrentModelChanged() { root.syncModelCombo() }
        function onModelsChanged() { root.syncModelCombo() }
    }

    function syncModelCombo() {
        var models = chatBridge.models
        for (var i = 0; i < models.length; i++) {
            if (models[i].displayName === chatBridge.currentModelName) {
                modelCombo.currentIndex = i
                return
            }
        }
        modelCombo.currentIndex = -1
    }

    // ---------------------------------------------------------- 布局
    RowLayout {
        anchors.fill: parent
        spacing: Theme.spaceM

        // ---- 会话列表栏 ----
        GlassPanel {
            Layout.preferredWidth: 248
            Layout.fillHeight: true
            radius: Theme.radiusXL

            ColumnLayout {
                anchors.fill: parent
                anchors.margins: Theme.spaceM
                spacing: Theme.spaceS

                GlassButton {
                    Layout.fillWidth: true
                    text: "＋  " + (i18n.language, i18n.tr("chat.newConversation"))
                    onClicked: chatBridge.newConversation()
                }

                ListView {
                    id: convList
                    Layout.fillWidth: true
                    Layout.fillHeight: true
                    clip: true
                    spacing: Theme.spaceXS
                    model: chatBridge.conversations

                    delegate: Item {
                        id: convItem
                        width: convList.width
                        height: 42
                        readonly property bool isActive: modelData.convId === chatBridge.currentConvId

                        GlassPanel {
                            anchors.fill: parent
                            radius: Theme.radiusM
                            specularOpacity: 0.25
                            shadow: false
                            sheen: false
                            edgeLight: false
                            opacity: convItem.isActive || convMouse.containsMouse ? 1 : 0
                            fillTop: convItem.isActive ? Theme.accentSoft : Qt.alpha("#FFFFFF", 0.10)
                            fillBottom: "transparent"
                            borderTop: convItem.isActive ? Qt.alpha(Theme.accent, 0.5)
                                                         : Theme.glassBorderTop
                            Behavior on opacity { NumberAnimation { duration: Theme.animFast } }
                        }
                        Text {
                            anchors.left: parent.left
                            anchors.leftMargin: Theme.spaceM
                            anchors.right: moreBtn.left
                            anchors.rightMargin: Theme.spaceXS
                            anchors.verticalCenter: parent.verticalCenter
                            text: modelData.title
                            color: convItem.isActive ? Theme.textPrimary : Theme.textSecondary
                            font.pixelSize: Theme.fontM
                            elide: Text.ElideRight
                        }
                        GlassIconButton {
                            id: moreBtn
                            anchors.right: parent.right
                            anchors.rightMargin: Theme.spaceXS
                            anchors.verticalCenter: parent.verticalCenter
                            glyph: "⋯"
                            size: 26
                            visible: convItem.isActive || convMouse.containsMouse
                            onClicked: root.openConvSettings(modelData.convId)
                        }
                        MouseArea {
                            id: convMouse
                            anchors.fill: parent
                            anchors.rightMargin: moreBtn.width + Theme.spaceS
                            hoverEnabled: true
                            cursorShape: Qt.PointingHandCursor
                            onClicked: chatBridge.selectConversation(modelData.convId)
                        }
                    }
                }
            }
        }

        // ---- 对话主区 ----
        ColumnLayout {
            Layout.fillWidth: true
            Layout.fillHeight: true
            spacing: Theme.spaceS

            // 顶栏：模型 + 思考模式
            RowLayout {
                Layout.fillWidth: true
                spacing: Theme.spaceM

                GlassComboBox {
                    id: modelCombo
                    Layout.preferredWidth: 300
                    model: chatBridge.models
                    placeholder: (i18n.language, i18n.tr("chat.noModel"))
                    enabled: chatBridge.hasConfiguredModel && !chatBridge.generating
                    onActivated: function(index, item) {
                        chatBridge.selectModel(item.providerKey, item.modelName, item.displayName)
                    }
                }

                Item { Layout.fillWidth: true }

                Text {
                    text: (i18n.language, i18n.tr("chat.thinkingMode"))
                    color: Theme.textSecondary
                    font.pixelSize: Theme.fontM
                }
                GlassSwitch {
                    checked: chatBridge.thinking
                    onToggled: function(checked) { chatBridge.thinking = checked }
                }
            }

            // 消息流
            GlassPanel {
                Layout.fillWidth: true
                Layout.fillHeight: true
                radius: Theme.radiusXL
                specularOpacity: 0.25

                ListView {
                    id: msgView
                    anchors.fill: parent
                    anchors.margins: Theme.spaceL
                    anchors.rightMargin: Theme.spaceS
                    clip: true
                    spacing: Theme.spaceL
                    model: msgModel
                    boundsBehavior: Flickable.StopAtBounds

                    delegate: MessageBubble {
                        width: msgView.width - Theme.spaceL
                        maxBubbleWidth: (msgView.width - Theme.spaceL) * 0.74
                        height: implicitHeight
                        role: model.role
                        text: model.body
                        reasoning: model.reasoning
                        refs: model.refs
                        steps: model.steps
                        streaming: model.streaming
                        isError: model.isError
                    }

                    add: Transition {
                        NumberAnimation { property: "opacity"; from: 0; to: 1
                                          duration: Theme.animMed }
                    }
                }

                // 空状态
                Column {
                    visible: msgModel.count === 0
                    anchors.centerIn: parent
                    spacing: Theme.spaceL
                    width: parent.width - Theme.spaceXXL * 2

                    Text {
                        anchors.horizontalCenter: parent.horizontalCenter
                        text: (i18n.language, i18n.tr("chat.empty.title"))
                        color: Theme.textPrimary
                        font.pixelSize: Theme.fontTitle
                        font.bold: true
                    }
                    Text {
                        anchors.horizontalCenter: parent.horizontalCenter
                        text: (i18n.language, i18n.tr("chat.empty.subtitle"))
                        color: Theme.textSecondary
                        font.pixelSize: Theme.fontM
                    }

                    // 未配置模型提示
                    Row {
                        visible: !chatBridge.hasConfiguredModel
                        anchors.horizontalCenter: parent.horizontalCenter
                        spacing: Theme.spaceM
                        Text {
                            anchors.verticalCenter: parent.verticalCenter
                            text: (i18n.language, i18n.tr("chat.noModelHint"))
                            color: Theme.warning
                            font.pixelSize: Theme.fontS
                            wrapMode: Text.Wrap
                            width: 320
                        }
                        GlassButton {
                            variant: "ghost"
                            text: (i18n.language, i18n.tr("nav.settings"))
                            onClicked: root.requestNavigate(3)
                        }
                    }

                    // 玻璃快捷提问
                    Row {
                        anchors.horizontalCenter: parent.horizontalCenter
                        spacing: Theme.spaceM
                        visible: chatBridge.hasConfiguredModel
                        Repeater {
                            model: ["chat.quickReply.1", "chat.quickReply.2", "chat.quickReply.3"]
                            GlassButton {
                                variant: "ghost"
                                text: (i18n.language, i18n.tr(modelData))
                                onClicked: chatBridge.send(text)
                            }
                        }
                    }
                }
            }

            // 输入栏（底部玻璃栏，聚焦发光）
            GlassPanel {
                Layout.fillWidth: true
                Layout.preferredHeight: Math.min(132, Math.max(52, inputEdit.contentHeight + 30))
                radius: Theme.radiusXL
                specularOpacity: 0.4
                glow: inputEdit.activeFocus
                glowColor: Theme.accent

                RowLayout {
                    anchors.fill: parent
                    anchors.margins: Theme.spaceM
                    spacing: Theme.spaceM

                    Flickable {
                        Layout.fillWidth: true
                        Layout.fillHeight: true
                        clip: true
                        contentWidth: width
                        contentHeight: inputEdit.contentHeight

                        TextEdit {
                            id: inputEdit
                            width: parent.width
                            wrapMode: TextEdit.Wrap
                            color: Theme.textPrimary
                            font.pixelSize: Theme.fontM
                            selectByMouse: true
                            selectedTextColor: Theme.textPrimary
                            selectionColor: Qt.alpha(Theme.accent, 0.45)
                            enabled: !chatBridge.generating || true

                            Text {
                                visible: inputEdit.text === "" && !inputEdit.activeFocus
                                text: (i18n.language, i18n.tr("chat.placeholder"))
                                color: Theme.textMuted
                                font.pixelSize: Theme.fontM
                            }

                            Keys.onPressed: function(event) {
                                if (event.key === Qt.Key_Return || event.key === Qt.Key_Enter) {
                                    if (event.modifiers & Qt.ShiftModifier) {
                                        inputEdit.insert(inputEdit.cursorPosition, "\n")
                                    } else if (!chatBridge.generating) {
                                        var t = inputEdit.text.trim()
                                        if (t !== "") {
                                            chatBridge.send(t)
                                            inputEdit.clear()
                                        }
                                    }
                                    event.accepted = true
                                }
                            }
                        }
                        onContentHeightChanged: {
                            if (contentHeight > height)
                                contentY = contentHeight - height
                        }
                    }

                    GlassButton {
                        Layout.alignment: Qt.AlignBottom
                        variant: chatBridge.generating ? "danger" : "primary"
                        text: chatBridge.generating
                              ? (i18n.language, i18n.tr("chat.stop"))
                              : (i18n.language, i18n.tr("chat.send"))
                        onClicked: {
                            if (chatBridge.generating) {
                                chatBridge.stop()
                            } else {
                                var t = inputEdit.text.trim()
                                if (t !== "") {
                                    chatBridge.send(t)
                                    inputEdit.clear()
                                }
                            }
                        }
                    }
                }
            }
        }
    }

    // ---------------------------------------------------------- 对话设置
    property int _editingConvId: -1
    property bool _editingAutoName: false

    function openConvSettings(convId) {
        var info = chatBridge.getConversationInfo(convId)
        if (!info || info.convId === undefined) return
        root._editingConvId = convId
        root._editingAutoName = info.autoName
        renameInput.text = info.title || ""
        convDlg.openCustom((i18n.language, i18n.tr("chat.convSettings")))
    }

    GlassDialog {
        id: convDlg
        dialogWidth: 480
        hideButtons: true
        singleButton: false

        Column {
            width: convDlg.dialogWidth - Theme.spaceL * 2
            spacing: Theme.spaceM

            RowLayout {
                width: parent.width
                spacing: Theme.spaceM
                Column {
                    Layout.fillWidth: true
                    spacing: 2
                    Text {
                        text: (i18n.language, i18n.tr("chat.autoName"))
                        color: Theme.textPrimary
                        font.pixelSize: Theme.fontM
                    }
                    Text {
                        text: (i18n.language, i18n.tr("chat.autoNameTip"))
                        color: Theme.textMuted
                        font.pixelSize: Theme.fontXS
                        wrapMode: Text.Wrap
                        width: parent.width
                    }
                }
                GlassSwitch {
                    checked: root._editingAutoName
                    onToggled: function(checked) {
                        root._editingAutoName = checked
                        chatBridge.setAutoName(root._editingConvId, checked)
                    }
                }
            }

            RowLayout {
                width: parent.width
                spacing: Theme.spaceS
                GlassInput {
                    id: renameInput
                    Layout.fillWidth: true
                    placeholder: (i18n.language, i18n.tr("chat.manualNamePlaceholder"))
                    onAccepted: {
                        chatBridge.renameConversation(root._editingConvId, text)
                        convDlg.close()
                    }
                }
                GlassButton {
                    variant: "ghost"
                    text: (i18n.language, i18n.tr("chat.nameIt"))
                    onClicked: {
                        chatBridge.renameConversation(root._editingConvId, renameInput.text)
                        convDlg.close()
                    }
                }
            }

            RowLayout {
                width: parent.width
                spacing: Theme.spaceS
                GlassButton {
                    Layout.fillWidth: true
                    variant: "ghost"
                    text: (i18n.language, i18n.tr("chat.reAutoName"))
                    onClicked: {
                        chatBridge.reAutoName(root._editingConvId)
                        convDlg.close()
                    }
                }
                GlassButton {
                    variant: "danger"
                    text: (i18n.language, i18n.tr("common.delete"))
                    onClicked: {
                        convDlg.close()
                        delConvDlg.openConfirm(
                            (i18n.language, i18n.tr("common.delete")),
                            (i18n.language, i18n.tr("chat.deleteConfirm")),
                            function() { chatBridge.deleteConversation(root._editingConvId) },
                            true)
                    }
                }
            }
        }
    }

    GlassDialog { id: delConvDlg }
}
