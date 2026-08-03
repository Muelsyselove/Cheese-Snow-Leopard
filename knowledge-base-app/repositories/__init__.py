"""存储仓库层 — 封装 PostgreSQL SQL 与对象存储操作

业务层通过此包的接口访问存储，不直接写 SQL 或调用对象存储 SDK。
当前实现：
- PostgresRepository（psycopg2）— 元数据/目录/补偿队列
- MinioRepository（minio）— 原始文件对象存储（生产方案）
- LocalFSAdapter — 本地文件系统（轻量方案，见技术文档 9.4，签名与 MinIO 一致）
"""
from repositories.postgres_repository import PostgresRepository
from repositories.object_storage import MinioRepository, LocalFSAdapter

__all__ = ["PostgresRepository", "MinioRepository", "LocalFSAdapter"]
