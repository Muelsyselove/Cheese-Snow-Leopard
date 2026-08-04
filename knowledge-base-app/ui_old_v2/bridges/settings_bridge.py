"""设置页桥接层 — 模型/默认模型/凭据/依赖/方案/一键部署/数据位置

复刻旧 SettingsPage 的全部功能，QMessageBox 交互改为信号驱动
（确认框/结果提示由 QML 层负责呈现）。
"""
from __future__ import annotations

import logging
import os

from PySide6.QtCore import QObject, QThread, Property, Signal, Slot

from services.dependency_service import DependencyService
from services.credential_service import CredentialService
from services.model_config_service import ModelConfigService, DEFAULT_ROLES
from presets.llm_providers import get_provider

logger = logging.getLogger(__name__)


# ============================================================
# 后台 Worker（与旧实现一致，信号协议不变）
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
            client = OpenAI(base_url=self.api_base, api_key=self.api_key,
                            timeout=15)
            resp = client.chat.completions.create(
                model=self.model,
                messages=[{"role": "user", "content": "ping"}],
                max_tokens=5,
            )
            content = resp.choices[0].message.content or ""
            self.finished.emit(True, f"OK: {content[:50]}")
        except Exception as e:
            self.finished.emit(False, str(e))


class _DataMigrateWorker(QObject):
    finished = Signal(bool, str)

    def __init__(self, new_root: str):
        super().__init__()
        self.new_root = new_root

    def run(self):
        from utils.paths import migrate_data_root
        ok, msg = migrate_data_root(self.new_root)
        self.finished.emit(ok, msg)


class _BootstrapWorker(QObject):
    """后台执行 bootstrap.Bootstrap.run()，实时转发日志"""
    progress = Signal(str)
    finished = Signal(bool, str)

    def __init__(self, bootstrap_cls, config_path: str):
        super().__init__()
        self._bootstrap_cls = bootstrap_cls
        self._config_path = config_path

    def run(self):
        handler = _SignalLogHandler(self.progress)
        handler.setFormatter(
            logging.Formatter("%(asctime)s [%(levelname)s] %(message)s"))
        targets = [
            logging.getLogger("scripts.bootstrap"),
            logging.getLogger("scripts.init_db"),
            logging.getLogger("utils.credentials"),
            logging.getLogger(),
        ]
        for lg in targets:
            lg.addHandler(handler)
        try:
            b = self._bootstrap_cls(config_path=self._config_path)
            ok = b.run()
            self.finished.emit(ok, "")
        except Exception as e:
            logger.error(f"Bootstrap 执行异常: {e}", exc_info=True)
            self.finished.emit(False, str(e))
        finally:
            for lg in targets:
                lg.removeHandler(handler)


class _DepWorkerHost(QObject):
    """依赖安装 Worker 的 QThread 宿主"""
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
# 设置桥接
# ============================================================
class SettingsBridge(QObject):
    """设置页桥接（context property: settingsBridge）"""

    providersChanged = Signal()
    defaultsChanged = Signal()
    credentialsChanged = Signal()
    dependenciesChanged = Signal()
    schemeChanged = Signal()
    computeChanged = Signal()
    dataRootChanged = Signal()

    testConnectionResult = Signal(bool, str)
    depLogAppended = Signal(str)
    depFinished = Signal(bool, str)
    depRunningChanged = Signal()
    bootstrapLogAppended = Signal(str)
    bootstrapFinished = Signal(bool, str)
    bootstrapRunningChanged = Signal()
    migrateFinished = Signal(bool, str)
    migrateRunningChanged = Signal()

    infoMessage = Signal(str)
    errorMessage = Signal(str)
    statusMessage = Signal(str)

    def __init__(self, model_config_service: ModelConfigService | None = None,
                 config_path: str = "config.yaml", i18n=None, parent=None):
        super().__init__(parent)
        self._model_svc = model_config_service or ModelConfigService()
        self._cred_service = CredentialService()
        self._dep_service = DependencyService()
        self._config_path = config_path
        self._i18n = i18n
        self._config: dict | None = None

        # 后台任务引用
        self._test_thread = None
        self._test_worker = None
        self._dep_host = None
        self._dep_running = False
        self._bootstrap_thread = None
        self._bootstrap_worker = None
        self._bootstrap_running = False
        self._migrate_thread = None
        self._migrate_worker = None
        self._migrate_running = False

        self._load_config()

    def _tr(self, key: str, **params) -> str:
        if self._i18n is None:
            return key
        return self._i18n.trf(key, params) if params else self._i18n.tr(key)

    def _load_config(self):
        import yaml
        try:
            with open(self._config_path, "r", encoding="utf-8") as f:
                self._config = yaml.safe_load(f) or {}
        except Exception as e:
            logger.error(f"加载 config.yaml 失败: {e}")
            self._config = {}

    # ======================================================== 模型配置
    @Property("QVariantList", notify=providersChanged)
    def providers(self) -> list[dict]:
        result = []
        for preset, pc in self._model_svc.list_providers():
            model_display = {m.model_name: m.display_name for m in preset.models}
            result.append({
                "key": preset.key,
                "displayName": preset.display_name,
                "apiBase": preset.api_base,
                "docUrl": preset.doc_url,
                "keyApplyUrl": preset.key_apply_url,
                "configured": pc.configured,
                "apiKey": pc.api_key or "",
                "models": [
                    {"modelName": mc.model_name,
                     "displayName": model_display.get(mc.model_name, mc.model_name),
                     "enabled": mc.enabled}
                    for mc in pc.models
                ],
            })
        return result

    @Slot(str, str)
    def saveApiKey(self, provider_key: str, api_key: str):
        api_key = (api_key or "").strip()
        if not api_key:
            self.infoMessage.emit(self._tr("settings.fillApiKey"))
            return
        try:
            self._model_svc.set_api_key(provider_key, api_key)
            self._model_svc.sync_default_to_config(self._config_path)
            self.providersChanged.emit()
            self.infoMessage.emit(self._tr("settings.apiKeySaved"))
        except Exception as e:
            self.errorMessage.emit(self._tr("settings.saveFailed", msg=e))

    @Slot(str)
    def clearApiKey(self, provider_key: str):
        try:
            self._model_svc.clear_api_key(provider_key)
            self.providersChanged.emit()
            self.infoMessage.emit(self._tr("settings.apiKeyCleared"))
        except Exception as e:
            self.errorMessage.emit(self._tr("settings.clearFailed", msg=e))

    @Slot(str, "QVariantMap")
    def saveModelStates(self, provider_key: str, states: dict):
        """批量保存模型启用状态 {model_name: enabled}"""
        try:
            for model_name, enabled in (states or {}).items():
                self._model_svc.set_model_enabled(
                    provider_key, model_name, bool(enabled))
            self._model_svc.sync_default_to_config(self._config_path)
            self.providersChanged.emit()
            self.infoMessage.emit(self._tr("settings.modelStatesSaved"))
        except Exception as e:
            self.errorMessage.emit(self._tr("settings.saveFailed", msg=e))

    @Slot(str, str)
    def testConnection(self, provider_key: str, api_key_from_field: str):
        provider = get_provider(provider_key)
        if provider is None:
            return
        api_key = (api_key_from_field or "").strip() or \
            self._model_svc.get_api_key(provider_key)
        if not api_key:
            self.infoMessage.emit(self._tr("settings.fillApiKey"))
            return
        pc = self._model_svc.get_provider_config(provider_key)
        model_name = ""
        if pc:
            for mc in pc.models:
                if mc.enabled:
                    model_name = mc.model_name
                    break
            if not model_name and pc.models:
                model_name = pc.models[0].model_name
        if not model_name:
            self.infoMessage.emit(self._tr("settings.noModelAvailable"))
            return
        self.statusMessage.emit(self._tr("settings.testing"))
        self._test_thread = QThread()
        self._test_worker = _LLMTestWorker(provider.api_base, api_key, model_name)
        self._test_worker.moveToThread(self._test_thread)
        self._test_thread.started.connect(self._test_worker.run)
        self._test_worker.finished.connect(self._on_test_done)
        self._test_thread.start()

    def _on_test_done(self, ok: bool, msg: str):
        if self._test_thread:
            self._test_thread.quit()
            self._test_thread.wait(2000)
        self._test_thread = None
        self._test_worker = None
        self.testConnectionResult.emit(ok, msg)

    @Slot(str)
    def openKeyApplyUrl(self, provider_key: str):
        provider = get_provider(provider_key)
        if provider is None:
            return
        from PySide6.QtGui import QDesktopServices
        from PySide6.QtCore import QUrl
        QDesktopServices.openUrl(QUrl(provider.key_apply_url))

    # ======================================================== 默认模型
    @Property("QVariantList", notify=defaultsChanged)
    def defaultRoles(self) -> list[dict]:
        """[{role, roleKey, providerKey, modelName}]（providerKey 为空表示自动）"""
        defaults = self._model_svc.get_default_models()
        result = []
        for role in DEFAULT_ROLES:
            ref = defaults.get(role)
            result.append({
                "role": role,
                "roleKey": f"settings.role.{role}",
                "providerKey": ref[0] if ref else "",
                "modelName": ref[1] if ref else "",
            })
        return result

    @Property("QVariantList", notify=providersChanged)
    def enabledModels(self) -> list[dict]:
        return [
            {"providerKey": pk, "providerName": pn,
             "modelName": mn, "displayName": md,
             "label": f"[{pn}] {md}"}
            for pk, pn, mn, md in self._model_svc.list_enabled_models()
        ]

    @Slot(str, str, str)
    def setDefaultModel(self, role: str, provider_key: str, model_name: str):
        try:
            self._model_svc.set_default_model(role, provider_key, model_name)
            self.defaultsChanged.emit()
        except Exception as e:
            self.errorMessage.emit(self._tr("settings.defaultsSaveFailed", msg=e))

    @Slot()
    def notifyDefaultsSaved(self):
        self.infoMessage.emit(self._tr("settings.defaultsSaved"))

    # ======================================================== 数据位置
    @Property(bool, notify=migrateRunningChanged)
    def migrateRunning(self) -> bool:
        return self._migrate_running

    @Property(str, notify=dataRootChanged)
    def dataRoot(self) -> str:
        try:
            from utils.paths import get_data_root
            return get_data_root()
        except Exception:
            from utils.paths import DEFAULT_DATA_ROOT
            return DEFAULT_DATA_ROOT

    @Slot(result=str)
    def pickDataDirectory(self) -> str:
        """弹出目录选择框，返回所选目录（取消返回空串）"""
        from PySide6.QtWidgets import QFileDialog
        new_dir = QFileDialog.getExistingDirectory(
            None, self._tr("settings.chooseLocation"), self.dataRoot)
        return os.path.abspath(new_dir) if new_dir else ""

    @Slot(str)
    def migrateData(self, new_dir: str):
        """后台迁移数据目录（确认框由 QML 负责）"""
        if self._migrate_running:
            return
        if os.path.abspath(new_dir) == os.path.abspath(self.dataRoot):
            self.infoMessage.emit(self._tr("settings.sameLocation"))
            return
        self._migrate_thread = QThread()
        self._migrate_worker = _DataMigrateWorker(new_dir)
        self._migrate_worker.moveToThread(self._migrate_thread)
        self._migrate_thread.started.connect(self._migrate_worker.run)
        self._migrate_worker.finished.connect(self._on_migrate_done)
        self._migrate_running = True
        self.migrateRunningChanged.emit()
        self._migrate_thread.start()
        self.statusMessage.emit(self._tr("settings.migrating"))

    def _on_migrate_done(self, ok: bool, msg: str):
        if self._migrate_thread:
            self._migrate_thread.quit()
            self._migrate_thread.wait(2000)
        self._migrate_thread = None
        self._migrate_worker = None
        self._migrate_running = False
        self.migrateRunningChanged.emit()
        if ok:
            try:
                import yaml
                from utils.paths import get_data_root
                if self._config is None:
                    self._config = {}
                self._config.setdefault("paths", {})
                self._config["paths"]["data_root"] = get_data_root()
                with open(self._config_path, "w", encoding="utf-8") as f:
                    yaml.safe_dump(self._config, f, allow_unicode=True,
                                   sort_keys=False)
                self.dataRootChanged.emit()
            except Exception as e:
                logger.error(f"更新 config.yaml 失败: {e}")
        self.migrateFinished.emit(ok, msg)

    # ======================================================== 凭据
    @Property("QVariantList", notify=credentialsChanged)
    def credentials(self) -> list[dict]:
        status = self._cred_service.get_status()
        return [
            {"key": item.key, "name": item.name,
             "description": item.description,
             "placeholder": item.placeholder or item.name,
             "isSet": status.get(item.key, False)}
            for item in self._cred_service.list_items()
        ]

    @Slot("QVariantMap")
    def saveCredentials(self, values: dict):
        saved = 0
        for key, val in (values or {}).items():
            if not val:
                continue
            try:
                self._cred_service.set(key, val)
                saved += 1
            except Exception as e:
                self.errorMessage.emit(
                    self._tr("settings.credentialSaveFailed", key=key, msg=e))
                return
        self.credentialsChanged.emit()
        if saved:
            self.infoMessage.emit(
                self._tr("settings.credentialsSaved", count=saved))
        else:
            self.infoMessage.emit(self._tr("settings.noCredentialFilled"))

    @Slot()
    def clearAllCredentials(self):
        for item in self._cred_service.list_items():
            try:
                self._cred_service.delete(item.key)
            except Exception as e:
                logger.warning(f"删除凭据 {item.key} 失败: {e}")
        self.credentialsChanged.emit()
        self.infoMessage.emit(self._tr("settings.credentialsCleared"))

    # ======================================================== 一键部署
    @Property(bool, notify=bootstrapRunningChanged)
    def bootstrapRunning(self) -> bool:
        return self._bootstrap_running

    @Slot()
    def runBootstrap(self):
        """后台执行一键部署（确认框由 QML 负责），日志实时转发"""
        if self._bootstrap_running:
            self.infoMessage.emit(self._tr("settings.bootstrapRunning"))
            return
        from scripts.bootstrap import Bootstrap
        self._bootstrap_thread = QThread()
        self._bootstrap_worker = _BootstrapWorker(Bootstrap, self._config_path)
        self._bootstrap_worker.moveToThread(self._bootstrap_thread)
        self._bootstrap_thread.started.connect(self._bootstrap_worker.run)
        self._bootstrap_worker.progress.connect(self.bootstrapLogAppended)
        self._bootstrap_worker.finished.connect(self._on_bootstrap_finished)
        self._bootstrap_running = True
        self.bootstrapRunningChanged.emit()
        self._bootstrap_thread.start()

    def _on_bootstrap_finished(self, ok: bool, err: str):
        if self._bootstrap_thread:
            self._bootstrap_thread.quit()
            self._bootstrap_thread.wait(3000)
        self._bootstrap_thread = None
        self._bootstrap_worker = None
        self._bootstrap_running = False
        self.bootstrapRunningChanged.emit()
        # 部署后刷新状态（与旧实现一致）
        self._load_config()
        self.credentialsChanged.emit()
        self.dependenciesChanged.emit()
        self.schemeChanged.emit()
        self.bootstrapFinished.emit(ok, err)

    # ======================================================== 依赖管理
    @Property("QVariantList", notify=dependenciesChanged)
    def coreDependencies(self) -> list[dict]:
        return [{"name": pkg, "installed": ok}
                for pkg, ok in self._dep_service.get_core_status().items()]

    @Property("QVariantList", notify=dependenciesChanged)
    def optionalComponents(self) -> list[dict]:
        status = self._dep_service.get_status()
        return [
            {"key": c.key, "name": c.name, "description": c.description,
             "packages": list(c.packages), "installed": status.get(c.key, False)}
            for c in self._dep_service.list_components()
        ]

    @Property(bool, notify=depRunningChanged)
    def depRunning(self) -> bool:
        return self._dep_running

    @Slot()
    def refreshDependencies(self):
        self.dependenciesChanged.emit()

    @Slot(list, bool)
    def runDependencyTask(self, component_keys: list, install: bool):
        """安装/卸载选中组件（确认框由 QML 负责）"""
        keys = [str(k) for k in (component_keys or [])]
        if not keys:
            self.infoMessage.emit(self._tr("settings.selectComponentFirst"))
            return
        if self._dep_running:
            self.infoMessage.emit(self._tr("settings.taskRunning"))
            return
        worker = self._dep_service.create_install_worker(keys, install=install)
        self._dep_host = _DepWorkerHost(worker)
        self._dep_host.progress.connect(self.depLogAppended)
        self._dep_host.finished.connect(self._on_dep_finished)
        self._dep_running = True
        self.depRunningChanged.emit()
        self._dep_host.start()

    def _on_dep_finished(self, ok: bool, msg: str):
        self._dep_running = False
        self.depRunningChanged.emit()
        self._dep_host = None
        self.dependenciesChanged.emit()
        self.depFinished.emit(ok, msg)

    # ======================================================== 方案选择
    @Property(str, notify=schemeChanged)
    def vlmScheme(self) -> str:
        return (self._config or {}).get("vlm", {}).get("provider", "A")

    @Property(str, notify=schemeChanged)
    def embedScheme(self) -> str:
        return (self._config or {}).get("embedding", {}).get("provider", "A")

    @Slot(str, str)
    def saveScheme(self, vlm: str, emb: str):
        try:
            import yaml
            if self._config is None:
                self._config = {}
            self._config.setdefault("vlm", {})["provider"] = vlm
            self._config.setdefault("embedding", {})["provider"] = emb
            with open(self._config_path, "w", encoding="utf-8") as f:
                yaml.safe_dump(self._config, f, allow_unicode=True,
                               sort_keys=False)
            self.schemeChanged.emit()
            self.infoMessage.emit(self._tr("settings.scheme.savedToast"))
        except Exception as e:
            self.errorMessage.emit(self._tr("settings.scheme.saveFailed", msg=e))

    # ======================================================== 计算设备（GPU）
    @Property(list, notify=computeChanged)
    def computeOptions(self) -> list:
        """可选设备：auto / 各 GPU / cpu。label 已本地化。"""
        from services.gpu_service import detect_gpus, strongest_gpu
        options: list[dict] = []
        gpus = detect_gpus()
        best = strongest_gpu(gpus)
        if best is not None:
            options.append({
                "value": "auto",
                "label": self._tr("settings.compute.autoWith",
                                  name=best.name),
            })
        else:
            options.append({
                "value": "auto",
                "label": self._tr("settings.compute.autoNoGpu"),
            })
        for g in gpus:
            options.append({
                "value": f"cuda:{g.index}",
                "label": f"GPU {g.index} · {g.name} · {g.vram_mb // 1024} GB",
            })
        options.append({
            "value": "cpu",
            "label": self._tr("settings.compute.cpuOnly"),
        })
        return options

    @Property(str, notify=computeChanged)
    def computeDevice(self) -> str:
        return ((self._config or {}).get("compute") or {}).get("device", "auto")

    @Property(str, notify=computeChanged)
    def computeActiveDesc(self) -> str:
        """当前进程实际生效的设备描述"""
        import os
        vis = os.environ.get("CUDA_VISIBLE_DEVICES")
        if vis == "":
            return "CPU"
        if vis:
            return f"GPU {vis}"
        return self._tr("settings.compute.activeDefault")

    @Slot(str)
    def setComputeDevice(self, device: str):
        device = (device or "auto").strip()
        try:
            import yaml
            if self._config is None:
                self._config = {}
            self._config.setdefault("compute", {})["device"] = device
            with open(self._config_path, "w", encoding="utf-8") as f:
                yaml.safe_dump(self._config, f, allow_unicode=True,
                               sort_keys=False)
            self.computeChanged.emit()
            self.infoMessage.emit(self._tr("settings.compute.savedToast"))
        except Exception as e:
            self.errorMessage.emit(self._tr("settings.compute.saveFailed", msg=e))
