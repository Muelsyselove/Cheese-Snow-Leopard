"""设置页 — 嵌入式 QWidget（不再是对话框）

四块功能：
1. 模型配置：双栏布局（左侧厂商列表，右侧模型管理），每厂商独立 API Key。
2. 凭据配置：PostgreSQL/MinIO 密码 + 一键自动配置（生成密码 + 写 keyring + 更新 config.yaml）。
3. 依赖管理：核心依赖状态展示 + 可选组件勾选安装/卸载。
4. 方案选择：VLM/Embedding provider 切换（写回 config.yaml）。
"""
from __future__ import annotations

import logging
import os
import secrets
import string

from PySide6.QtCore import QThread, QObject, Signal, Qt
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel,
    QPushButton, QCheckBox, QComboBox, QFormLayout,
    QLineEdit, QMessageBox, QGroupBox, QGridLayout, QPlainTextEdit,
    QScrollArea, QListWidget, QListWidgetItem, QSplitter,
)

from services.dependency_service import DependencyService
from services.credential_service import CredentialService
from services.model_config_service import ModelConfigService
from utils.credentials import get_credential, set_credential
from presets.llm_providers import PROVIDERS, get_provider

logger = logging.getLogger(__name__)


# ============================================================
# 后台安装 Worker 包装
# ============================================================
class _WorkerHost(QObject):
    progress = Signal(str)
    finished = Signal(bool, str)

    def __init__(self, worker):
        super().__init__()
        self._worker = worker
        self._thread: QThread | None = None

    def start(self):
        self._thread = QThread()
        self._worker.moveToThread(self._thread)
        self._thread.started.connect(self._worker.run)
        self._worker.progress.connect(self.progress)
        self._worker.finished.connect(self._on_finished)
        self._thread.start()

    def _on_finished(self, ok: bool, msg: str):
        if self._thread:
            self._thread.quit()
            self._thread.wait(3000)
        self.finished.emit(ok, msg)


# ============================================================
# 设置页（嵌入式 QWidget）
# ============================================================
class SettingsPage(QWidget):
    """嵌入式设置页 — 由主窗口 QStackedWidget 直接承载"""

    def __init__(self, parent=None, config_path: str = "config.yaml",
                 model_config_service: ModelConfigService | None = None):
        super().__init__(parent)
        self._dep_service = DependencyService()
        self._cred_service = CredentialService()
        self._config_path = config_path
        self._worker_host: _WorkerHost | None = None
        self._config: dict | None = None
        self._model_svc = model_config_service or ModelConfigService()
        self._current_provider_key: str | None = None
        # 模型复选框缓存 {model_name: QCheckBox}
        self._model_checkboxes: dict[str, QCheckBox] = {}

        self._init_ui()
        self._load_config()
        self._refresh_dependency_status()
        self._refresh_credential_status()

    # ------------------------------------------------------------------ UI
    def _init_ui(self):
        outer = QVBoxLayout(self)
        outer.setContentsMargins(16, 16, 16, 16)

        title = QLabel("设置")
        title.setStyleSheet("font-weight: bold; font-size: 18px;")
        outer.addWidget(title)

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QScrollArea.NoFrame)
        content = QWidget()
        scroll.setWidget(content)

        v = QVBoxLayout(content)
        v.setSpacing(12)

        v.addWidget(self._build_model_group())
        v.addWidget(self._build_data_location_group())
        v.addWidget(self._build_credential_group())
        v.addWidget(self._build_dep_group())
        v.addWidget(self._build_scheme_group())
        v.addStretch()

        outer.addWidget(scroll, 1)

    # ---------------------- 模型配置（双栏） ----------------------
    def _build_model_group(self) -> QGroupBox:
        group = QGroupBox("模型配置")
        group.setMinimumHeight(360)
        outer_v = QVBoxLayout(group)

        hint = QLabel(
            "左侧选择厂商，右侧填入该厂商 API Key 并勾选要启用的模型。"
            "一个厂商共用同一个 API Key。对话界面仅可选择已配置且已启用的模型。"
        )
        hint.setWordWrap(True)
        hint.setStyleSheet("color: #666; font-size: 12px;")
        outer_v.addWidget(hint)

        # 双栏：左厂商列表 + 右模型管理
        splitter = QSplitter(Qt.Horizontal)

        # ---- 左栏：厂商列表 ----
        left_box = QGroupBox("厂商")
        left_v = QVBoxLayout(left_box)
        self._provider_list = QListWidget()
        self._provider_list.currentItemChanged.connect(self._on_provider_selected)
        left_v.addWidget(self._provider_list)
        splitter.addWidget(left_box)

        # ---- 右栏：模型管理 ----
        right_box = QGroupBox("模型管理")
        right_v = QVBoxLayout(right_box)

        # 厂商信息
        self._provider_info_label = QLabel()
        self._provider_info_label.setWordWrap(True)
        self._provider_info_label.setStyleSheet("color: #555; font-size: 12px;")
        right_v.addWidget(self._provider_info_label)

        # API Key 输入行
        key_form = QFormLayout()
        key_row = QHBoxLayout()
        self._api_key_edit = QLineEdit()
        self._api_key_edit.setEchoMode(QLineEdit.Password)
        self._api_key_edit.setPlaceholderText("填入该厂商 API Key")
        key_row.addWidget(self._api_key_edit, 1)

        toggle = QPushButton("显示")
        toggle.setCheckable(True)
        toggle.setFixedWidth(50)
        def _toggle(checked):
            self._api_key_edit.setEchoMode(
                QLineEdit.Normal if checked else QLineEdit.Password
            )
            toggle.setText("隐藏" if checked else "显示")
        toggle.toggled.connect(_toggle)
        key_row.addWidget(toggle)

        self._apply_key_btn = QPushButton("申请 Key")
        self._apply_key_btn.clicked.connect(self._on_apply_key_url)
        key_row.addWidget(self._apply_key_btn)
        key_form.addRow("API Key：", key_row)
        right_v.addLayout(key_form)

        # Key 操作按钮
        key_btn_row = QHBoxLayout()
        save_key_btn = QPushButton("保存 API Key")
        save_key_btn.clicked.connect(self._on_save_api_key)
        key_btn_row.addWidget(save_key_btn)

        clear_key_btn = QPushButton("清除 Key")
        clear_key_btn.clicked.connect(self._on_clear_api_key)
        key_btn_row.addWidget(clear_key_btn)

        test_btn = QPushButton("测试连接")
        test_btn.clicked.connect(self._on_test_connection)
        key_btn_row.addWidget(test_btn)

        key_btn_row.addStretch()
        right_v.addLayout(key_btn_row)

        # 模型列表（带启用复选框）
        right_v.addWidget(QLabel("可选模型（勾选启用）："))
        self._model_list = QListWidget()
        right_v.addWidget(self._model_list, 1)

        # 启用状态保存
        model_btn_row = QHBoxLayout()
        save_models_btn = QPushButton("保存启用状态")
        save_models_btn.clicked.connect(self._on_save_model_states)
        model_btn_row.addWidget(save_models_btn)
        model_btn_row.addStretch()
        right_v.addLayout(model_btn_row)

        splitter.addWidget(right_box)
        splitter.setSizes([220, 480])
        outer_v.addWidget(splitter, 1)

        self._populate_provider_list()
        return group

    def _populate_provider_list(self):
        """填充左侧厂商列表，显示配置状态"""
        self._provider_list.clear()
        for preset, pc in self._model_svc.list_providers():
            status = "✓" if pc.configured else "○"
            label = f"{status}  {preset.display_name}"
            item = QListWidgetItem(label)
            item.setData(Qt.UserRole, preset.key)
            self._provider_list.addItem(item)
        # 默认选中第一个
        if self._provider_list.count() > 0:
            self._provider_list.setCurrentRow(0)

    def _on_provider_selected(self, current: QListWidgetItem,
                              previous: QListWidgetItem):
        if current is None:
            self._current_provider_key = None
            return
        key = current.data(Qt.UserRole)
        self._current_provider_key = key
        self._refresh_provider_detail(key)

    def _refresh_provider_detail(self, key: str):
        """刷新右侧厂商详情"""
        preset = get_provider(key)
        pc = self._model_svc.get_provider_config(key)
        if preset is None or pc is None:
            return

        # 厂商信息
        configured = "已配置" if pc.configured else "未配置"
        self._provider_info_label.setText(
            f"<b>{preset.display_name}</b>  [{configured}]\n"
            f"API Base: {preset.api_base}\n"
            f"文档: <a href='{preset.doc_url}'>{preset.doc_url}</a>"
        )

        # 回填 API Key
        self._api_key_edit.setText(pc.api_key or "")

        # 模型列表
        self._model_list.clear()
        self._model_checkboxes.clear()
        model_display = {m.model_name: m.display_name for m in preset.models}
        for mc in pc.models:
            cb = QCheckBox(f"{model_display.get(mc.model_name, mc.model_name)}  ({mc.model_name})")
            cb.setChecked(mc.enabled)
            self._model_checkboxes[mc.model_name] = cb
            item = QListWidgetItem()
            self._model_list.addItem(item)
            self._model_list.setItemWidget(item, cb)

    def _on_apply_key_url(self):
        if not self._current_provider_key:
            return
        provider = get_provider(self._current_provider_key)
        if provider is None:
            return
        from PySide6.QtGui import QDesktopServices
        from PySide6.QtCore import QUrl
        QDesktopServices.openUrl(QUrl(provider.key_apply_url))

    def _on_save_api_key(self):
        if not self._current_provider_key:
            QMessageBox.warning(self, "提示", "请先在左侧选择厂商")
            return
        api_key = self._api_key_edit.text().strip()
        if not api_key:
            QMessageBox.warning(self, "提示", "请填入 API Key")
            return
        try:
            self._model_svc.set_api_key(self._current_provider_key, api_key)
            # 同步默认模型到 config.yaml
            self._model_svc.sync_default_to_config(self._config_path)
            self._populate_provider_list()
            # 恢复选中
            self._select_provider(self._current_provider_key)
            QMessageBox.information(self, "成功", "API Key 已保存。")
        except Exception as e:
            QMessageBox.critical(self, "失败", f"保存失败: {e}")

    def _on_clear_api_key(self):
        if not self._current_provider_key:
            return
        reply = QMessageBox.question(
            self, "确认", "确认清除该厂商的 API Key？",
            QMessageBox.Yes | QMessageBox.No, QMessageBox.No
        )
        if reply != QMessageBox.Yes:
            return
        try:
            self._model_svc.clear_api_key(self._current_provider_key)
            self._populate_provider_list()
            self._select_provider(self._current_provider_key)
            QMessageBox.information(self, "完成", "API Key 已清除。")
        except Exception as e:
            QMessageBox.critical(self, "失败", f"清除失败: {e}")

    def _on_save_model_states(self):
        if not self._current_provider_key:
            QMessageBox.warning(self, "提示", "请先在左侧选择厂商")
            return
        try:
            for model_name, cb in self._model_checkboxes.items():
                self._model_svc.set_model_enabled(
                    self._current_provider_key, model_name, cb.isChecked()
                )
            # 同步默认模型到 config.yaml
            self._model_svc.sync_default_to_config(self._config_path)
            QMessageBox.information(self, "成功", "模型启用状态已保存。")
        except Exception as e:
            QMessageBox.critical(self, "失败", f"保存失败: {e}")

    def _select_provider(self, key: str):
        for i in range(self._provider_list.count()):
            item = self._provider_list.item(i)
            if item.data(Qt.UserRole) == key:
                self._provider_list.setCurrentRow(i)
                break

    def _on_test_connection(self):
        if not self._current_provider_key:
            return
        provider = get_provider(self._current_provider_key)
        if provider is None:
            return
        api_key = self._api_key_edit.text().strip() or self._model_svc.get_api_key(self._current_provider_key)
        if not api_key:
            QMessageBox.warning(self, "提示", "请先填入 API Key")
            return
        # 取第一个启用的模型做测试，否则取第一个模型
        pc = self._model_svc.get_provider_config(self._current_provider_key)
        model_name = ""
        if pc:
            for mc in pc.models:
                if mc.enabled:
                    model_name = mc.model_name
                    break
            if not model_name and pc.models:
                model_name = pc.models[0].model_name
        if not model_name:
            QMessageBox.warning(self, "提示", "该厂商无可用模型")
            return
        QMessageBox.information(self, "测试", "正在测试连接...")
        self._test_thread = QThread()
        self._test_worker = _LLMTestWorker(provider.api_base, api_key, model_name)
        self._test_worker.moveToThread(self._test_thread)
        self._test_thread.started.connect(self._test_worker.run)
        self._test_worker.finished.connect(self._on_test_done)
        self._test_thread.start()

    def _on_test_done(self, ok: bool, msg: str):
        if hasattr(self, "_test_thread") and self._test_thread:
            self._test_thread.quit()
            self._test_thread.wait(2000)
        title = "连接成功" if ok else "连接失败"
        icon = QMessageBox.Information if ok else QMessageBox.Warning
        box = QMessageBox(self)
        box.setWindowTitle(title)
        box.setIcon(icon)
        box.setText(msg)
        box.exec()

    # ---------------------- 数据存储位置 ----------------------
    def _build_data_location_group(self) -> QGroupBox:
        group = QGroupBox("数据存储位置")
        v = QVBoxLayout(group)

        try:
            from utils.paths import get_data_root, DEFAULT_DATA_ROOT
            current = get_data_root()
        except Exception:
            current = DEFAULT_DATA_ROOT

        hint = QLabel(
            "所有应用数据（对话记录、文件、解析产物、模型缓存等）默认存放在程序目录的 data/ 文件夹。\n"
            "可更改为其他位置，更改后自动迁移现有数据。"
        )
        hint.setWordWrap(True)
        hint.setStyleSheet("color: #666; font-size: 12px;")
        v.addWidget(hint)

        loc_row = QHBoxLayout()
        loc_row.addWidget(QLabel("当前位置："))
        self._data_root_label = QLabel(current)
        self._data_root_label.setStyleSheet("font-weight: bold; color: #2a6;")
        loc_row.addWidget(self._data_root_label, 1)

        change_btn = QPushButton("更改位置...")
        change_btn.clicked.connect(self._on_change_data_location)
        loc_row.addWidget(change_btn)
        v.addLayout(loc_row)
        return group

    def _on_change_data_location(self):
        """选择新数据存储位置并迁移"""
        from PySide6.QtWidgets import QFileDialog
        new_dir = QFileDialog.getExistingDirectory(
            self, "选择数据存储位置",
            self._data_root_label.text(),
        )
        if not new_dir:
            return
        new_dir = os.path.abspath(new_dir)
        from utils.paths import get_data_root, migrate_data_root
        if new_dir == os.path.abspath(get_data_root()):
            QMessageBox.information(self, "提示", "新位置与当前位置相同，无需迁移。")
            return
        reply = QMessageBox.question(
            self, "确认迁移",
            f"将把所有数据迁移到：\n{new_dir}\n\n"
            "迁移过程可能需要一些时间，期间请勿关闭应用。确认？",
            QMessageBox.Yes | QMessageBox.No, QMessageBox.No
        )
        if reply != QMessageBox.Yes:
            return
        # 后台迁移避免阻塞 UI
        self._migrate_thread = QThread()
        self._migrate_worker = _DataMigrateWorker(new_dir)
        self._migrate_worker.moveToThread(self._migrate_thread)
        self._migrate_thread.started.connect(self._migrate_worker.run)
        self._migrate_worker.finished.connect(self._on_migrate_done)
        self._migrate_thread.start()
        QMessageBox.information(self, "迁移中", "数据正在迁移，完成后会提示。")

    def _on_migrate_done(self, ok: bool, msg: str):
        if hasattr(self, "_migrate_thread") and self._migrate_thread:
            self._migrate_thread.quit()
            self._migrate_thread.wait(2000)
        if ok:
            # 更新 config.yaml
            try:
                import yaml
                from utils.paths import get_data_root
                if self._config is None:
                    self._config = {}
                self._config.setdefault("paths", {})
                self._config["paths"]["data_root"] = get_data_root()
                with open(self._config_path, "w", encoding="utf-8") as f:
                    yaml.safe_dump(self._config, f, allow_unicode=True, sort_keys=False)
                self._data_root_label.setText(get_data_root())
            except Exception as e:
                logger.error(f"更新 config.yaml 失败: {e}")
            QMessageBox.information(self, "迁移完成", msg + "\n重启应用后所有路径生效。")
        else:
            QMessageBox.warning(self, "迁移失败", msg)

    # ---------------------- 凭据配置 ----------------------
    def _build_credential_group(self) -> QGroupBox:
        group = QGroupBox("凭据配置")
        v = QVBoxLayout(group)

        hint = QLabel(
            "敏感凭据通过系统 keyring 安全存储，不写入 config.yaml 明文。\n"
            "Windows 凭据管理器 / macOS Keychain / Linux Secret Service。"
        )
        hint.setWordWrap(True)
        hint.setStyleSheet("color: #666; font-size: 12px;")
        v.addWidget(hint)

        form = QFormLayout()
        self._cred_inputs: dict[str, QLineEdit] = {}
        self._cred_status_labels: dict[str, QLabel] = {}
        for item in self._cred_service.list_items():
            row_widget = QWidget()
            row_layout = QHBoxLayout(row_widget)
            row_layout.setContentsMargins(0, 0, 0, 0)

            edit = QLineEdit()
            edit.setEchoMode(QLineEdit.Password)
            edit.setPlaceholderText(item.placeholder or item.name)
            row_layout.addWidget(edit)

            toggle = QPushButton("显示")
            toggle.setCheckable(True)
            toggle.setFixedWidth(50)
            def _toggle(checked, e=edit, b=toggle):
                e.setEchoMode(QLineEdit.Normal if checked else QLineEdit.Password)
                b.setText("隐藏" if checked else "显示")
            toggle.toggled.connect(_toggle)
            row_layout.addWidget(toggle)

            status_lbl = QLabel()
            row_layout.addWidget(status_lbl)

            self._cred_inputs[item.key] = edit
            self._cred_status_labels[item.key] = status_lbl
            form.addRow(f"{item.name}:", row_widget)
            desc_lbl = QLabel(item.description)
            desc_lbl.setStyleSheet("color: gray; font-size: 11px;")
            form.addRow("", desc_lbl)

        v.addLayout(form)

        btn_row = QHBoxLayout()
        save_btn = QPushButton("保存已填写的凭据")
        save_btn.clicked.connect(self._on_save_credentials)
        del_btn = QPushButton("清空所有凭据")
        del_btn.clicked.connect(self._on_delete_credentials)
        btn_row.addWidget(save_btn)
        btn_row.addWidget(del_btn)
        btn_row.addStretch()
        v.addLayout(btn_row)

        # 一键自动配置（生成密码 + 写 keyring + 更新 config.yaml + 同步模型默认）
        auto_box = QGroupBox("一键自动配置（使服务可直接运行）")
        auto_v = QVBoxLayout(auto_box)
        auto_hint = QLabel(
            "自动生成 PostgreSQL / MinIO 随机密码并写入 keyring，\n"
            "同时更新 config.yaml 引用，确保重启后服务可连接。\n"
            "若已配置模型，也一并同步默认模型到 config.yaml。\n"
            "注意：需确保本地 PostgreSQL / MinIO 服务使用相同密码。"
        )
        auto_hint.setWordWrap(True)
        auto_hint.setStyleSheet("color: #666; font-size: 12px;")
        auto_v.addWidget(auto_hint)
        auto_btn = QPushButton("一键完成配置")
        auto_btn.clicked.connect(self._on_auto_setup_credentials)
        auto_v.addWidget(auto_btn)
        v.addWidget(auto_box)

        return group

    def _on_auto_setup_credentials(self):
        """一键完成配置：从零开始自动发现并启动 PG/Qdrant/MinIO、生成凭据、
        初始化数据库表结构、回写 config.yaml，直到应用完全可用。

        调用 scripts.bootstrap.Bootstrap.run() 完成全部流程，
        通过后台线程执行避免阻塞 UI，实时显示日志。
        """
        reply = QMessageBox.question(
            self, "确认一键完成配置",
            "将自动执行完整部署流程：\n"
            "  - 发现并启动 PostgreSQL / Qdrant / MinIO（未安装的自动下载）\n"
            "  - 生成随机密码并写入 keyring\n"
            "  - 创建数据库用户 / 库 / 表结构\n"
            "  - 回写 config.yaml 引用\n"
            "  - 同步模型默认配置\n\n"
            "过程可能需要 1-3 分钟（首次启动 MinIO 需下载），\n"
            "期间请勿关闭应用。确认继续？",
            QMessageBox.Yes | QMessageBox.No, QMessageBox.No
        )
        if reply != QMessageBox.Yes:
            return

        # 防止重复触发
        if hasattr(self, "_bootstrap_thread") and self._bootstrap_thread and \
                self._bootstrap_thread.isRunning():
            QMessageBox.information(self, "提示", "已有部署任务在执行中，请等待完成。")
            return

        # 构建进度对话框
        self._bootstrap_dialog = QDialog(self)
        self._bootstrap_dialog.setWindowTitle("一键部署进度")
        self._bootstrap_dialog.resize(720, 520)
        dlg_v = QVBoxLayout(self._bootstrap_dialog)
        dlg_v.addWidget(QLabel("实时日志："))
        self._bootstrap_log = QPlainTextEdit()
        self._bootstrap_log.setReadOnly(True)
        self._bootstrap_log.setMinimumHeight(380)
        dlg_v.addWidget(self._bootstrap_log, 1)
        self._bootstrap_status_lbl = QLabel("进行中 ...")
        self._bootstrap_status_lbl.setStyleSheet("color: #2a6; font-weight: bold;")
        dlg_v.addWidget(self._bootstrap_status_lbl)
        self._bootstrap_close_btn = QPushButton("关闭")
        self._bootstrap_close_btn.setEnabled(False)
        self._bootstrap_close_btn.clicked.connect(self._bootstrap_dialog.accept)
        dlg_v.addWidget(self._bootstrap_close_btn)

        # 后台线程执行 bootstrap
        from scripts.bootstrap import Bootstrap
        self._bootstrap_thread = QThread()
        self._bootstrap_worker = _BootstrapWorker(Bootstrap, self._config_path)
        self._bootstrap_worker.moveToThread(self._bootstrap_thread)
        self._bootstrap_thread.started.connect(self._bootstrap_worker.run)
        self._bootstrap_worker.progress.connect(self._on_bootstrap_progress)
        self._bootstrap_worker.finished.connect(self._on_bootstrap_finished)
        self._bootstrap_thread.start()

        # 模态显示进度对话框（不阻塞后台线程，因为 worker 在另一个线程）
        self._bootstrap_dialog.exec()

    def _on_bootstrap_progress(self, line: str):
        if hasattr(self, "_bootstrap_log") and self._bootstrap_log:
            self._bootstrap_log.appendPlainText(line)

    def _on_bootstrap_finished(self, ok: bool, summary: str):
        if hasattr(self, "_bootstrap_thread") and self._bootstrap_thread:
            self._bootstrap_thread.quit()
            self._bootstrap_thread.wait(3000)
        if hasattr(self, "_bootstrap_log") and self._bootstrap_log:
            self._bootstrap_log.appendPlainText("")
            self._bootstrap_log.appendPlainText("=" * 50)
            self._bootstrap_log.appendPlainText(summary)
        if hasattr(self, "_bootstrap_status_lbl") and self._bootstrap_status_lbl:
            self._bootstrap_status_lbl.setText("完成" if ok else "部分失败")
            self._bootstrap_status_lbl.setStyleSheet(
                "color: #2a6; font-weight: bold;" if ok
                else "color: #c63; font-weight: bold;"
            )
        if hasattr(self, "_bootstrap_close_btn") and self._bootstrap_close_btn:
            self._bootstrap_close_btn.setEnabled(True)

        # 刷新凭据/依赖状态，并重新加载 config（bootstrap 已写盘）
        self._load_config()
        self._refresh_credential_status()
        self._refresh_dependency_status()

        title = "部署完成" if ok else "部署完成（部分失败）"
        icon = QMessageBox.Information if ok else QMessageBox.Warning
        box = QMessageBox(self)
        box.setWindowTitle(title)
        box.setIcon(icon)
        box.setText(summary + "\n\n详见上方日志。应用已可直接使用，无需重启。")
        box.exec()

    @staticmethod
    def _gen_password(length: int) -> str:
        """生成随机密码（字母+数字）"""
        alphabet = string.ascii_letters + string.digits
        return "".join(secrets.choice(alphabet) for _ in range(length))

    def _on_save_credentials(self):
        saved = []
        for key, edit in self._cred_inputs.items():
            val = edit.text()
            if not val:
                continue
            try:
                self._cred_service.set(key, val)
                saved.append(key)
                edit.clear()
            except Exception as e:
                QMessageBox.critical(self, "失败", f"保存 {key} 失败: {e}")
                return
        self._refresh_credential_status()
        if saved:
            QMessageBox.information(self, "成功", f"已保存 {len(saved)} 项凭据。")
        else:
            QMessageBox.information(self, "提示", "未填写任何凭据。")

    def _on_delete_credentials(self):
        reply = QMessageBox.question(
            self, "确认", "将清空所有凭据（不可恢复），确认？",
            QMessageBox.Yes | QMessageBox.No, QMessageBox.No
        )
        if reply != QMessageBox.Yes:
            return
        for item in self._cred_service.list_items():
            try:
                self._cred_service.delete(item.key)
            except Exception as e:
                logger.warning(f"删除凭据 {item.key} 失败: {e}")
        self._refresh_credential_status()
        QMessageBox.information(self, "完成", "所有凭据已清空。")

    # ---------------------- 依赖管理 ----------------------
    def _build_dep_group(self) -> QGroupBox:
        group = QGroupBox("依赖管理")
        v = QVBoxLayout(group)

        # 核心依赖
        core_group = QGroupBox("核心依赖（必需）")
        core_grid = QGridLayout(core_group)
        core_grid.addWidget(QLabel("包名"), 0, 0)
        core_grid.addWidget(QLabel("状态"), 0, 1)
        self._core_labels: dict[str, QLabel] = {}
        row = 1
        for pkg in self._dep_service.get_core_status().keys():
            core_grid.addWidget(QLabel(pkg), row, 0)
            status_label = QLabel()
            self._core_labels[pkg] = status_label
            core_grid.addWidget(status_label, row, 1)
            row += 1
        v.addWidget(core_group)

        # 可选组件
        opt_group = QGroupBox("可选功能组件（勾选后点击安装/卸载）")
        opt_v = QVBoxLayout(opt_group)
        self._comp_checkboxes: dict[str, QCheckBox] = {}
        for comp in self._dep_service.list_components():
            cb = QCheckBox(f"{comp.name}  —  {comp.description}")
            cb.setToolTip("\n".join(comp.packages))
            self._comp_checkboxes[comp.key] = cb
            opt_v.addWidget(cb)

        btn_row = QHBoxLayout()
        self._install_btn = QPushButton("安装选中")
        self._install_btn.clicked.connect(lambda: self._start_install(True))
        self._uninstall_btn = QPushButton("卸载选中")
        self._uninstall_btn.clicked.connect(lambda: self._start_install(False))
        self._refresh_btn = QPushButton("刷新状态")
        self._refresh_btn.clicked.connect(self._refresh_dependency_status)
        btn_row.addWidget(self._install_btn)
        btn_row.addWidget(self._uninstall_btn)
        btn_row.addStretch()
        btn_row.addWidget(self._refresh_btn)
        opt_v.addLayout(btn_row)

        opt_v.addWidget(QLabel("输出："))
        self._dep_log = QPlainTextEdit()
        self._dep_log.setReadOnly(True)
        self._dep_log.setMaximumBlockCount(2000)
        self._dep_log.setMaximumHeight(180)
        opt_v.addWidget(self._dep_log)
        v.addWidget(opt_group)
        return group

    def _start_install(self, install: bool):
        keys = [k for k, cb in self._comp_checkboxes.items() if cb.isChecked()]
        if not keys:
            QMessageBox.information(self, "提示", "请先勾选至少一个组件")
            return
        if self._worker_host is not None:
            QMessageBox.information(self, "提示", "已有任务在执行中")
            return

        action = "安装" if install else "卸载"
        names = [c.name for c in self._dep_service.list_components() if c.key in keys]
        reply = QMessageBox.question(
            self, f"确认{action}",
            f"将{action}以下组件的依赖包：\n\n" + "\n".join(names) +
            "\n\n此操作可能需要几分钟，确认继续？",
            QMessageBox.Yes | QMessageBox.No, QMessageBox.No
        )
        if reply != QMessageBox.Yes:
            return

        self._dep_log.clear()
        self._dep_log.appendPlainText(f"[$开始] {action}：{', '.join(keys)}")
        self._set_dep_buttons_enabled(False)

        worker = self._dep_service.create_install_worker(keys, install=install)
        self._worker_host = _WorkerHost(worker)
        self._worker_host.progress.connect(self._on_dep_progress)
        self._worker_host.finished.connect(self._on_dep_finished)
        self._worker_host.start()

    def _set_dep_buttons_enabled(self, enabled: bool):
        self._install_btn.setEnabled(enabled)
        self._uninstall_btn.setEnabled(enabled)
        self._refresh_btn.setEnabled(enabled)

    def _on_dep_progress(self, line: str):
        self._dep_log.appendPlainText(line)

    def _on_dep_finished(self, ok: bool, msg: str):
        tag = "成功" if ok else "失败"
        self._dep_log.appendPlainText(f"[$结束] {tag}: {msg}")
        self._set_dep_buttons_enabled(True)
        self._worker_host = None
        self._refresh_dependency_status()
        if ok:
            QMessageBox.information(self, "完成", msg)
        else:
            QMessageBox.warning(self, "失败", msg + "\n详见输出日志。")

    # ---------------------- 方案选择 ----------------------
    def _build_scheme_group(self) -> QGroupBox:
        group = QGroupBox("方案选择")
        form = QFormLayout(group)

        self._vlm_combo = QComboBox()
        self._vlm_combo.addItem("A — PaddleOCR-VL（CPU 可运行）", "A")
        self._vlm_combo.addItem("B — MinerU 框架（vlm/pipeline）", "B")
        self._vlm_combo.addItem("C — MiniCPM-V 4.5（需 GPU）", "C")
        form.addRow("VLM 方案：", self._vlm_combo)

        self._embed_combo = QComboBox()
        self._embed_combo.addItem("A — BGE-M3（三模态）", "A")
        self._embed_combo.addItem("B — Qwen3-Embedding（纯 dense）", "B")
        form.addRow("Embedding 方案：", self._embed_combo)

        save_btn = QPushButton("保存到 config.yaml")
        save_btn.clicked.connect(self._on_save_scheme)
        form.addRow("", save_btn)

        self._scheme_status = QLabel()
        self._scheme_status.setWordWrap(True)
        form.addRow("状态：", self._scheme_status)
        return group

    def _on_save_scheme(self):
        vlm = self._vlm_combo.currentData()
        emb = self._embed_combo.currentData()
        try:
            import yaml
            if self._config is None:
                self._config = {}
            self._config.setdefault("vlm", {})["provider"] = vlm
            self._config.setdefault("embedding", {})["provider"] = emb
            with open(self._config_path, "w", encoding="utf-8") as f:
                yaml.safe_dump(self._config, f, allow_unicode=True, sort_keys=False)
            self._scheme_status.setText(
                f"已保存：VLM={vlm}，Embedding={emb}（需重启应用生效）"
            )
            QMessageBox.information(self, "成功", "方案已保存到 config.yaml，重启应用后生效。")
        except Exception as e:
            QMessageBox.critical(self, "失败", f"保存配置失败: {e}")

    # ---------------------- 数据加载 ----------------------
    def _load_config(self):
        import yaml
        try:
            with open(self._config_path, "r", encoding="utf-8") as f:
                self._config = yaml.safe_load(f) or {}
        except Exception as e:
            logger.error(f"加载 config.yaml 失败: {e}")
            self._config = {}

        # 方案回填
        vlm_provider = (self._config.get("vlm") or {}).get("provider", "A")
        embed_provider = (self._config.get("embedding") or {}).get("provider", "A")
        idx_vlm = self._vlm_combo.findData(vlm_provider)
        if idx_vlm >= 0:
            self._vlm_combo.setCurrentIndex(idx_vlm)
        idx_emb = self._embed_combo.findData(embed_provider)
        if idx_emb >= 0:
            self._embed_combo.setCurrentIndex(idx_emb)
        self._scheme_status.setText(
            f"当前配置：VLM={vlm_provider}，Embedding={embed_provider}"
        )

    def _refresh_dependency_status(self):
        core_status = self._dep_service.get_core_status()
        for pkg, ok in core_status.items():
            lbl = self._core_labels.get(pkg)
            if lbl is None:
                continue
            lbl.setText("已安装" if ok else "未安装")
            lbl.setStyleSheet("color: green;" if ok else "color: red;")
        opt_status = self._dep_service.get_status()
        for key, cb in self._comp_checkboxes.items():
            ok = opt_status.get(key, False)
            text = cb.text()
            base = text.split("  [")[0]
            cb.setText(f"{base}  [{'已安装' if ok else '未安装'}]")

    def _refresh_credential_status(self):
        status = self._cred_service.get_status()
        for key, lbl in self._cred_status_labels.items():
            ok = status.get(key, False)
            lbl.setText("已设置" if ok else "未设置")
            lbl.setStyleSheet("color: green;" if ok else "color: red;")


# ============================================================
# 数据迁移 Worker
# ============================================================
class _DataMigrateWorker(QObject):
    finished = Signal(bool, str)

    def __init__(self, new_root: str):
        super().__init__()
        self.new_root = new_root

    def run(self):
        from utils.paths import migrate_data_root
        ok, msg = migrate_data_root(self.new_root)
        self.finished.emit(ok, msg)


# ============================================================
# 一键部署 Bootstrap Worker — 后台执行 bootstrap.run() 并转发日志
# ============================================================
class _SignalLogHandler(logging.Handler):
    """将 logging 记录通过 Qt Signal 转发到主线程"""

    def __init__(self, signal):
        super().__init__()
        self._signal = signal

    def emit(self, record):  # noqa: A003 - logging.Handler API
        try:
            self._signal.emit(self.format(record))
        except Exception:
            pass


class _BootstrapWorker(QObject):
    """后台执行 bootstrap.Bootstrap.run()，实时转发日志"""

    progress = Signal(str)
    finished = Signal(bool, str)

    def __init__(self, bootstrap_cls, config_path: str):
        super().__init__()
        self._bootstrap_cls = bootstrap_cls
        self._config_path = config_path

    def run(self):
        # 安装 Signal 日志 handler，捕获 bootstrap 及其调用的子模块日志
        handler = _SignalLogHandler(self.progress)
        handler.setFormatter(logging.Formatter("%(asctime)s [%(levelname)s] %(message)s"))
        targets = [
            logging.getLogger("scripts.bootstrap"),
            logging.getLogger("scripts.init_db"),
            logging.getLogger("utils.credentials"),
            logging.getLogger(),  # root，兜底
        ]
        for lg in targets:
            lg.addHandler(handler)

        try:
            b = self._bootstrap_cls(config_path=self._config_path)
            ok = b.run()
            if ok:
                summary = (
                    "一键部署完成：PostgreSQL / Qdrant / MinIO 均已就绪，"
                    "数据库表结构已初始化，凭据已写入 keyring，config.yaml 已回写。"
                )
            else:
                summary = (
                    "部署流程已执行，但部分服务未完全就绪。\n"
                    "请查看日志中的 [ERROR] / [WARNING] 行确定失败项。\n"
                    "PostgreSQL 或 Qdrant 失败时应用核心功能不可用；"
                    "MinIO 失败会自动回退到本地文件存储。"
                )
            self.finished.emit(ok, summary)
        except Exception as e:
            logger.error(f"Bootstrap 执行异常: {e}", exc_info=True)
            self.finished.emit(False, f"引导异常: {e}")
        finally:
            for lg in targets:
                lg.removeHandler(handler)


# ============================================================
# LLM 连接测试 Worker
# ============================================================
class _LLMTestWorker(QObject):
    finished = Signal(bool, str)

    def __init__(self, api_base: str, api_key: str, model: str):
        super().__init__()
        self.api_base = api_base
        self.api_key = api_key
        self.model = model

    def run(self):
        try:
            from openai import OpenAI
            client = OpenAI(base_url=self.api_base, api_key=self.api_key, timeout=15)
            resp = client.chat.completions.create(
                model=self.model,
                messages=[{"role": "user", "content": "ping"}],
                max_tokens=5,
            )
            content = resp.choices[0].message.content or ""
            self.finished.emit(
                True,
                f"连接成功！模型响应：{content[:50]}"
            )
        except Exception as e:
            self.finished.emit(False, f"连接失败：{e}")


# ============================================================
# 对话框包装（保留向后兼容，但内部嵌入 SettingsPage）
# ============================================================
from PySide6.QtWidgets import QDialog  # noqa: E402


class SettingsDialog(QDialog):
    """设置对话框（兼容旧调用，内部嵌入 SettingsPage）"""

    def __init__(self, parent=None, config_path: str = "config.yaml"):
        super().__init__(parent)
        self.setWindowTitle("设置")
        self.resize(760, 720)
        layout = QVBoxLayout(self)
        self.page = SettingsPage(self, config_path=config_path)
        layout.addWidget(self.page)
        close_btn = QPushButton("关闭")
        close_btn.clicked.connect(self.accept)
        layout.addWidget(close_btn)
