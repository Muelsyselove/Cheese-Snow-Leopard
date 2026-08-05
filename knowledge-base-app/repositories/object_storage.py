"""对象存储仓库实现 — MinIO + 本地文件系统 adapter。

- MinioRepository：S3 兼容对象存储（生产方案）
- LocalFSAdapter：本地文件系统（轻量方案，技术文档 9.4，签名与 MinIO 一致）

两者均实现 interfaces.storage.ObjectStorage Protocol。
业务层通过依赖注入选择具体实现，不感知后端差异。
"""
from __future__ import annotations

import logging
import os
import shutil
import uuid
from typing import Optional

from interfaces.storage import ObjectStorage
from utils.exceptions import StorageError

logger = logging.getLogger(__name__)


class MinioRepository(ObjectStorage):
    """MinIO 对象存储仓库（S3 兼容）

    配置（config.yaml storage.minio）：
    - endpoint: MinIO 地址（host:port）
    - access_key / secret_key: 凭据（secret_key 走 keyring）
    - bucket: 存储桶名（不存在时自动创建）
    - secure: 是否启用 HTTPS（默认 False）
    """

    def __init__(self, endpoint: str = "localhost:9000",
                 access_key: str = "admin", secret_key: str = "",
                 bucket: str = "knowledge-base", secure: bool = False):
        self.endpoint = endpoint
        self.access_key = access_key
        self.secret_key = secret_key
        self.bucket = bucket
        self.secure = secure
        self._client = None

    def _get_client(self):
        if self._client is None:
            try:
                from minio import Minio
                from minio.error import S3Error
            except ImportError as e:
                raise StorageError(
                    "未安装 minio 客户端，请执行 pip install minio"
                ) from e

            self._client = Minio(
                endpoint=self.endpoint,
                access_key=self.access_key,
                secret_key=self.secret_key,
                secure=self.secure,
            )
            try:
                if not self._client.bucket_exists(self.bucket):
                    self._client.make_bucket(self.bucket)
                    logger.info(f"MinIO bucket 已创建: {self.bucket}")
            except S3Error as e:
                raise StorageError(f"MinIO bucket 初始化失败: {e}") from e
        return self._client

    def upload(self, local_path: str, object_key: str = "") -> str:
        if not os.path.isfile(local_path):
            raise StorageError(f"本地文件不存在: {local_path}")

        if not object_key:
            object_key = self._generate_object_key(local_path)

        client = self._get_client()
        try:
            from minio.error import S3Error
        except ImportError:
            S3Error = Exception

        try:
            client.fput_object(
                bucket_name=self.bucket,
                object_name=object_key,
                file_path=local_path,
            )
            logger.debug(f"MinIO 上传成功: {object_key}")
            return object_key
        except S3Error as e:
            raise StorageError(f"MinIO 上传失败 {object_key}: {e}") from e

    def download(self, object_key: str, local_path: str) -> str:
        client = self._get_client()
        try:
            from minio.error import S3Error
        except ImportError:
            S3Error = Exception

        local_dir = os.path.dirname(local_path)
        if local_dir:
            os.makedirs(local_dir, exist_ok=True)

        try:
            client.fget_object(
                bucket_name=self.bucket,
                object_name=object_key,
                file_path=local_path,
            )
            return local_path
        except S3Error as e:
            raise StorageError(f"MinIO 下载失败 {object_key}: {e}") from e

    def delete(self, object_key: str) -> None:
        client = self._get_client()
        try:
            from minio.error import S3Error
        except ImportError:
            S3Error = Exception

        try:
            client.remove_object(bucket_name=self.bucket, object_name=object_key)
        except S3Error as e:
            if "NoSuchKey" in str(e) or "NoSuchObject" in str(e):
                logger.debug(f"MinIO 对象不存在（幂等忽略）: {object_key}")
                return
            raise StorageError(f"MinIO 删除失败 {object_key}: {e}") from e

    def exists(self, object_key: str) -> bool:
        client = self._get_client()
        try:
            from minio.error import S3Error
        except ImportError:
            S3Error = Exception

        try:
            client.stat_object(bucket_name=self.bucket, object_name=object_key)
            return True
        except S3Error as e:
            if "NoSuchKey" in str(e) or "NoSuchObject" in str(e):
                return False
            raise StorageError(f"MinIO 存在性检查失败 {object_key}: {e}") from e

    def clear(self) -> None:
        """清空 bucket 内全部对象（知识库全量重置用）。异常仅告警不抛出。"""
        try:
            client = self._get_client()
            for obj in client.list_objects(self.bucket, recursive=True):
                try:
                    client.remove_object(self.bucket, obj.object_name)
                except Exception as e:
                    logger.warning(f"MinIO 删除对象失败 {obj.object_name}: {e}")
            logger.info(f"MinIO bucket 已清空: {self.bucket}")
        except Exception as e:
            logger.warning(f"MinIO 清空失败（忽略）: {e}")

    @staticmethod
    def _generate_object_key(local_path: str) -> str:
        file_name = os.path.basename(local_path) or "file"
        return f"{uuid.uuid4().hex}/{file_name}"


class LocalFSAdapter(ObjectStorage):
    """本地文件系统对象存储 adapter（轻量方案）

    签名与 MinioRepository 一致，业务层无感切换。
    配置（config.yaml storage.local_fs）：
    - root: 本地存储根目录
    """

    def __init__(self, root: str = "./data/files"):
        self.root = os.path.abspath(root)
        os.makedirs(self.root, exist_ok=True)

    def _full_path(self, object_key: str) -> str:
        if not object_key:
            raise StorageError("object_key 不可为空")
        full = os.path.abspath(os.path.join(self.root, object_key))
        if not full.startswith(self.root + os.sep) and full != self.root:
            raise StorageError(f"非法 object_key（路径穿越）: {object_key}")
        return full

    def upload(self, local_path: str, object_key: str = "") -> str:
        if not os.path.isfile(local_path):
            raise StorageError(f"本地文件不存在: {local_path}")

        if not object_key:
            object_key = self._generate_object_key(local_path)

        full = self._full_path(object_key)
        os.makedirs(os.path.dirname(full), exist_ok=True)
        try:
            shutil.copy2(local_path, full)
            logger.debug(f"本地文件系统上传成功: {object_key}")
            return object_key
        except OSError as e:
            raise StorageError(f"本地文件上传失败 {object_key}: {e}") from e

    def download(self, object_key: str, local_path: str) -> str:
        full = self._full_path(object_key)
        if not os.path.isfile(full):
            raise StorageError(f"对象不存在: {object_key}")

        local_dir = os.path.dirname(local_path)
        if local_dir:
            os.makedirs(local_dir, exist_ok=True)
        try:
            shutil.copy2(full, local_path)
            return local_path
        except OSError as e:
            raise StorageError(f"本地文件下载失败 {object_key}: {e}") from e

    def delete(self, object_key: str) -> None:
        full = self._full_path(object_key)
        if not os.path.exists(full):
            return
        try:
            if os.path.isfile(full):
                os.remove(full)
            else:
                shutil.rmtree(full)
        except OSError as e:
            raise StorageError(f"本地文件删除失败 {object_key}: {e}") from e

    def exists(self, object_key: str) -> bool:
        full = self._full_path(object_key)
        return os.path.exists(full)

    def clear(self) -> None:
        """清空 root 下所有子项（保留 root 目录本身）。异常仅告警不抛出。"""
        try:
            for entry in os.listdir(self.root):
                full = os.path.join(self.root, entry)
                try:
                    if os.path.isfile(full) or os.path.islink(full):
                        os.remove(full)
                    else:
                        shutil.rmtree(full)
                except OSError as e:
                    logger.warning(f"本地文件系统删除失败 {full}: {e}")
            logger.info(f"本地文件系统存储已清空: {self.root}")
        except OSError as e:
            logger.warning(f"本地文件系统清空失败（忽略）: {e}")

    @staticmethod
    def _generate_object_key(local_path: str) -> str:
        file_name = os.path.basename(local_path) or "file"
        return f"{uuid.uuid4().hex}/{file_name}"
