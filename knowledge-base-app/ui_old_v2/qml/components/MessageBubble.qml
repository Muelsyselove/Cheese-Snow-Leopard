// MessageBubble — 液态玻璃消息气泡
//
// 用户消息：青色调玻璃，靠右；AI 消息：紫色调玻璃，靠左。
// 头像悬浮在气泡上缘外侧（部分重叠玻璃边缘）。
// 支持：流式输出（辉光 + 光标 / 打字指示器）、思考过程折叠、引用来源展开。
import QtQuick
import "../theme"

Item {
    id: root

    property string role: "assistant"          // user | assistant
    property string text: ""
    property string reasoning: ""
    property var refs: []
    property var steps: []                     // 多步时间线 [{kind, status, detail}]
    property bool streaming: false
    property bool isError: false
    property real maxBubbleWidth: 620

    readonly property bool isUser: role === "user"
    readonly property color tone: isUser ? Theme.accent : Theme.accentViolet
    property bool _reasoningOpen: false

    // 自然宽度测量（隐藏文本，避免换行宽度自引用）
    Text {
        id: measureText
        visible: false
        text: root.text
        font.pixelSize: Theme.fontM
    }
    readonly property real bubbleWidth: Math.min(
        root.maxBubbleWidth,
        Math.max(200, measureText.implicitWidth + Theme.spaceL * 2 + 4))

    implicitHeight: contentCol.implicitHeight + Theme.avatarSize * 0.3

    // 头像（悬浮在气泡玻璃层上缘）
    GlassAvatar {
        id: avatar
        role: root.role
        text: root.isUser ? (i18n.language, i18n.tr("chat.you")) : "AI"
        anchors.right: root.isUser ? parent.right : undefined
        anchors.left: root.isUser ? undefined : parent.left
        y: 0
    }

    Column {
        id: contentCol
        spacing: Theme.spaceS
        width: root.bubbleWidth
        anchors.top: parent.top
        anchors.topMargin: Theme.avatarSize * 0.3
        anchors.right: root.isUser ? parent.right : undefined
        anchors.left: root.isUser ? undefined : parent.left
        anchors.rightMargin: root.isUser ? Theme.avatarSize * 0.55 : 0
        anchors.leftMargin: root.isUser ? 0 : Theme.avatarSize * 0.55

        // ---- 步骤时间线（多步输出：思考 / 检索 / 回答） ----
        Column {
            visible: root.steps.length > 0
            width: parent.width
            spacing: 4
            leftPadding: Theme.spaceXS

            Repeater {
                model: root.steps

                Row {
                    spacing: Theme.spaceS
                    height: 18

                    // 状态指示：进行中 = 呼吸圆点；完成 = 对勾
                    Text {
                        visible: modelData.status === "running"
                        anchors.verticalCenter: parent.verticalCenter
                        text: "●"
                        color: root.tone
                        font.pixelSize: Theme.fontXS
                        SequentialAnimation on opacity {
                            running: modelData.status === "running"
                            loops: Animation.Infinite
                            NumberAnimation { to: 0.25; duration: 550; easing.type: Easing.InOutSine }
                            NumberAnimation { to: 1.0; duration: 550; easing.type: Easing.InOutSine }
                        }
                    }
                    Text {
                        visible: modelData.status !== "running"
                        anchors.verticalCenter: parent.verticalCenter
                        text: "✓"
                        color: Theme.success
                        font.pixelSize: Theme.fontXS
                        font.bold: true
                    }

                    // 步骤名
                    Text {
                        anchors.verticalCenter: parent.verticalCenter
                        text: modelData.kind === "thinking"
                              ? (i18n.language, i18n.tr("chat.step.thinking"))
                              : modelData.kind === "search"
                              ? (i18n.language, i18n.tr("chat.step.search"))
                              : (i18n.language, i18n.tr("chat.step.answer"))
                        color: modelData.status === "running"
                               ? Theme.textPrimary : Theme.textMuted
                        font.pixelSize: Theme.fontXS
                    }

                    // 步骤详情：检索中显示查询词，完成显示命中数
                    Text {
                        anchors.verticalCenter: parent.verticalCenter
                        visible: text !== ""
                        width: Math.min(implicitWidth, root.bubbleWidth - 180)
                        elide: Text.ElideRight
                        color: Theme.textMuted
                        font.pixelSize: Theme.fontXS
                        text: modelData.kind === "search"
                              ? (modelData.status === "running"
                                 ? "「" + modelData.detail + "」"
                                 : (i18n.language,
                                    i18n.trf("chat.step.searchFound",
                                             { "count": modelData.detail })))
                              : ""
                    }
                }
            }
        }

        // ---- 思考过程（可折叠） ----
        GlassPanel {
            visible: root.reasoning !== ""
            width: parent.width
            height: reasoningCol.implicitHeight + Theme.spaceS * 2
            radius: Theme.radiusM
            specularOpacity: 0.25
            fillTop: Qt.alpha(Theme.accentViolet, 0.14)
            fillBottom: Qt.alpha(Theme.accentViolet, 0.05)
            borderTop: Qt.alpha(Theme.accentViolet, 0.30)

            Column {
                id: reasoningCol
                x: Theme.spaceM
                y: Theme.spaceS
                width: parent.width - Theme.spaceM * 2
                spacing: Theme.spaceXS

                Item {
                    width: parent.width
                    height: reasoningHeader.implicitHeight
                    Text {
                        id: reasoningHeader
                        text: (root._reasoningOpen ? "▾ " : "▸ ")
                              + (i18n.language, i18n.tr("chat.thinkingProcess"))
                        color: Theme.accentViolet
                        font.pixelSize: Theme.fontS
                    }
                    MouseArea {
                        anchors.fill: parent
                        cursorShape: Qt.PointingHandCursor
                        onClicked: root._reasoningOpen = !root._reasoningOpen
                    }
                }
                Text {
                    visible: root._reasoningOpen
                    text: root.reasoning
                    width: parent.width
                    wrapMode: Text.Wrap
                    color: Theme.textMuted
                    font.pixelSize: Theme.fontS
                    lineHeight: 1.35
                }
            }
        }

        // ---- 主气泡 ----
        GlassPanel {
            width: parent.width
            height: mainContent.implicitHeight + Theme.spaceM * 2
            radius: Theme.radiusL
            specularOpacity: 0.5
            glow: root.streaming
            glowColor: root.tone
            causticColor: root.tone
            fillTop: root.isUser ? Theme.bubbleUserTop : Theme.bubbleAiTop
            fillBottom: root.isUser ? Theme.bubbleUserBottom : Theme.bubbleAiBottom
            borderTop: root.isUser ? Theme.bubbleUserBorder : Theme.bubbleAiBorder
            borderBottom: Qt.alpha(root.tone, 0.18)

            Column {
                id: mainContent
                x: Theme.spaceL
                y: Theme.spaceM
                width: parent.width - Theme.spaceL * 2
                spacing: Theme.spaceS

                TypingIndicator {
                    visible: root.streaming && root.text === ""
                    color: root.tone
                }
                Text {
                    visible: !(root.streaming && root.text === "")
                    text: root.text + (root.streaming ? " ▍" : "")
                    width: parent.width
                    wrapMode: Text.Wrap
                    textFormat: root.isUser ? Text.PlainText : Text.MarkdownText
                    color: root.isError ? Theme.danger : Theme.textPrimary
                    font.pixelSize: Theme.fontM
                    lineHeight: 1.4
                }
            }
        }

        // ---- 引用来源 ----
        GlassPanel {
            visible: root.refs.length > 0
            width: parent.width
            height: refsCol.implicitHeight + Theme.spaceS * 2
            radius: Theme.radiusM
            specularOpacity: 0.2
            fillTop: Qt.alpha("#FFFFFF", 0.08)
            fillBottom: Qt.alpha("#FFFFFF", 0.03)

            Column {
                id: refsCol
                x: Theme.spaceM
                y: Theme.spaceS
                width: parent.width - Theme.spaceM * 2
                spacing: Theme.spaceXS

                Text {
                    text: (i18n.language, i18n.tr("chat.references"))
                    color: Theme.textSecondary
                    font.pixelSize: Theme.fontS
                    font.bold: true
                }
                Repeater {
                    model: root.refs
                    Column {
                        id: refItem
                        property bool open: false
                        width: refsCol.width
                        spacing: 2

                        Item {
                            width: parent.width
                            height: refLine.implicitHeight
                            Text {
                                id: refLine
                                width: parent.width
                                elide: Text.ElideRight
                                color: Theme.accent
                                font.pixelSize: Theme.fontXS
                                text: "[" + (modelData.chunk_id || "") + "] "
                                      + (modelData.source_file || "") + " · "
                                      + (i18n.language, i18n.trf("chat.page", { "page": modelData.page || "?" }))
                                      + " · " + (modelData.type || "text")
                            }
                            MouseArea {
                                anchors.fill: parent
                                cursorShape: Qt.PointingHandCursor
                                onClicked: refItem.open = !refItem.open
                            }
                        }
                        Text {
                            visible: refItem.open && (modelData.excerpt || "") !== ""
                            text: modelData.excerpt || ""
                            width: parent.width
                            wrapMode: Text.Wrap
                            color: Theme.textMuted
                            font.pixelSize: Theme.fontXS
                            lineHeight: 1.3
                        }
                    }
                }
            }
        }
    }
}
