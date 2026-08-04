"""凭据存储 — 程序目录内本地文件

敏感凭据（LLM API Key、PostgreSQL 密码、MinIO Secret Key）统一保存在程序目录下的
credentials.json 中，便于随程序目录整体迁移（直接复制程序目录即可，不依赖操作系统
keyring 服务，换机/迁移后凭据不丢失）。

对外接口与原先 keyring 版保持一致：get_credential / set_credential /
delete_credential / resolve_credential_placeholder。
"""
from __future__ import annotations

import json
import logging
import os
import threading

logger = logging.getLogger(__name__)

# 程序根目录（utils/ 的上一级，即 main.py 所在目录）
APP_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
CREDENTIALS_FILE = os.path.join(APP_ROOT, "credentials.json")

_lock = threading.Lock()


def _load() -> dict:
    """读取本地凭据文件"""
    if not os.path.isfile(CREDENTIALS_FILE):
        return {}
    try:
        with open(CREDENTIALS_FILE, "r", encoding="utf-8") as f:
            data = json.load(f)
        return data if isinstance(data, dict) else {}
    except Exception as e:
        logger.warning(f"读取凭据文件失败: {e}")
        return {}


def _save(data: dict) -> None:
    """原子写入本地凭据文件（先写临时文件再替换，避免写一半损坏）"""
    with _lock:
        os.makedirs(os.path.dirname(CREDENTIALS_FILE), exist_ok=True)
        tmp = CREDENTIALS_FILE + ".tmp"
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
        os.replace(tmp, CREDENTIALS_FILE)


def get_credential(key: str) -> str:
    """从本地凭据文件读取凭据，未设置时返回 None"""
    return _load().get(key)


def set_credential(key: str, value: str) -> None:
    """写入凭据到本地文件"""
    data = _load()
    data[key] = value
    _save(data)


def delete_credential(key: str) -> None:
    """删除凭据"""
    data = _load()
    if key in data:
        del data[key]
        _save(data)


def resolve_credential_placeholder(value):
    """解析 config.yaml 中的 keyring:xxx 占位符。

    保留 keyring: 前缀占位符以兼容现有 config.yaml / providers.yaml 配置，
    实际值从程序目录内的本地凭据文件读取。

    Args:
        value: config.yaml 中的字段值（可能是字符串占位符或普通值）
    Returns:
        解析后的真实凭据值
    Raises:
        ValueError: 占位符指向的凭据未设置
    """
    if isinstance(value, str) and value.startswith("keyring:"):
        key_name = value.removeprefix("keyring:")
        cred = get_credential(key_name)
        if cred is None:
            raise ValueError(
                f"凭据 {key_name} 未设置，请在设置界面录入"
            )
        return cred
    return value