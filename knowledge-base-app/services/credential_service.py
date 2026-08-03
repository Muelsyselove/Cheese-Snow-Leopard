"""凭据服务 — 封装 keyring 读写，供设置界面使用

对 utils/credentials.py 的薄封装，提供凭据项元信息（key、显示名、描述）
统一管理，UI 层不直接接触 keyring。
"""
from __future__ import annotations

from dataclasses import dataclass

from utils.credentials import (
    get_credential, set_credential, delete_credential,
)


@dataclass
class CredentialItem:
    """一个凭据项的元信息"""
    key: str            # keyring 中的 key
    name: str           # 显示名称
    description: str    # 用途说明
    placeholder: str = ""


# 应用所需凭据清单（与 config.yaml 中的 keyring:xxx 占位符对齐）
# 注：LLM API Key 由模型配置页统一管理，不在此处重复
CREDENTIAL_ITEMS: list[CredentialItem] = [
    CredentialItem(
        key="pg_password",
        name="PostgreSQL 密码",
        description="元数据库密码（config.yaml: storage.postgres.password_env）",
        placeholder="",
    ),
    CredentialItem(
        key="minio_secret_key",
        name="MinIO Secret Key",
        description="对象存储密钥（config.yaml: storage.minio.secret_key_env）",
        placeholder="",
    ),
]


class CredentialService:
    """凭据管理服务 — UI 层调用接口"""

    def list_items(self) -> list[CredentialItem]:
        return CREDENTIAL_ITEMS

    def is_set(self, key: str) -> bool:
        return get_credential(key) is not None

    def get_status(self) -> dict[str, bool]:
        """返回所有凭据项的设置状态 {key: is_set}"""
        return {item.key: self.is_set(item.key) for item in CREDENTIAL_ITEMS}

    def set(self, key: str, value: str) -> None:
        if not value:
            raise ValueError("凭据值不能为空")
        set_credential(key, value)

    def delete(self, key: str) -> None:
        delete_credential(key)
