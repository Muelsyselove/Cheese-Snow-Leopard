"""对象存储接口 — 原始文件持久化层。

技术文档 4.1 三层存储：
- 原始文件层：MinIO（S3 兼容），按 bucket + 路径组织
- 元数据索引层：PostgreSQL
- 向量索引层：Qdrant

轻量方案（技术文档 9.4）：本地文件系统替代 MinIO，签名一致。
本接口同时被 MinioRepository 与 LocalFSAdapter 实现，业务层（file_service /
compensation）仅依赖 ObjectStorage Protocol，不感知具体后端。
"""
from __future__ import annotations

from typing import Protocol


class ObjectStorage(Protocol):
    """对象存储接口 — 原始文件的上传/下载/删除/存在性。

    契约：
    - upload 将本地文件持久化到对象存储，返回逻辑路径（存入 document_index.file_path）
    - 路径组织建议：{doc_id}/{file_name}，避免重名覆盖；具体策略由实现决定
    - 幂等性：同一文件重复上传应返回同一路径（按 content_hash 去重可选）
    - delete 按 upload 返回的逻辑路径删除；不存在视为成功（幂等）
    """

    def upload(self, local_path: str, object_key: str = "") -> str:
        """上传本地文件到对象存储。

        Args:
            local_path: 本地文件路径
            object_key: 可选的对象键（相对 bucket 的路径）；
                        为空时由实现自动生成（推荐 {uuid}/{file_name}）

        Returns:
            对象存储逻辑路径（file_path，存入 document_index）

        Raises:
            StorageError: 上传失败
        """
        ...

    def download(self, object_key: str, local_path: str) -> str:
        """下载对象到本地文件。

        Args:
            object_key: upload 返回的逻辑路径
            local_path: 本地目标路径

        Returns:
            本地文件路径（同 local_path）

        Raises:
            StorageError: 下载失败（含对象不存在）
        """
        ...

    def delete(self, object_key: str) -> None:
        """删除对象。对象不存在视为成功（幂等）。

        Args:
            object_key: upload 返回的逻辑路径

        Raises:
            StorageError: 删除失败（非"不存在"的其他错误）
        """
        ...

    def exists(self, object_key: str) -> bool:
        """检查对象是否存在。

        Args:
            object_key: upload 返回的逻辑路径

        Returns:
            True=存在 / False=不存在
        """
        ...
