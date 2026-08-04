// SettingsPage — 设置页
//
// 左侧子导航 + 右侧分区内容（Flickable 滚动）：
// 语言 / 模型配置 / 默认模型 / 数据位置 / 凭据 / 一键部署 / 依赖管理 / 方案选择
import QtQuick
import QtQuick.Layouts
import QtQuick.Controls as QC
import "../theme"
import "../components"

Item {
    id: root

    property int section: 0
    property string currentProvider: ""

    // 依赖勾选状态 {key: bool}（可选组件安装/卸载）
    property var depChecked: ({})
    // 凭据输入缓存 {key: value}
    property var credValues: ({})

    signal modelsSaved()

    // ---------------------------------------------------------- 桥接信号
    Connections {
        target: settingsBridge
        function onTestConnectionResult(ok, msg) {
            testDlg.singleButton = true
            testDlg.dangerConfirm = !ok
            testDlg.openCustom(ok ? (i18n.language, i18n.tr("settings.testSuccess"))
                                  : (i18n.language, i18n.tr("settings.testFailed")))
            testDlg.message = msg
        }
        function onDepLogAppended(line) { root.appendLog(depLog, line) }
        function onDepFinished(ok, msg) { if (msg) root.appendLog(depLog, msg) }
        function onBootstrapLogAppended(line) { root.appendLog(bootLog, line) }
        function onBootstrapFinished(ok, err) {
            bootDlg.singleButton = true
            bootDlg.dangerConfirm = !ok
            bootDlg.openCustom(ok ? (i18n.language, i18n.tr("settings.bootstrapDone"))
                                  : (i18n.language, i18n.tr("settings.bootstrapPartial")))
            bootDlg.message = (ok ? "" : err)
                              + (i18n.language, i18n.tr("settings.bootstrapDoneSuffix"))
        }
        function onMigrateFinished(ok, msg) {
            migDlg.singleButton = true
            migDlg.dangerConfirm = !ok
            migDlg.openCustom(ok ? (i18n.language, i18n.tr("settings.migrateDone"))
                                 : (i18n.language, i18n.tr("settings.migrateFailed")))
            migDlg.message = msg + (ok ? (i18n.language, i18n.tr("settings.migrateDoneSuffix")) : "")
        }
    }

    function appendLog(logView, line) {
        logView.append(line)
    }

    // 当前选中厂商对象（providers 变化后重新解析）
    function currentProviderObj() {
        var ps = settingsBridge.providers
        for (var i = 0; i < ps.length; i++)
            if (ps[i].key === root.currentProvider) return ps[i]
        return null
    }

    // ============================================================ 布局
    RowLayout {
        anchors.fill: parent
        spacing: Theme.spaceM

        // ---- 子导航 ----
        GlassPanel {
            Layout.preferredWidth: 168
            Layout.fillHeight: true
            radius: Theme.radiusXL

            ColumnLayout {
                anchors.fill: parent
                anchors.margins: Theme.spaceM
                spacing: Theme.spaceXS

                Text {
                    text: (i18n.language, i18n.tr("settings.title"))
                    color: Theme.textPrimary
                    font.pixelSize: Theme.fontL
                    font.bold: true
                    Layout.bottomMargin: Theme.spaceS
                }

                Repeater {
                    model: [
                        { "icon": "🌐", "key": "settings.language" },
                        { "icon": "🤖", "key": "settings.models" },
                        { "icon": "⭐", "key": "settings.defaults" },
                        { "icon": "📂", "key": "settings.dataLocation" },
                        { "icon": "🔑", "key": "settings.credentials" },
                        { "icon": "🚀", "key": "settings.bootstrapRun" },
                        { "icon": "📦", "key": "settings.deps" },
                        { "icon": "🧩", "key": "settings.scheme" },
                        { "icon": "🖥️", "key": "settings.compute" }
                    ]
                    NavRailButton {
                        Layout.fillWidth: true
                        icon: modelData.icon
                        text: (i18n.language, i18n.tr(modelData.key))
                        active: root.section === index
                        onClicked: root.section = index
                    }
                }
                Item { Layout.fillHeight: true }
            }
        }

        // ---- 内容区 ----
        StackLayout {
            Layout.fillWidth: true
            Layout.fillHeight: true
            currentIndex: root.section

            // ==================== 0. 语言 ====================
            Flickable {
                clip: true
                contentWidth: width
                contentHeight: langCol.implicitHeight
                boundsBehavior: Flickable.StopAtBounds

                ColumnLayout {
                    id: langCol
                    width: parent.width
                    spacing: Theme.spaceM

                    GlassPanel {
                        Layout.fillWidth: true
                        Layout.preferredHeight: langInner.implicitHeight + Theme.spaceL * 2
                        radius: Theme.radiusXL
                        ColumnLayout {
                            id: langInner
                            anchors.left: parent.left
                            anchors.right: parent.right
                            anchors.top: parent.top
                            anchors.margins: Theme.spaceL
                            spacing: Theme.spaceS
                            Text {
                                text: (i18n.language, i18n.tr("settings.language"))
                                color: Theme.textPrimary
                                font.pixelSize: Theme.fontL
                                font.bold: true
                            }
                            Text {
                                Layout.fillWidth: true
                                text: (i18n.language, i18n.tr("settings.languageHint"))
                                color: Theme.textMuted
                                font.pixelSize: Theme.fontS
                                wrapMode: Text.Wrap
                            }
                            GlassComboBox {
                                Layout.preferredWidth: 240
                                model: i18n.availableLanguages
                                displayRole: "name"
                                currentIndex: {
                                    i18n.language   // 依赖语言变化重建
                                    var ls = i18n.availableLanguages
                                    for (var i = 0; i < ls.length; i++)
                                        if (ls[i].code === i18n.language) return i
                                    return 0
                                }
                                onActivated: function(index, item) { i18n.language = item.code }
                            }
                        }
                    }
                    Item { Layout.fillHeight: true }
                }
            }

            // ==================== 1. 模型配置 ====================
            RowLayout {
                spacing: Theme.spaceM

                // 厂商列表
                GlassPanel {
                    Layout.preferredWidth: 220
                    Layout.fillHeight: true
                    radius: Theme.radiusXL

                    ColumnLayout {
                        anchors.fill: parent
                        anchors.margins: Theme.spaceM
                        spacing: Theme.spaceS
                        Text {
                            text: (i18n.language, i18n.tr("settings.providers"))
                            color: Theme.textSecondary
                            font.pixelSize: Theme.fontM
                            font.bold: true
                        }
                        ListView {
                            Layout.fillWidth: true
                            Layout.fillHeight: true
                            clip: true
                            spacing: Theme.spaceXS
                            model: settingsBridge.providers
                            delegate: Item {
                                width: parent.width
                                height: 40
                                readonly property bool isActive: modelData.key === root.currentProvider
                                GlassPanel {
                                    anchors.fill: parent
                                    radius: Theme.radiusM
                                    specularOpacity: 0.3
                                    shadow: false
                                    sheen: false
                                    edgeLight: false
                                    opacity: isActive || provMouse.containsMouse ? 1 : 0
                                    fillTop: isActive ? Theme.accentSoft : Qt.alpha("#FFFFFF", 0.10)
                                    fillBottom: "transparent"
                                    borderTop: isActive ? Qt.alpha(Theme.accent, 0.5)
                                                        : Theme.glassBorderTop
                                    Behavior on opacity { NumberAnimation { duration: Theme.animFast } }
                                }
                                RowLayout {
                                    anchors.fill: parent
                                    anchors.leftMargin: Theme.spaceM
                                    anchors.rightMargin: Theme.spaceS
                                    Text {
                                        Layout.fillWidth: true
                                        text: modelData.displayName
                                        color: isActive ? Theme.textPrimary : Theme.textSecondary
                                        font.pixelSize: Theme.fontM
                                        elide: Text.ElideRight
                                    }
                                    GlassBadge {
                                        text: modelData.configured
                                              ? (i18n.language, i18n.tr("common.configured"))
                                              : (i18n.language, i18n.tr("common.unconfigured"))
                                        tone: modelData.configured ? "success" : "muted"
                                    }
                                }
                                MouseArea {
                                    id: provMouse
                                    anchors.fill: parent
                                    hoverEnabled: true
                                    cursorShape: Qt.PointingHandCursor
                                    onClicked: {
                                        root.currentProvider = modelData.key
                                        apiKeyField.text = modelData.apiKey || ""
                                    }
                                }
                            }
                        }
                    }
                }

                // 厂商详情
                GlassPanel {
                    Layout.fillWidth: true
                    Layout.fillHeight: true
                    radius: Theme.radiusXL

                    Flickable {
                        anchors.fill: parent
                        anchors.margins: Theme.spaceL
                        clip: true
                        contentWidth: width
                        contentHeight: provCol.implicitHeight
                        boundsBehavior: Flickable.StopAtBounds

                        ColumnLayout {
                            id: provCol
                            width: parent.width
                            spacing: Theme.spaceM

                            property var prov: root.currentProviderObj()

                            Text {
                                visible: provCol.prov === null
                                text: (i18n.language, i18n.tr("settings.selectProviderFirst"))
                                color: Theme.textMuted
                                font.pixelSize: Theme.fontM
                            }

                            Text {
                                visible: provCol.prov !== null
                                text: provCol.prov ? provCol.prov.displayName : ""
                                color: Theme.textPrimary
                                font.pixelSize: Theme.fontL
                                font.bold: true
                            }
                            Text {
                                visible: provCol.prov !== null
                                Layout.fillWidth: true
                                text: provCol.prov ? ("API Base: " + provCol.prov.apiBase) : ""
                                color: Theme.textMuted
                                font.pixelSize: Theme.fontS
                                elide: Text.ElideRight
                            }

                            // API Key 行
                            RowLayout {
                                visible: provCol.prov !== null
                                Layout.fillWidth: true
                                spacing: Theme.spaceS
                                GlassInput {
                                    id: apiKeyField
                                    Layout.fillWidth: true
                                    echoMode: TextInput.Password
                                    placeholder: (i18n.language, i18n.tr("settings.apiKeyPlaceholder"))
                                }
                                GlassButton {
                                    text: (i18n.language, i18n.tr("settings.saveApiKey"))
                                    onClicked: settingsBridge.saveApiKey(root.currentProvider, apiKeyField.text)
                                }
                            }
                            RowLayout {
                                visible: provCol.prov !== null
                                spacing: Theme.spaceS
                                GlassButton {
                                    variant: "ghost"
                                    text: (i18n.language, i18n.tr("settings.applyKey"))
                                    onClicked: settingsBridge.openKeyApplyUrl(root.currentProvider)
                                }
                                GlassButton {
                                    variant: "ghost"
                                    text: (i18n.language, i18n.tr("settings.testConnection"))
                                    onClicked: settingsBridge.testConnection(root.currentProvider, apiKeyField.text)
                                }
                                GlassButton {
                                    variant: "danger"
                                    text: (i18n.language, i18n.tr("settings.clearKey"))
                                    onClicked: clearKeyDlg.openConfirm(
                                        (i18n.language, i18n.tr("settings.clearKey")),
                                        (i18n.language, i18n.tr("settings.clearKeyConfirm")),
                                        function() {
                                            settingsBridge.clearApiKey(root.currentProvider)
                                            apiKeyField.text = ""
                                        }, true)
                                }
                            }

                            // 模型勾选
                            Text {
                                visible: provCol.prov !== null
                                text: (i18n.language, i18n.tr("settings.availableModels"))
                                color: Theme.textSecondary
                                font.pixelSize: Theme.fontM
                            }
                            Repeater {
                                model: provCol.prov ? provCol.prov.models : []
                                delegate: GlassCheckBox {
                                    text: modelData.displayName
                                    checked: modelData.enabled
                                    onToggled: function(c) {
                                        checked = c            // 断开绑定，立即更新视觉
                                        modelData.enabled = c
                                    }
                                }
                            }
                            GlassButton {
                                visible: provCol.prov !== null
                                variant: "ghost"
                                text: (i18n.language, i18n.tr("settings.saveModelStates"))
                                onClicked: {
                                    var states = {}
                                    var models = provCol.prov ? provCol.prov.models : []
                                    for (var i = 0; i < models.length; i++)
                                        states[models[i].modelName] = models[i].enabled
                                    settingsBridge.saveModelStates(root.currentProvider, states)
                                }
                            }
                        }
                    }
                }
            }

            // ==================== 2. 默认模型 ====================
            Flickable {
                clip: true
                contentWidth: width
                contentHeight: defCol.implicitHeight
                boundsBehavior: Flickable.StopAtBounds

                ColumnLayout {
                    id: defCol
                    width: parent.width
                    spacing: Theme.spaceM

                    GlassPanel {
                        Layout.fillWidth: true
                        Layout.preferredHeight: defInner.implicitHeight + Theme.spaceL * 2
                        radius: Theme.radiusXL
                        ColumnLayout {
                            id: defInner
                            anchors.left: parent.left
                            anchors.right: parent.right
                            anchors.top: parent.top
                            anchors.margins: Theme.spaceL
                            spacing: Theme.spaceM

                            Text {
                                text: (i18n.language, i18n.tr("settings.defaults"))
                                color: Theme.textPrimary
                                font.pixelSize: Theme.fontL
                                font.bold: true
                            }
                            Text {
                                Layout.fillWidth: true
                                text: (i18n.language, i18n.tr("settings.defaultsHint"))
                                color: Theme.textMuted
                                font.pixelSize: Theme.fontS
                                wrapMode: Text.Wrap
                                lineHeight: 1.3
                            }

                            Repeater {
                                model: settingsBridge.defaultRoles
                                delegate: RowLayout {
                                    id: roleRow
                                    Layout.fillWidth: true
                                    spacing: Theme.spaceM

                                    property var comboModel: {
                                        settingsBridge.enabledModels   // 依赖刷新
                                        var arr = [{
                                            "label": (i18n.language, i18n.tr("common.auto")),
                                            "providerKey": "", "modelName": ""
                                        }]
                                        var ms = settingsBridge.enabledModels
                                        for (var i = 0; i < ms.length; i++) arr.push(ms[i])
                                        return arr
                                    }

                                    Text {
                                        Layout.preferredWidth: 180
                                        text: (i18n.language, i18n.tr(modelData.roleKey))
                                        color: Theme.textPrimary
                                        font.pixelSize: Theme.fontM
                                        elide: Text.ElideRight
                                    }
                                    GlassComboBox {
                                        Layout.fillWidth: true
                                        model: roleRow.comboModel
                                        currentIndex: {
                                            roleRow.comboModel   // 依赖刷新
                                            for (var i = 0; i < roleRow.comboModel.length; i++) {
                                                var it = roleRow.comboModel[i]
                                                if (it.providerKey === modelData.providerKey
                                                        && it.modelName === modelData.modelName)
                                                    return i
                                            }
                                            return 0
                                        }
                                        onActivated: function(index, item) {
                                            settingsBridge.setDefaultModel(
                                                modelData.role, item.providerKey, item.modelName)
                                            settingsBridge.notifyDefaultsSaved()
                                            root.modelsSaved()
                                        }
                                    }
                                }
                            }
                        }
                    }
                    Item { Layout.fillHeight: true }
                }
            }

            // ==================== 3. 数据位置 ====================
            Flickable {
                clip: true
                contentWidth: width
                contentHeight: dataCol.implicitHeight
                boundsBehavior: Flickable.StopAtBounds

                ColumnLayout {
                    id: dataCol
                    width: parent.width
                    spacing: Theme.spaceM

                    GlassPanel {
                        Layout.fillWidth: true
                        Layout.preferredHeight: dataInner.implicitHeight + Theme.spaceL * 2
                        radius: Theme.radiusXL
                        ColumnLayout {
                            id: dataInner
                            anchors.left: parent.left
                            anchors.right: parent.right
                            anchors.top: parent.top
                            anchors.margins: Theme.spaceL
                            spacing: Theme.spaceS

                            Text {
                                text: (i18n.language, i18n.tr("settings.dataLocation"))
                                color: Theme.textPrimary
                                font.pixelSize: Theme.fontL
                                font.bold: true
                            }
                            Text {
                                Layout.fillWidth: true
                                text: (i18n.language, i18n.tr("settings.dataLocationHint"))
                                color: Theme.textMuted
                                font.pixelSize: Theme.fontS
                                wrapMode: Text.Wrap
                                lineHeight: 1.3
                            }
                            RowLayout {
                                Layout.fillWidth: true
                                spacing: Theme.spaceM
                                Text {
                                    Layout.fillWidth: true
                                    text: (i18n.language, i18n.tr("settings.currentLocation"))
                                          + " " + settingsBridge.dataRoot
                                    color: Theme.textSecondary
                                    font.pixelSize: Theme.fontM
                                    elide: Text.ElideMiddle
                                }
                                GlassButton {
                                    variant: "ghost"
                                    enabled: !settingsBridge.migrateRunning
                                    text: (i18n.language, i18n.tr("settings.changeLocation"))
                                    onClicked: {
                                        var dir = settingsBridge.pickDataDirectory()
                                        if (dir === "") return
                                        migConfirmDlg.openConfirm(
                                            (i18n.language, i18n.tr("settings.changeLocation")),
                                            (i18n.language, i18n.trf("settings.migrateConfirm", { "dir": dir })),
                                            function() { settingsBridge.migrateData(dir) },
                                            false)
                                    }
                                }
                            }
                            GlassProgressBar {
                                Layout.fillWidth: true
                                visible: settingsBridge.migrateRunning
                                indeterminate: true
                                text: (i18n.language, i18n.tr("settings.migrating"))
                            }
                        }
                    }
                    Item { Layout.fillHeight: true }
                }
            }

            // ==================== 4. 凭据 ====================
            Flickable {
                clip: true
                contentWidth: width
                contentHeight: credCol.implicitHeight
                boundsBehavior: Flickable.StopAtBounds

                ColumnLayout {
                    id: credCol
                    width: parent.width
                    spacing: Theme.spaceM

                    GlassPanel {
                        Layout.fillWidth: true
                        Layout.preferredHeight: credInner.implicitHeight + Theme.spaceL * 2
                        radius: Theme.radiusXL
                        ColumnLayout {
                            id: credInner
                            anchors.left: parent.left
                            anchors.right: parent.right
                            anchors.top: parent.top
                            anchors.margins: Theme.spaceL
                            spacing: Theme.spaceS

                            Text {
                                text: (i18n.language, i18n.tr("settings.credentials"))
                                color: Theme.textPrimary
                                font.pixelSize: Theme.fontL
                                font.bold: true
                            }
                            Text {
                                Layout.fillWidth: true
                                text: (i18n.language, i18n.tr("settings.credentialsHint"))
                                color: Theme.textMuted
                                font.pixelSize: Theme.fontS
                                wrapMode: Text.Wrap
                                lineHeight: 1.3
                            }

                            Repeater {
                                model: settingsBridge.credentials
                                delegate: RowLayout {
                                    Layout.fillWidth: true
                                    spacing: Theme.spaceM
                                    Text {
                                        Layout.preferredWidth: 200
                                        text: modelData.name
                                        color: Theme.textPrimary
                                        font.pixelSize: Theme.fontM
                                        elide: Text.ElideRight
                                    }
                                    GlassInput {
                                        id: credField
                                        Layout.fillWidth: true
                                        echoMode: TextInput.Password
                                        placeholder: modelData.placeholder
                                        onTextChanged: {
                                            var m = root.credValues
                                            m[modelData.key] = text
                                            root.credValues = m
                                        }
                                    }
                                    GlassBadge {
                                        text: modelData.isSet
                                              ? (i18n.language, i18n.tr("common.isSet"))
                                              : (i18n.language, i18n.tr("common.notSet"))
                                        tone: modelData.isSet ? "success" : "muted"
                                    }
                                }
                            }

                            RowLayout {
                                Layout.topMargin: Theme.spaceS
                                spacing: Theme.spaceM
                                GlassButton {
                                    text: (i18n.language, i18n.tr("settings.saveCredentials"))
                                    onClicked: {
                                        var values = {}
                                        for (var k in root.credValues)
                                            if (root.credValues[k]) values[k] = root.credValues[k]
                                        settingsBridge.saveCredentials(values)
                                    }
                                }
                                GlassButton {
                                    variant: "danger"
                                    text: (i18n.language, i18n.tr("settings.clearCredentials"))
                                    onClicked: credClearDlg.openConfirm(
                                        (i18n.language, i18n.tr("settings.clearCredentials")),
                                        (i18n.language, i18n.tr("settings.clearCredentialsConfirm")),
                                        function() { settingsBridge.clearAllCredentials() },
                                        true)
                                }
                            }
                        }
                    }
                    Item { Layout.fillHeight: true }
                }
            }

            // ==================== 5. 一键部署 ====================
            ColumnLayout {
                spacing: Theme.spaceM

                GlassPanel {
                    Layout.fillWidth: true
                    Layout.preferredHeight: bootInner.implicitHeight + Theme.spaceL * 2
                    radius: Theme.radiusXL
                    ColumnLayout {
                        id: bootInner
                        anchors.left: parent.left
                        anchors.right: parent.right
                        anchors.top: parent.top
                        anchors.margins: Theme.spaceL
                        spacing: Theme.spaceS

                        Text {
                            text: (i18n.language, i18n.tr("settings.bootstrap"))
                            color: Theme.textPrimary
                            font.pixelSize: Theme.fontL
                            font.bold: true
                        }
                        Text {
                            Layout.fillWidth: true
                            text: (i18n.language, i18n.tr("settings.bootstrapHint"))
                            color: Theme.textMuted
                            font.pixelSize: Theme.fontS
                            wrapMode: Text.Wrap
                            lineHeight: 1.3
                        }
                        RowLayout {
                            spacing: Theme.spaceM
                            GlassButton {
                                enabled: !settingsBridge.bootstrapRunning
                                text: (i18n.language, i18n.tr("settings.bootstrapRun"))
                                onClicked: bootConfirmDlg.openConfirm(
                                    (i18n.language, i18n.tr("settings.bootstrapRun")),
                                    (i18n.language, i18n.tr("settings.bootstrapConfirm")),
                                    function() {
                                        bootLog.clear()
                                        settingsBridge.runBootstrap()
                                    }, false)
                            }
                            GlassProgressBar {
                                Layout.fillWidth: true
                                visible: settingsBridge.bootstrapRunning
                                indeterminate: true
                                text: (i18n.language, i18n.tr("common.inProgress"))
                            }
                        }
                    }
                }

                // 实时日志
                GlassPanel {
                    Layout.fillWidth: true
                    Layout.fillHeight: true
                    radius: Theme.radiusXL
                    specularOpacity: 0.2
                    LogView { id: bootLog; anchors.fill: parent; anchors.margins: Theme.spaceM }
                }
            }

            // ==================== 6. 依赖管理 ====================
            ColumnLayout {
                spacing: Theme.spaceM

                Flickable {
                    Layout.fillWidth: true
                    Layout.preferredHeight: depTopCol.implicitHeight
                    clip: true
                    contentWidth: width
                    contentHeight: depTopCol.implicitHeight
                    boundsBehavior: Flickable.StopAtBounds

                    ColumnLayout {
                        id: depTopCol
                        width: parent.width
                        spacing: Theme.spaceM

                        // 核心依赖
                        GlassPanel {
                            Layout.fillWidth: true
                            Layout.preferredHeight: coreInner.implicitHeight + Theme.spaceL * 2
                            radius: Theme.radiusXL
                            ColumnLayout {
                                id: coreInner
                                anchors.left: parent.left
                                anchors.right: parent.right
                                anchors.top: parent.top
                                anchors.margins: Theme.spaceL
                                spacing: Theme.spaceS
                                Text {
                                    text: (i18n.language, i18n.tr("settings.depsCore"))
                                    color: Theme.textPrimary
                                    font.pixelSize: Theme.fontM
                                    font.bold: true
                                }
                                Flow {
                                    Layout.fillWidth: true
                                    spacing: Theme.spaceS
                                    Repeater {
                                        model: settingsBridge.coreDependencies
                                        delegate: GlassBadge {
                                            text: modelData.name + "  " + (modelData.installed ? "✓" : "✗")
                                            tone: modelData.installed ? "success" : "danger"
                                        }
                                    }
                                }
                            }
                        }

                        // 可选组件
                        GlassPanel {
                            Layout.fillWidth: true
                            Layout.preferredHeight: optInner.implicitHeight + Theme.spaceL * 2
                            radius: Theme.radiusXL
                            ColumnLayout {
                                id: optInner
                                anchors.left: parent.left
                                anchors.right: parent.right
                                anchors.top: parent.top
                                anchors.margins: Theme.spaceL
                                spacing: Theme.spaceS
                                Text {
                                    text: (i18n.language, i18n.tr("settings.depsOptional"))
                                    color: Theme.textPrimary
                                    font.pixelSize: Theme.fontM
                                    font.bold: true
                                }
                                Repeater {
                                    model: settingsBridge.optionalComponents
                                    delegate: RowLayout {
                                        Layout.fillWidth: true
                                        spacing: Theme.spaceM
                                        GlassCheckBox {
                                            Layout.fillWidth: true
                                            text: modelData.name + "  —  " + modelData.description
                                            checked: root.depChecked[modelData.key] === true
                                            onToggled: function(c) {
                                                checked = c      // 断开绑定，立即更新视觉
                                                var m = root.depChecked
                                                m[modelData.key] = c
                                                root.depChecked = m
                                            }
                                        }
                                        GlassBadge {
                                            text: modelData.installed
                                                  ? (i18n.language, i18n.tr("common.installed"))
                                                  : (i18n.language, i18n.tr("common.notInstalled"))
                                            tone: modelData.installed ? "success" : "muted"
                                        }
                                    }
                                }
                                RowLayout {
                                    Layout.topMargin: Theme.spaceS
                                    spacing: Theme.spaceM
                                    GlassButton {
                                        enabled: !settingsBridge.depRunning
                                        text: (i18n.language, i18n.tr("settings.installSelected"))
                                        onClicked: root.runDepTask(true)
                                    }
                                    GlassButton {
                                        variant: "danger"
                                        enabled: !settingsBridge.depRunning
                                        text: (i18n.language, i18n.tr("settings.uninstallSelected"))
                                        onClicked: root.runDepTask(false)
                                    }
                                    GlassButton {
                                        variant: "ghost"
                                        enabled: !settingsBridge.depRunning
                                        text: (i18n.language, i18n.tr("settings.refreshStatus"))
                                        onClicked: settingsBridge.refreshDependencies()
                                    }
                                    GlassProgressBar {
                                        Layout.fillWidth: true
                                        visible: settingsBridge.depRunning
                                        indeterminate: true
                                        text: (i18n.language, i18n.tr("common.inProgress"))
                                    }
                                }
                            }
                        }
                    }
                }

                // 输出日志
                GlassPanel {
                    Layout.fillWidth: true
                    Layout.fillHeight: true
                    Layout.minimumHeight: 120
                    radius: Theme.radiusXL
                    specularOpacity: 0.2
                    LogView { id: depLog; anchors.fill: parent; anchors.margins: Theme.spaceM }
                }
            }

            // ==================== 7. 方案选择 ====================
            Flickable {
                clip: true
                contentWidth: width
                contentHeight: schemeCol.implicitHeight
                boundsBehavior: Flickable.StopAtBounds

                ColumnLayout {
                    id: schemeCol
                    width: parent.width
                    spacing: Theme.spaceM

                    GlassPanel {
                        Layout.fillWidth: true
                        Layout.preferredHeight: schemeInner.implicitHeight + Theme.spaceL * 2
                        radius: Theme.radiusXL
                        ColumnLayout {
                            id: schemeInner
                            anchors.left: parent.left
                            anchors.right: parent.right
                            anchors.top: parent.top
                            anchors.margins: Theme.spaceL
                            spacing: Theme.spaceM

                            Text {
                                text: (i18n.language, i18n.tr("settings.scheme"))
                                color: Theme.textPrimary
                                font.pixelSize: Theme.fontL
                                font.bold: true
                            }
                            Text {
                                text: (i18n.language, i18n.trf("settings.scheme.current",
                                      { "vlm": settingsBridge.vlmScheme, "emb": settingsBridge.embedScheme }))
                                color: Theme.textMuted
                                font.pixelSize: Theme.fontS
                            }

                            RowLayout {
                                Layout.fillWidth: true
                                spacing: Theme.spaceM
                                Text {
                                    Layout.preferredWidth: 140
                                    text: (i18n.language, i18n.tr("settings.scheme.vlm"))
                                    color: Theme.textPrimary
                                    font.pixelSize: Theme.fontM
                                }
                                GlassComboBox {
                                    id: vlmCombo
                                    Layout.fillWidth: true
                                    model: [
                                        { "label": (i18n.language, i18n.tr("settings.scheme.vlmA")), "value": "A" },
                                        { "label": (i18n.language, i18n.tr("settings.scheme.vlmB")), "value": "B" },
                                        { "label": (i18n.language, i18n.tr("settings.scheme.vlmC")), "value": "C" }
                                    ]
                                    currentIndex: Math.max(0, ["A", "B", "C"].indexOf(settingsBridge.vlmScheme))
                                }
                            }
                            RowLayout {
                                Layout.fillWidth: true
                                spacing: Theme.spaceM
                                Text {
                                    Layout.preferredWidth: 140
                                    text: (i18n.language, i18n.tr("settings.scheme.embedding"))
                                    color: Theme.textPrimary
                                    font.pixelSize: Theme.fontM
                                }
                                GlassComboBox {
                                    id: embCombo
                                    Layout.fillWidth: true
                                    model: [
                                        { "label": (i18n.language, i18n.tr("settings.scheme.embedA")), "value": "A" },
                                        { "label": (i18n.language, i18n.tr("settings.scheme.embedB")), "value": "B" }
                                    ]
                                    currentIndex: Math.max(0, ["A", "B"].indexOf(settingsBridge.embedScheme))
                                }
                            }
                            GlassButton {
                                text: (i18n.language, i18n.tr("settings.scheme.save"))
                                onClicked: settingsBridge.saveScheme(
                                    vlmCombo.model[vlmCombo.currentIndex].value,
                                    embCombo.model[embCombo.currentIndex].value)
                            }
                        }
                    }
                    Item { Layout.fillHeight: true }
                }
            }

            // ==================== 8. 计算设备 ====================
            Flickable {
                clip: true
                contentWidth: width
                contentHeight: computeCol.implicitHeight
                boundsBehavior: Flickable.StopAtBounds

                ColumnLayout {
                    id: computeCol
                    width: parent.width
                    spacing: Theme.spaceM

                    GlassPanel {
                        Layout.fillWidth: true
                        Layout.preferredHeight: computeInner.implicitHeight + Theme.spaceL * 2
                        radius: Theme.radiusXL
                        specularOpacity: 0.3
                        ColumnLayout {
                            id: computeInner
                            anchors.left: parent.left
                            anchors.right: parent.right
                            anchors.top: parent.top
                            anchors.margins: Theme.spaceL
                            spacing: Theme.spaceM

                            Text {
                                text: (i18n.language, i18n.tr("settings.compute"))
                                color: Theme.textPrimary
                                font.pixelSize: Theme.fontL
                                font.bold: true
                            }
                            Text {
                                Layout.fillWidth: true
                                text: (i18n.language, i18n.tr("settings.computeHint"))
                                color: Theme.textMuted
                                font.pixelSize: Theme.fontS
                                wrapMode: Text.Wrap
                                lineHeight: 1.3
                            }
                            Text {
                                text: (i18n.language, i18n.tr("settings.compute.active"))
                                     + " " + settingsBridge.computeActiveDesc
                                color: Theme.textSecondary
                                font.pixelSize: Theme.fontS
                            }

                            RowLayout {
                                Layout.fillWidth: true
                                spacing: Theme.spaceM
                                Text {
                                    Layout.preferredWidth: 80
                                    text: (i18n.language, i18n.tr("settings.compute.device"))
                                    color: Theme.textPrimary
                                    font.pixelSize: Theme.fontM
                                }
                                GlassComboBox {
                                    id: computeCombo
                                    Layout.fillWidth: true
                                    displayRole: "label"
                                    model: settingsBridge.computeOptions
                                    currentIndex: {
                                        // 依赖 computeDevice 属性变化重建
                                        var dev = settingsBridge.computeDevice
                                        var opts = settingsBridge.computeOptions
                                        for (var i = 0; i < opts.length; i++)
                                            if (opts[i].value === dev) return i
                                        return 0
                                    }
                                }
                            }
                            GlassButton {
                                text: (i18n.language, i18n.tr("common.save"))
                                onClicked: {
                                    var item = computeCombo.model[computeCombo.currentIndex]
                                    if (item) settingsBridge.setComputeDevice(item.value)
                                }
                            }
                        }
                    }
                    Item { Layout.fillHeight: true }
                }
            }
        }
    }

    // ---------------------------------------------------------- 依赖任务
    function runDepTask(install) {
        var keys = []
        var names = []
        var comps = settingsBridge.optionalComponents
        for (var i = 0; i < comps.length; i++) {
            if (root.depChecked[comps[i].key] === true) {
                keys.push(comps[i].key)
                names.push(comps[i].name)
            }
        }
        if (keys.length === 0) {
            // 交由 bridge 发出「请先勾选组件」轻提示
            settingsBridge.runDependencyTask([], install)
            return
        }
        depConfirmDlg.openConfirm(
            install ? (i18n.language, i18n.tr("settings.installSelected"))
                    : (i18n.language, i18n.tr("settings.uninstallSelected")),
            (i18n.language, i18n.trf("settings.installConfirm", {
                "action": install ? (i18n.language, i18n.tr("settings.action.install"))
                                  : (i18n.language, i18n.tr("settings.action.uninstall")),
                "names": names.join("\n")
            })),
            function() {
                depLog.clear()
                settingsBridge.runDependencyTask(keys, install)
            }, !install)
    }

    // ---------------------------------------------------------- 对话框
    GlassDialog { id: testDlg }
    GlassDialog { id: clearKeyDlg }
    GlassDialog { id: migConfirmDlg }
    GlassDialog { id: migDlg }
    GlassDialog { id: credClearDlg }
    GlassDialog { id: bootConfirmDlg }
    GlassDialog { id: bootDlg }
    GlassDialog { id: depConfirmDlg }

    // 日志视图（内部复用组件）
    component LogView: Item {
        property alias text: area.text
        function append(line) { area.append(line); area.cursorPosition = area.length }
        function clear() { area.clear() }

        QC.ScrollView {
            anchors.fill: parent
            clip: true
            QC.TextArea {
                id: area
                readOnly: true
                wrapMode: QC.TextArea.Wrap
                color: Theme.textSecondary
                font.pixelSize: Theme.fontS
                font.family: "Consolas"
                selectByMouse: true
                background: null
            }
        }
    }
}
