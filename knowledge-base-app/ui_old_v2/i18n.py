"""多语言服务 — JSON 词典驱动，QML 侧通过 i18n.tr(key) 绑定

- 词典文件：ui/i18n/zh_CN.json、ui/i18n/en_US.json（key → 文案）
- 当前语言持久化到 config.yaml 的 ui.language 字段
- 语言切换发出 languageChanged 信号，QML 全部文本绑定即时刷新
- 占位符：tr("files.imported", count=3) → "已导入 3 个文档"
"""
from __future__ import annotations

import json
import logging
import os

from PySide6.QtCore import QObject, Property, Signal, Slot

logger = logging.getLogger(__name__)

I18N_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "i18n")

# 支持的语言：code → (词典文件名, 显示名)
LANGUAGES: dict[str, str] = {
    "zh_CN": "简体中文",
    "en_US": "English",
}
DEFAULT_LANGUAGE = "zh_CN"


class I18nService(QObject):
    """多语言服务（暴露给 QML 的 context property: i18n）"""

    languageChanged = Signal()

    def __init__(self, config_path: str = "config.yaml", parent=None):
        super().__init__(parent)
        self._config_path = config_path
        self._dicts: dict[str, dict[str, str]] = {}
        self._load_dicts()
        self._language = self._load_saved_language()
        if self._language not in LANGUAGES:
            self._language = DEFAULT_LANGUAGE

    # ---------------------------------------------------------- 词典加载
    def _load_dicts(self):
        for code in LANGUAGES:
            path = os.path.join(I18N_DIR, f"{code}.json")
            try:
                with open(path, "r", encoding="utf-8") as f:
                    self._dicts[code] = json.load(f)
            except Exception as e:
                logger.error(f"加载语言包失败 {path}: {e}")
                self._dicts[code] = {}

    def _load_saved_language(self) -> str:
        try:
            import yaml
            with open(self._config_path, "r", encoding="utf-8") as f:
                cfg = yaml.safe_load(f) or {}
            return (cfg.get("ui") or {}).get("language", DEFAULT_LANGUAGE)
        except Exception:
            return DEFAULT_LANGUAGE

    def _save_language(self, code: str):
        try:
            import yaml
            try:
                with open(self._config_path, "r", encoding="utf-8") as f:
                    cfg = yaml.safe_load(f) or {}
            except FileNotFoundError:
                cfg = {}
            cfg.setdefault("ui", {})["language"] = code
            with open(self._config_path, "w", encoding="utf-8") as f:
                yaml.safe_dump(cfg, f, allow_unicode=True, sort_keys=False)
        except Exception as e:
            logger.error(f"保存语言设置失败: {e}")

    # ---------------------------------------------------------- QML 接口
    def _get_language(self) -> str:
        return self._language

    def _set_language(self, code: str):
        if code not in LANGUAGES or code == self._language:
            return
        self._language = code
        self._save_language(code)
        self.languageChanged.emit()

    language = Property(str, _get_language, _set_language, notify=languageChanged)

    @Property("QVariantList", constant=True)
    def availableLanguages(self) -> list[dict]:
        return [{"code": code, "name": name} for code, name in LANGUAGES.items()]

    @Slot(str, result=str)
    def tr(self, key: str) -> str:
        """翻译 key；缺失时回退默认语言，再回退 key 本身"""
        text = self._dicts.get(self._language, {}).get(key)
        if text is None:
            text = self._dicts.get(DEFAULT_LANGUAGE, {}).get(key, key)
        return text

    @Slot(str, "QVariantMap", result=str)
    def trf(self, key: str, params: dict) -> str:
        """带占位符翻译：trf("files.imported", {"count": 3})"""
        text = self.tr(key)
        try:
            for k, v in (params or {}).items():
                text = text.replace("{" + str(k) + "}", str(v))
        except Exception:
            pass
        return text
