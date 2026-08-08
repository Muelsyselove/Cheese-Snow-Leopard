"""配置加载与组件工厂

配置加载时调用 resolve_credential_placeholder 解析 keyring:xxx 占位符为真实凭据。
工厂根据配置动态创建组件实例，业务层仅接收接口。

零配置回退（开箱即用）：
- 元数据仓库：PostgreSQL 不可达时自动回退 SQLite（data/db/knowledge_base.db）
- 向量存储：Qdrant 服务器不可达时自动回退本地嵌入模式（data/qdrant/）
- 对象存储：MinIO 不可达时自动回退本地文件系统（data/files/）
回退仅在本进程生效，不回写 config.yaml；服务恢复后重启即回到生产方案。
"""
from __future__ import annotations

import logging
import socket
from dataclasses import dataclass, field
from typing import Any

import yaml

from utils.credentials import resolve_credential_placeholder

logger = logging.getLogger(__name__)


def _tcp_open(host: str, port: int, timeout: float = 1.0) -> bool:
    """探测 TCP 端口是否可连（用于服务自动发现与零配置回退）"""
    try:
        with socket.create_connection((host, int(port)), timeout=timeout):
            return True
    except (OSError, ValueError):
        return False


@dataclass
class AppConfig:
    llm: dict
    encoding: dict
    vlm: dict
    embedding: dict
    storage: dict
    chunking: dict
    retrieval: dict
    concurrency: dict
    ui: dict
    paths: dict = field(default_factory=dict)
    compute: dict = field(default_factory=dict)


def load_config(path: str = "config.yaml") -> AppConfig:
    """加载配置文件并解析 keyring 占位符"""
    with open(path, "r", encoding="utf-8") as f:
        data = yaml.safe_load(f)
    # 初始化数据路径（必须在创建任何组件前完成）
    from utils.paths import init_paths
    paths_cfg = data.get("paths") or {}
    init_paths(paths_cfg.get("data_root"))
    # 递归解析 keyring:xxx 占位符
    data = _resolve_credentials(data)
    return AppConfig(
        llm=data["llm"],
        encoding=data.get("encoding", {"worker_id": 1}),
        vlm=data["vlm"],
        embedding=data["embedding"],
        storage=data["storage"],
        chunking=data["chunking"],
        retrieval=data["retrieval"],
        concurrency=data.get("concurrency", {}),
        ui=data.get("ui", {}),
        paths=paths_cfg,
        compute=data.get("compute", {}),
    )


def _resolve_credentials(obj):
    """递归解析 dict/list 中的 keyring:xxx 占位符

    缺失的 keyring 凭据返回空字符串而非抛异常，确保应用在未配置凭据时仍可启动。
    """
    if isinstance(obj, dict):
        return {k: _resolve_credentials(v) for k, v in obj.items()}
    if isinstance(obj, list):
        return [_resolve_credentials(v) for v in obj]
    if isinstance(obj, str) and obj.startswith("keyring:"):
        try:
            return resolve_credential_placeholder(obj)
        except ValueError:
            return ""
    return obj


class ComponentFactory:
    """根据配置动态创建组件实例，业务层仅接收接口"""

    def __init__(self, config: AppConfig):
        self.config = config

    def create_parser(self):
        """创建文档解析器（统一接口，原 create_vlm 合并于此）"""
        provider = self.config.vlm["provider"]
        if provider == "A":
            from adapters.paddleocr_vl import PaddleOCRVLModel
            return PaddleOCRVLModel(**self.config.vlm["paddleocr_vl"])
        elif provider == "B":
            from adapters.mineru_vlm import MinerUModel
            return MinerUModel(**self.config.vlm["mineru_vlm"])
        elif provider == "C":
            from adapters.minicpm_vlm import MiniCPMVModel
            return MiniCPMVModel(**self.config.vlm["minicpm_v"])
        else:
            raise ValueError(f"未知 VLM provider: {provider}")

    def create_embedder(self):
        """创建文本向量化器"""
        provider = self.config.embedding["provider"]
        if provider == "A":
            from adapters.bge_embedder import BgeM3Embedder
            return BgeM3Embedder(**self.config.embedding["bge_m3"])
        elif provider == "B":
            from adapters.qwen3_embedder import Qwen3Embedder
            return Qwen3Embedder(**self.config.embedding["qwen3"])
        else:
            raise ValueError(f"未知 Embedding provider: {provider}")

    def create_llm(self):
        """创建文字 LLM 客户端"""
        from adapters.openai_llm import OpenAILLMClient
        cfg = self.config.llm
        return OpenAILLMClient(
            api_base=cfg["api_base"],
            api_key=cfg["api_key"],  # 已由 load_config 解析为真实值
            model=cfg["model"],
            temperature=cfg.get("temperature", 0.3),
            max_tokens=cfg.get("max_tokens", 4096),
            timeout=cfg.get("timeout", 60)
        )

    def create_vector_store(self, sparse_support: bool):
        """创建向量存储

        零配置回退：未显式配置 local_path 且 Qdrant 服务器不可达时，
        自动切换到本地嵌入模式（data/qdrant/），无需启动 Qdrant 服务。
        """
        from adapters.qdrant_store import QdrantStore
        cfg = (self.config.storage or {}).get("qdrant", {})
        host = cfg.get("host", "localhost")
        port = int(cfg.get("port", 6333))
        local_path = cfg.get("local_path") or None
        if local_path is None and not _tcp_open(host, port):
            from utils.paths import get_qdrant_local_path
            local_path = get_qdrant_local_path()
            logger.warning(
                f"Qdrant 服务器 {host}:{port} 不可达，"
                f"回退到本地嵌入模式: {local_path}"
            )
        return QdrantStore(
            host=host, port=port,
            collection=cfg.get("collection", "text_chunks"),
            sparse_support=sparse_support,
            local_path=local_path,
        )

    def create_metadata_repository(self):
        """创建元数据仓库（document/chunk/category/compensation）

        零配置回退：PostgreSQL 不可达（端口关闭或连接失败）时，
        自动切换到 SQLite（data/db/knowledge_base.db），自动建表。
        """
        storage = self.config.storage or {}
        pg_cfg = storage.get("postgres") or {}
        host = pg_cfg.get("host", "localhost")
        port = int(pg_cfg.get("port", 5432))
        if pg_cfg and _tcp_open(host, port):
            try:
                from repositories import PostgresRepository
                repo = PostgresRepository(
                    host=host, port=port,
                    database=pg_cfg.get("database", "knowledge_base"),
                    user=pg_cfg.get("user", "admin"),
                    password=pg_cfg.get("password", ""),
                )
                # 触发真实连接验证（库不存在/认证失败时抛异常 → 回退）
                conn = repo._get_conn()
                with conn.cursor() as cur:
                    cur.execute("SELECT 1")
                logger.info(f"元数据仓库: PostgreSQL {host}:{port}")
                return repo
            except Exception as e:
                logger.warning(f"PostgreSQL 连接失败，回退 SQLite: {e}")
        from repositories import SQLiteRepository
        from utils.paths import get_metadata_db_path
        db_path = get_metadata_db_path()
        logger.warning(f"元数据仓库: SQLite（零配置模式） {db_path}")
        return SQLiteRepository(db_path)

    def create_snowflake(self):
        """创建 Snowflake ID 生成器"""
        from services.encoding import SnowflakeGenerator
        return SnowflakeGenerator(worker_id=self.config.encoding.get("worker_id", 1))

    def create_chunker(self, token_counter=None):
        """创建文档分块器（结构感知分块）

        :param token_counter: 可选的 TokenCounter，默认使用 CharTokenCounter（无第三方依赖）
        """
        from services.chunker import StructureAwareChunker
        cfg = self.config.chunking
        return StructureAwareChunker(
            target_tokens=cfg.get("target_tokens", 300),
            overlap_ratio=cfg.get("overlap_ratio", 0.15),
            min_chunk_tokens=cfg.get("min_chunk_tokens", 50),
            token_counter=token_counter,
        )

    def create_object_storage(self):
        """创建对象存储仓库

        按配置自动选择后端：
        - storage.minio 段存在且服务可达 → MinioRepository（生产方案）
        - storage.minio 段存在但服务不可达 → LocalFSAdapter（零配置回退）
        - storage.local_fs 段存在 → LocalFSAdapter（轻量方案，技术文档 9.4）
        两者实现同一 ObjectStorage Protocol，业务层无感切换。
        """
        storage = self.config.storage or {}
        if "minio" in storage:
            cfg = storage["minio"]
            endpoint = cfg.get("endpoint", "localhost:9000")
            host, _, port_s = endpoint.partition(":")
            if _tcp_open(host or "localhost", int(port_s or 9000)):
                from repositories import MinioRepository
                return MinioRepository(
                    endpoint=endpoint,
                    access_key=cfg.get("access_key", "admin"),
                    secret_key=cfg.get("secret_key", ""),
                    bucket=cfg.get("bucket", "knowledge-base"),
                    secure=cfg.get("secure", False),
                )
            logger.warning(
                f"MinIO {endpoint} 不可达，回退到本地文件系统存储"
            )
        if "local_fs" in storage:
            from repositories import LocalFSAdapter
            cfg = storage["local_fs"]
            return LocalFSAdapter(root=cfg.get("root") or _default_files_root())
        # 默认回退到本地文件系统（无外部依赖，开箱即用）
        from repositories import LocalFSAdapter
        return LocalFSAdapter(root=_default_files_root())

def _default_files_root() -> str:
    """获取默认文件存储根目录（来自 paths.py）"""
    try:
        from utils.paths import get_files_root
        return get_files_root()
    except Exception:
        return "./data/files"
