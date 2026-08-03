"""凭据安全存储（基于 keyring 库）

敏感凭据（LLM API Key、PostgreSQL 密码、MinIO Secret Key）不存入 config.yaml 明文，
统一走操作系统级 keyring 服务（macOS Keychain / Windows Credential Manager / Linux Secret Service）。
"""
from __future__ import annotations

import keyring

SERVICE_NAME = "knowledge-base-app"


def get_credential(key: str) -> str:
    """从系统 keyring 读取凭据。

    Args:
        key: keyring 中的凭据名（如 llm_api_key、pg_password、minio_secret_key）
    Returns:
        凭据值，未设置时返回 None
    """
    return keyring.get_password(SERVICE_NAME, key)


def set_credential(key: str, value: str) -> None:
    """用户在设置界面输入凭据时写入 keyring"""
    keyring.set_password(SERVICE_NAME, key, value)


def delete_credential(key: str) -> None:
    """删除凭据"""
    try:
        keyring.delete_password(SERVICE_NAME, key)
    except keyring.errors.PasswordDeleteError:
        pass


def resolve_credential_placeholder(value):
    """解析 config.yaml 中的 keyring:xxx 占位符。

    config.yaml 中敏感字段格式为 "keyring:<key_name>"，加载时替换为真实值。
    非 keyring 占位符的值原样返回。

    Args:
        value: config.yaml 中的字段值（可能是字符串占位符或普通值）
    Returns:
        解析后的真实凭据值
    Raises:
        ValueError: 占位符指向的凭据未在 keyring 中设置
    """
    if isinstance(value, str) and value.startswith("keyring:"):
        key_name = value.removeprefix("keyring:")
        cred = get_credential(key_name)
        if cred is None:
            raise ValueError(
                f"凭据 {key_name} 未在 keyring 中设置，请在设置界面录入"
            )
        return cred
    return value
