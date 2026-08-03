"""PostgreSQL 仓库实现 — 封装全部 SQL 操作

覆盖四类表：
- document_index：文档元数据 + 解析状态机
- chunk_index：知识块反向索引（含去重 UNIQUE 约束）
- category + chunk_category：分类目录 + 多对多关联（单一数据源）
- compensation_queue：补偿队列

连接管理：骨架阶段用单连接 + 自动重连；生产环境可换连接池。
"""
from __future__ import annotations

import json
import logging
from typing import Optional

from models.chunk import Chunk
from models.document import Document
from models.category import Category, ChunkCategory
from models.compensation import CompensationTask

logger = logging.getLogger(__name__)


class PostgresRepository:
    """PostgreSQL 仓库实现"""

    def __init__(self, host: str = "localhost", port: int = 5432,
                 database: str = "knowledge_base", user: str = "admin",
                 password: str = ""):
        self.host = host
        self.port = port
        self.database = database
        self.user = user
        self.password = password
        self._conn = None

    def _get_conn(self):
        """获取连接，断开则自动重连"""
        if self._conn is None or self._conn.closed:
            import psycopg2
            self._conn = psycopg2.connect(
                host=self.host, port=self.port, dbname=self.database,
                user=self.user, password=self.password
            )
            self._conn.autocommit = False
        return self._conn

    def _execute(self, sql: str, params: tuple = None, fetch: str = None):
        """执行 SQL（内部通用方法）。

        Args:
            sql: SQL 语句
            params: 参数元组
            fetch: None=不返回 / "one"=单行 / "all"=多行
        """
        conn = self._get_conn()
        try:
            with conn.cursor() as cur:
                cur.execute(sql, params or ())
                result = None
                if fetch == "one":
                    result = cur.fetchone()
                elif fetch == "all":
                    result = cur.fetchall()
            conn.commit()
            return result
        except Exception:
            conn.rollback()
            raise

    # ========== document_index 表 ==========

    def insert_document(self, doc_id: int, file_name: str,
                        file_path: str, file_type: str,
                        content_hash: str,
                        parse_status: str = "pending",
                        page_count: Optional[int] = None) -> None:
        """插入文档记录"""
        self._execute(
            """INSERT INTO document_index
               (doc_id, file_name, file_path, file_type, content_hash,
                page_count, parse_status)
               VALUES (%s, %s, %s, %s, %s, %s, %s)""",
            (doc_id, file_name, file_path, file_type, content_hash,
             page_count, parse_status)
        )

    def update_parse_status(self, doc_id: int, status: str,
                            fail_stage: Optional[str] = None,
                            fail_reason: Optional[str] = None) -> None:
        """更新文档解析状态（状态机）"""
        self._execute(
            """UPDATE document_index
               SET parse_status = %s, fail_stage = %s, fail_reason = %s
               WHERE doc_id = %s""",
            (status, fail_stage, fail_reason, doc_id)
        )

    def get_parse_status(self, doc_id: int) -> Optional[str]:
        """查询文档当前解析状态"""
        row = self._execute(
            "SELECT parse_status FROM document_index WHERE doc_id = %s",
            (doc_id,), fetch="one"
        )
        return row[0] if row else None

    def get_document(self, doc_id: int) -> Optional[Document]:
        """查询单个文档完整信息"""
        row = self._execute(
            """SELECT doc_id, file_name, file_path, file_type, content_hash,
                      page_count, upload_time, parse_status, fail_stage, fail_reason
               FROM document_index WHERE doc_id = %s""",
            (doc_id,), fetch="one"
        )
        return self._row_to_document(row) if row else None

    def get_file_path(self, doc_id: int) -> Optional[str]:
        """查询文档的对象存储路径"""
        row = self._execute(
            "SELECT file_path FROM document_index WHERE doc_id = %s",
            (doc_id,), fetch="one"
        )
        return row[0] if row else None

    def list_by_status(self, statuses: list[str]) -> list[Document]:
        """按状态列表查询文档（用于恢复中断任务）"""
        rows = self._execute(
            f"""SELECT doc_id, file_name, file_path, file_type, content_hash,
                       page_count, upload_time, parse_status, fail_stage, fail_reason
                FROM document_index
                WHERE parse_status = ANY(%s)
                ORDER BY upload_time""",
            (statuses,), fetch="all"
        )
        return [self._row_to_document(r) for r in rows]

    def delete_document(self, doc_id: int) -> None:
        """删除文档记录（物理删除，由补偿队列调用）"""
        self._execute(
            "DELETE FROM document_index WHERE doc_id = %s", (doc_id,)
        )

    # ========== chunk_index 表 ==========

    def insert_chunks(self, chunks: list[Chunk],
                      classifications: list[list[ChunkCategory]]) -> None:
        """批量插入知识块 + 分类关联。
        按 (content_hash, doc_id) 去重：ON CONFLICT DO NOTHING。
        单事务保证原子性。
        """
        conn = self._get_conn()
        try:
            with conn.cursor() as cur:
                # 1. 插入 chunk_index
                for chunk in chunks:
                    cur.execute(
                        """INSERT INTO chunk_index
                           (chunk_id, content_hash, doc_id, doc_name, page_number,
                            char_start, char_end, bbox, chunk_type, content, vector_id)
                           VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                           ON CONFLICT (content_hash, doc_id) DO NOTHING""",
                        (chunk.chunk_id, chunk.content_hash, chunk.doc_id,
                         chunk.doc_name, chunk.page_number, chunk.char_start,
                         chunk.char_end,
                         json.dumps(chunk.bbox) if chunk.bbox else None,
                         chunk.chunk_type, chunk.content, chunk.vector_id)
                    )
                # 2. 插入 chunk_category 关联
                for chunk, cats in zip(chunks, classifications):
                    for cat in cats:
                        cur.execute(
                            """INSERT INTO chunk_category
                               (chunk_id, category_id, assigned_by, confidence)
                               VALUES (%s, %s, %s, %s)
                               ON CONFLICT (chunk_id, category_id) DO NOTHING""",
                            (cat.chunk_id, cat.category_id,
                             cat.assigned_by, cat.confidence)
                        )
            conn.commit()
        except Exception:
            conn.rollback()
            raise

    def get_chunk(self, chunk_id: int) -> Optional[Chunk]:
        """查询单个知识块（溯源服务使用）"""
        row = self._execute(
            """SELECT chunk_id, content_hash, doc_id, doc_name, page_number,
                      char_start, char_end, bbox, chunk_type, content, vector_id
               FROM chunk_index WHERE chunk_id = %s""",
            (chunk_id,), fetch="one"
        )
        return self._row_to_chunk(row) if row else None

    def list_chunk_ids(self, doc_id: int) -> list[int]:
        """查询文档包含的所有块ID（正向查询：文件→块列表）"""
        rows = self._execute(
            "SELECT chunk_id FROM chunk_index WHERE doc_id = %s ORDER BY chunk_id",
            (doc_id,), fetch="all"
        )
        return [r[0] for r in rows]

    def list_chunks_by_doc(self, doc_id: int) -> list[Chunk]:
        """查询文档包含的所有块（完整信息）"""
        rows = self._execute(
            """SELECT chunk_id, content_hash, doc_id, doc_name, page_number,
                      char_start, char_end, bbox, chunk_type, content, vector_id
               FROM chunk_index WHERE doc_id = %s ORDER BY chunk_id""",
            (doc_id,), fetch="all"
        )
        return [self._row_to_chunk(r) for r in rows]

    def delete_chunks_by_doc(self, doc_id: int) -> None:
        """删除文档的所有块 + 分类关联（级联，由补偿队列调用）"""
        conn = self._get_conn()
        try:
            with conn.cursor() as cur:
                # 先删关联表，再删块表（外键约束）
                cur.execute(
                    """DELETE FROM chunk_category
                       WHERE chunk_id IN
                       (SELECT chunk_id FROM chunk_index WHERE doc_id = %s)""",
                    (doc_id,)
                )
                cur.execute(
                    "DELETE FROM chunk_index WHERE doc_id = %s", (doc_id,)
                )
            conn.commit()
        except Exception:
            conn.rollback()
            raise

    # ========== category 表 ==========

    def list_all_categories(self) -> list[Category]:
        """查询所有分类（分类服务使用）"""
        rows = self._execute(
            """SELECT c.category_id, c.name, c.parent_id, c.description,
                      COUNT(cc.chunk_id) AS chunk_count
               FROM category c
               LEFT JOIN chunk_category cc ON c.category_id = cc.category_id
               GROUP BY c.category_id, c.name, c.parent_id, c.description
               ORDER BY c.name""",
            fetch="all"
        )
        return [Category(
            category_id=r[0], name=r[1], parent_id=r[2],
            description=r[3] or "", chunk_count=r[4]
        ) for r in rows]

    def insert_category(self, category_id: int, name: str,
                        parent_id: Optional[int] = None,
                        description: str = "") -> None:
        """新增分类"""
        self._execute(
            """INSERT INTO category (category_id, name, parent_id, description)
               VALUES (%s, %s, %s, %s)""",
            (category_id, name, parent_id, description)
        )

    # ========== chunk_category 关联表 ==========

    def upsert_chunk_categories(self, chunk_id: int,
                                category_ids: list[int]) -> None:
        """更新块分类关联（先删后插，单一数据源）"""
        conn = self._get_conn()
        try:
            with conn.cursor() as cur:
                cur.execute(
                    "DELETE FROM chunk_category WHERE chunk_id = %s", (chunk_id,)
                )
                for cat_id in category_ids:
                    cur.execute(
                        """INSERT INTO chunk_category
                           (chunk_id, category_id, assigned_by, confidence)
                           VALUES (%s, %s, %s, %s)
                           ON CONFLICT (chunk_id, category_id) DO NOTHING""",
                        (chunk_id, cat_id, "manual", 1.0)
                    )
            conn.commit()
        except Exception:
            conn.rollback()
            raise

    def get_category_names(self, chunk_id: int) -> list[str]:
        """查询块所属分类名称列表（从关联表读取，同步 Qdrant payload）"""
        rows = self._execute(
            """SELECT c.name
               FROM chunk_category cc
               JOIN category c ON cc.category_id = c.category_id
               WHERE cc.chunk_id = %s""",
            (chunk_id,), fetch="all"
        )
        return [r[0] for r in rows]

    # ========== compensation_queue 表 ==========

    def enqueue_compensation(self, op_type: str, target_id: str) -> int:
        """入队补偿任务，返回任务ID"""
        row = self._execute(
            """INSERT INTO compensation_queue (op_type, target_id, status, retries)
               VALUES (%s, %s, 'pending', 0)
               RETURNING id""",
            (op_type, target_id), fetch="one"
        )
        return row[0] if row else None

    def list_pending_compensations(self) -> list[CompensationTask]:
        """查询所有待处理补偿任务"""
        rows = self._execute(
            """SELECT id, op_type, target_id, status, retries,
                      created_at, updated_at
               FROM compensation_queue
               WHERE status = 'pending'
               ORDER BY created_at
               LIMIT 100""",
            fetch="all"
        )
        return [CompensationTask(
            id=r[0], op_type=r[1], target_id=r[2], status=r[3],
            retries=r[4], created_at=str(r[5]) if r[5] else None,
            updated_at=str(r[6]) if r[6] else None
        ) for r in rows]

    def mark_compensation_done(self, task_id: int) -> None:
        """标记补偿任务完成"""
        self._execute(
            "UPDATE compensation_queue SET status = 'done', updated_at = now() WHERE id = %s",
            (task_id,)
        )

    def mark_compensation_failed(self, task_id: int, reason: str) -> None:
        """标记补偿任务最终失败"""
        self._execute(
            """UPDATE compensation_queue
               SET status = 'failed', updated_at = now(), fail_reason = %s
               WHERE id = %s""",
            (reason, task_id)
        )

    def update_compensation_retries(self, task_id: int, retries: int) -> None:
        """更新补偿任务重试次数"""
        self._execute(
            "UPDATE compensation_queue SET retries = %s, updated_at = now() WHERE id = %s",
            (retries, task_id)
        )

    # ========== 行映射工具方法 ==========

    @staticmethod
    def _row_to_document(row) -> Document:
        """数据库行 → Document 对象"""
        return Document(
            doc_id=row[0], file_name=row[1], file_path=row[2],
            file_type=row[3], content_hash=row[4], page_count=row[5],
            upload_time=str(row[6]) if row[6] else None,
            parse_status=row[7], fail_stage=row[8], fail_reason=row[9]
        )

    @staticmethod
    def _row_to_chunk(row) -> Chunk:
        """数据库行 → Chunk 对象"""
        bbox = None
        if row[7]:
            bbox = json.loads(row[7]) if isinstance(row[7], str) else row[7]
        return Chunk(
            chunk_id=row[0], content_hash=row[1], doc_id=row[2],
            doc_name=row[3], page_number=row[4], char_start=row[5],
            char_end=row[6], bbox=bbox, chunk_type=row[8],
            content=row[9], vector_id=row[10]
        )

    def close(self):
        """关闭连接"""
        if self._conn and not self._conn.closed:
            self._conn.close()
