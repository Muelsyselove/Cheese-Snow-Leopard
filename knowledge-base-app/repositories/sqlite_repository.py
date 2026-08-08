"""SQLite 仓库实现 — 零配置回退方案

与 PostgresRepository 接口完全一致（同方法名/同参数/同返回模型），
供零配置场景替换使用：无需安装/启动 PostgreSQL，数据落到
<data_root>/db/knowledge_base.db，开箱即用。

方言差异处理：
- 占位符 %s → ?
- ANY(%s) 数组匹配 → IN (?, ...)
- RETURNING id → cursor.lastrowid
- now() → datetime('now')
- JSONB → TEXT（JSON 字符串）
- BIGSERIAL → INTEGER PRIMARY KEY AUTOINCREMENT
- TRUNCATE ... RESTART IDENTITY CASCADE → 按外键序 DELETE

线程安全：单连接 + check_same_thread=False + 全局锁（应用为多线程：
reconciler / 导入 / UI 均可能并发访问）。WAL 模式提升并发读性能。
建表在 __init__ 自动完成（IF NOT EXISTS，幂等）。
"""
from __future__ import annotations

import json
import logging
import os
import sqlite3
import threading
from typing import Optional

from models.chunk import Chunk
from models.document import Document
from models.category import Category, ChunkCategory
from models.compensation import CompensationTask

logger = logging.getLogger(__name__)

SCHEMA_SQL = """
CREATE TABLE IF NOT EXISTS document_index (
    doc_id          INTEGER PRIMARY KEY,
    file_name       TEXT NOT NULL,
    file_path       TEXT NOT NULL,
    file_type       TEXT NOT NULL,
    content_hash    TEXT NOT NULL,
    page_count      INTEGER,
    upload_time     TEXT DEFAULT (datetime('now')),
    parse_status    TEXT DEFAULT 'pending',
    fail_stage      TEXT,
    fail_reason     TEXT
);

CREATE TABLE IF NOT EXISTS chunk_index (
    chunk_id        INTEGER PRIMARY KEY,
    content_hash    TEXT NOT NULL,
    doc_id          INTEGER NOT NULL,
    doc_name        TEXT NOT NULL,
    page_number     INTEGER,
    char_start      INTEGER,
    char_end        INTEGER,
    bbox            TEXT,
    chunk_type      TEXT,
    content         TEXT NOT NULL,
    vector_id       TEXT,
    created_at      TEXT DEFAULT (datetime('now')),
    FOREIGN KEY (doc_id) REFERENCES document_index(doc_id)
);
CREATE INDEX IF NOT EXISTS idx_chunk_index_doc_id ON chunk_index(doc_id);
CREATE UNIQUE INDEX IF NOT EXISTS idx_chunk_dedup ON chunk_index(content_hash, doc_id);

CREATE TABLE IF NOT EXISTS category (
    category_id     INTEGER PRIMARY KEY,
    name            TEXT NOT NULL,
    parent_id       INTEGER,
    description     TEXT,
    created_at      TEXT DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS chunk_category (
    chunk_id        INTEGER NOT NULL,
    category_id     INTEGER NOT NULL,
    assigned_by     TEXT DEFAULT 'ai',
    confidence      REAL,
    PRIMARY KEY (chunk_id, category_id),
    FOREIGN KEY (chunk_id) REFERENCES chunk_index(chunk_id) ON DELETE CASCADE,
    FOREIGN KEY (category_id) REFERENCES category(category_id) ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS compensation_queue (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    op_type     TEXT NOT NULL,
    target_id   TEXT NOT NULL,
    status      TEXT DEFAULT 'pending',
    retries     INTEGER DEFAULT 0,
    fail_reason TEXT,
    created_at  TEXT DEFAULT (datetime('now')),
    updated_at  TEXT DEFAULT (datetime('now'))
);
CREATE INDEX IF NOT EXISTS idx_compensation_status ON compensation_queue(status);
"""


class SQLiteRepository:
    """SQLite 仓库实现（接口与 PostgresRepository 一致）"""

    def __init__(self, db_path: str):
        self.db_path = os.path.abspath(db_path)
        os.makedirs(os.path.dirname(self.db_path), exist_ok=True)
        self._conn: Optional[sqlite3.Connection] = None
        self._lock = threading.Lock()
        self._init_schema()
        logger.info(f"SQLite 元数据库已就绪: {self.db_path}")

    # ---------------------------------------------------------- 连接
    def _get_conn(self) -> sqlite3.Connection:
        if self._conn is None:
            self._conn = sqlite3.connect(self.db_path, check_same_thread=False)
            self._conn.execute("PRAGMA foreign_keys = ON")
            self._conn.execute("PRAGMA journal_mode = WAL")
        return self._conn

    def _init_schema(self):
        conn = self._get_conn()
        with self._lock:
            try:
                conn.executescript(SCHEMA_SQL)
                conn.commit()
            except Exception:
                conn.rollback()
                raise

    def _execute(self, sql: str, params: tuple = None, fetch: str = None):
        """执行 SQL（内部通用方法，语义同 PostgresRepository._execute）"""
        with self._lock:
            conn = self._get_conn()
            try:
                cur = conn.cursor()
                cur.execute(sql, params or ())
                result = None
                if fetch == "one":
                    result = cur.fetchone()
                elif fetch == "all":
                    result = cur.fetchall()
                lastrowid = cur.lastrowid
                cur.close()
                conn.commit()
                if fetch == "lastrowid":
                    return lastrowid
                return result
            except Exception:
                conn.rollback()
                raise

    @staticmethod
    def _in_placeholders(values: list) -> str:
        return ", ".join("?" for _ in values)

    # ========== document_index 表 ==========

    def insert_document(self, doc_id: int, file_name: str,
                        file_path: str, file_type: str,
                        content_hash: str,
                        parse_status: str = "pending",
                        page_count: Optional[int] = None) -> None:
        self._execute(
            """INSERT INTO document_index
               (doc_id, file_name, file_path, file_type, content_hash,
                page_count, parse_status)
               VALUES (?, ?, ?, ?, ?, ?, ?)""",
            (doc_id, file_name, file_path, file_type, content_hash,
             page_count, parse_status)
        )

    def update_parse_status(self, doc_id: int, status: str,
                            fail_stage: Optional[str] = None,
                            fail_reason: Optional[str] = None) -> None:
        self._execute(
            """UPDATE document_index
               SET parse_status = ?, fail_stage = ?, fail_reason = ?
               WHERE doc_id = ?""",
            (status, fail_stage, fail_reason, doc_id)
        )

    def get_parse_status(self, doc_id: int) -> Optional[str]:
        row = self._execute(
            "SELECT parse_status FROM document_index WHERE doc_id = ?",
            (doc_id,), fetch="one"
        )
        return row[0] if row else None

    def get_document(self, doc_id: int) -> Optional[Document]:
        row = self._execute(
            """SELECT doc_id, file_name, file_path, file_type, content_hash,
                      page_count, upload_time, parse_status, fail_stage, fail_reason
               FROM document_index WHERE doc_id = ?""",
            (doc_id,), fetch="one"
        )
        return self._row_to_document(row) if row else None

    def get_file_path(self, doc_id: int) -> Optional[str]:
        row = self._execute(
            "SELECT file_path FROM document_index WHERE doc_id = ?",
            (doc_id,), fetch="one"
        )
        return row[0] if row else None

    def list_by_status(self, statuses: list[str]) -> list[Document]:
        if not statuses:
            return []
        ph = self._in_placeholders(statuses)
        rows = self._execute(
            f"""SELECT doc_id, file_name, file_path, file_type, content_hash,
                       page_count, upload_time, parse_status, fail_stage, fail_reason
                FROM document_index
                WHERE parse_status IN ({ph})
                ORDER BY upload_time""",
            tuple(statuses), fetch="all"
        )
        return [self._row_to_document(r) for r in rows]

    def list_all_documents(self) -> list[Document]:
        rows = self._execute(
            """SELECT doc_id, file_name, file_path, file_type, content_hash,
                      page_count, upload_time, parse_status, fail_stage, fail_reason
               FROM document_index
               ORDER BY upload_time""",
            fetch="all"
        )
        return [self._row_to_document(r) for r in rows]

    def delete_document(self, doc_id: int) -> None:
        self._execute(
            "DELETE FROM document_index WHERE doc_id = ?", (doc_id,)
        )

    # ========== chunk_index 表 ==========

    def insert_chunks(self, chunks: list[Chunk],
                      classifications: list[list[ChunkCategory]]) -> None:
        with self._lock:
            conn = self._get_conn()
            try:
                cur = conn.cursor()
                for chunk in chunks:
                    cur.execute(
                        """INSERT INTO chunk_index
                           (chunk_id, content_hash, doc_id, doc_name, page_number,
                            char_start, char_end, bbox, chunk_type, content, vector_id)
                           VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                           ON CONFLICT (content_hash, doc_id) DO NOTHING""",
                        (chunk.chunk_id, chunk.content_hash, chunk.doc_id,
                         chunk.doc_name, chunk.page_number, chunk.char_start,
                         chunk.char_end,
                         json.dumps(chunk.bbox) if chunk.bbox else None,
                         chunk.chunk_type, chunk.content, chunk.vector_id)
                    )
                for chunk, cats in zip(chunks, classifications):
                    for cat in cats:
                        cur.execute(
                            """INSERT INTO chunk_category
                               (chunk_id, category_id, assigned_by, confidence)
                               VALUES (?, ?, ?, ?)
                               ON CONFLICT (chunk_id, category_id) DO NOTHING""",
                            (cat.chunk_id, cat.category_id,
                             cat.assigned_by, cat.confidence)
                        )
                cur.close()
                conn.commit()
            except Exception:
                conn.rollback()
                raise

    def get_chunk(self, chunk_id: int) -> Optional[Chunk]:
        row = self._execute(
            """SELECT chunk_id, content_hash, doc_id, doc_name, page_number,
                      char_start, char_end, bbox, chunk_type, content, vector_id
               FROM chunk_index WHERE chunk_id = ?""",
            (chunk_id,), fetch="one"
        )
        return self._row_to_chunk(row) if row else None

    def list_chunk_ids(self, doc_id: int) -> list[int]:
        rows = self._execute(
            "SELECT chunk_id FROM chunk_index WHERE doc_id = ? ORDER BY chunk_id",
            (doc_id,), fetch="all"
        )
        return [r[0] for r in rows]

    def list_chunks_by_doc(self, doc_id: int) -> list[Chunk]:
        rows = self._execute(
            """SELECT chunk_id, content_hash, doc_id, doc_name, page_number,
                      char_start, char_end, bbox, chunk_type, content, vector_id
               FROM chunk_index WHERE doc_id = ? ORDER BY chunk_id""",
            (doc_id,), fetch="all"
        )
        return [self._row_to_chunk(r) for r in rows]

    def list_all_chunks(self, batch_size: int = 500) -> list[Chunk]:
        rows = self._execute(
            """SELECT chunk_id, content_hash, doc_id, doc_name, page_number,
                      char_start, char_end, bbox, chunk_type, content, vector_id
               FROM chunk_index ORDER BY chunk_id""",
            fetch="all"
        )
        return [self._row_to_chunk(r) for r in rows]

    def count_chunks(self) -> int:
        rows = self._execute("SELECT COUNT(*) FROM chunk_index", fetch="all")
        return rows[0][0] if rows else 0

    def list_random_chunks_by_category(self, category_ids: list[int],
                                       limit: int) -> list[Chunk]:
        if not category_ids:
            return []
        ph = self._in_placeholders(category_ids)
        rows = self._execute(
            f"""SELECT * FROM (
                   SELECT DISTINCT c.chunk_id, c.content_hash, c.doc_id,
                          c.doc_name, c.page_number, c.char_start, c.char_end,
                          c.bbox, c.chunk_type, c.content, c.vector_id
                   FROM chunk_index c
                   JOIN chunk_category cc ON c.chunk_id = cc.chunk_id
                   WHERE cc.category_id IN ({ph})
               ) t
               ORDER BY RANDOM() LIMIT ?""",
            tuple(category_ids) + (limit,), fetch="all"
        )
        return [self._row_to_chunk(r) for r in rows]

    def list_random_chunks(self, limit: int) -> list[Chunk]:
        rows = self._execute(
            """SELECT chunk_id, content_hash, doc_id, doc_name, page_number,
                      char_start, char_end, bbox, chunk_type, content, vector_id
               FROM chunk_index ORDER BY RANDOM() LIMIT ?""",
            (limit,), fetch="all"
        )
        return [self._row_to_chunk(r) for r in rows]

    def list_all_doc_ids(self) -> list[int]:
        rows = self._execute(
            "SELECT DISTINCT doc_id FROM chunk_index ORDER BY doc_id",
            fetch="all"
        )
        return [r[0] for r in rows]

    def delete_chunks_by_doc(self, doc_id: int) -> None:
        with self._lock:
            conn = self._get_conn()
            try:
                cur = conn.cursor()
                cur.execute(
                    """DELETE FROM chunk_category
                       WHERE chunk_id IN
                       (SELECT chunk_id FROM chunk_index WHERE doc_id = ?)""",
                    (doc_id,)
                )
                cur.execute(
                    "DELETE FROM chunk_index WHERE doc_id = ?", (doc_id,)
                )
                cur.close()
                conn.commit()
            except Exception:
                conn.rollback()
                raise

    # ========== category 表 ==========

    def list_all_categories(self) -> list[Category]:
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
        self._execute(
            """INSERT INTO category (category_id, name, parent_id, description)
               VALUES (?, ?, ?, ?)""",
            (category_id, name, parent_id, description)
        )

    def find_category_by_path(self, path: list[str]) -> Optional[int]:
        parent_id = None
        leaf_id = None
        for name in path:
            name = (name or "").strip()
            if not name:
                continue
            if parent_id is None:
                row = self._execute(
                    """SELECT category_id FROM category
                       WHERE parent_id IS NULL AND lower(name) = ?""",
                    (name.lower(),), fetch="one"
                )
            else:
                row = self._execute(
                    """SELECT category_id FROM category
                       WHERE parent_id = ? AND lower(name) = ?""",
                    (parent_id, name.lower()), fetch="one"
                )
            if not row:
                return None
            leaf_id = row[0]
            parent_id = row[0]
        return leaf_id

    def list_children(self, parent_id: Optional[int]) -> list[Category]:
        if parent_id is None:
            rows = self._execute(
                """SELECT c.category_id, c.name, c.parent_id, c.description,
                          COUNT(cc.chunk_id) AS chunk_count
                   FROM category c
                   LEFT JOIN chunk_category cc
                          ON c.category_id = cc.category_id
                   WHERE c.parent_id IS NULL
                   GROUP BY c.category_id, c.name, c.parent_id, c.description
                   ORDER BY c.name""",
                fetch="all"
            )
        else:
            rows = self._execute(
                """SELECT c.category_id, c.name, c.parent_id, c.description,
                          COUNT(cc.chunk_id) AS chunk_count
                   FROM category c
                   LEFT JOIN chunk_category cc
                          ON c.category_id = cc.category_id
                   WHERE c.parent_id = ?
                   GROUP BY c.category_id, c.name, c.parent_id, c.description
                   ORDER BY c.name""",
                (parent_id,), fetch="all"
            )
        return [Category(
            category_id=r[0], name=r[1], parent_id=r[2],
            description=r[3] or "", chunk_count=r[4]
        ) for r in rows]

    # ========== chunk_category 关联表 ==========

    def upsert_chunk_categories(self, chunk_id: int,
                                category_ids: list[int]) -> None:
        with self._lock:
            conn = self._get_conn()
            try:
                cur = conn.cursor()
                cur.execute(
                    "DELETE FROM chunk_category WHERE chunk_id = ?", (chunk_id,)
                )
                for cat_id in category_ids:
                    cur.execute(
                        """INSERT INTO chunk_category
                           (chunk_id, category_id, assigned_by, confidence)
                           VALUES (?, ?, ?, ?)
                           ON CONFLICT (chunk_id, category_id) DO NOTHING""",
                        (chunk_id, cat_id, "manual", 1.0)
                    )
                cur.close()
                conn.commit()
            except Exception:
                conn.rollback()
                raise

    def get_category_names(self, chunk_id: int) -> list[str]:
        rows = self._execute(
            """SELECT c.name
               FROM chunk_category cc
               JOIN category c ON cc.category_id = c.category_id
               WHERE cc.chunk_id = ?""",
            (chunk_id,), fetch="all"
        )
        return [r[0] for r in rows]

    def count_chunk_category_links(self) -> int:
        row = self._execute(
            "SELECT COUNT(*) FROM chunk_category", fetch="one"
        )
        return row[0] if row else 0

    # ========== compensation_queue 表 ==========

    def enqueue_compensation(self, op_type: str, target_id: str) -> int:
        return self._execute(
            """INSERT INTO compensation_queue (op_type, target_id, status, retries)
               VALUES (?, ?, 'pending', 0)""",
            (op_type, target_id), fetch="lastrowid"
        )

    def list_pending_compensations(self) -> list[CompensationTask]:
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
        self._execute(
            """UPDATE compensation_queue
               SET status = 'done', updated_at = datetime('now') WHERE id = ?""",
            (task_id,)
        )

    def mark_compensation_failed(self, task_id: int, reason: str) -> None:
        self._execute(
            """UPDATE compensation_queue
               SET status = 'failed', updated_at = datetime('now'), fail_reason = ?
               WHERE id = ?""",
            (reason, task_id)
        )

    def update_compensation_retries(self, task_id: int, retries: int) -> None:
        self._execute(
            """UPDATE compensation_queue
               SET retries = ?, updated_at = datetime('now') WHERE id = ?""",
            (retries, task_id)
        )

    # ========== 全量清空（知识库重置） ==========

    def clear_all_knowledge(self) -> None:
        """清空全部知识数据（单事务按外键序 DELETE）"""
        with self._lock:
            conn = self._get_conn()
            try:
                cur = conn.cursor()
                for table in ("chunk_category", "chunk_index",
                              "document_index", "category",
                              "compensation_queue"):
                    cur.execute(f"DELETE FROM {table}")
                cur.close()
                conn.commit()
            except Exception:
                conn.rollback()
                raise

    # ========== 行映射工具方法 ==========

    @staticmethod
    def _row_to_document(row) -> Document:
        return Document(
            doc_id=row[0], file_name=row[1], file_path=row[2],
            file_type=row[3], content_hash=row[4], page_count=row[5],
            upload_time=str(row[6]) if row[6] else None,
            parse_status=row[7], fail_stage=row[8], fail_reason=row[9]
        )

    @staticmethod
    def _row_to_chunk(row) -> Chunk:
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
        with self._lock:
            if self._conn is not None:
                self._conn.close()
                self._conn = None
