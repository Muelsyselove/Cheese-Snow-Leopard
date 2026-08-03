"""存储仓库层 — 封装 PostgreSQL SQL 操作

业务层通过此包的接口访问数据库，不直接写 SQL。
当前实现：PostgresRepository（psycopg2）
未来可扩展：SqliteRepository（轻量方案，见技术文档 9.4）
"""
from repositories.postgres_repository import PostgresRepository

__all__ = ["PostgresRepository"]
