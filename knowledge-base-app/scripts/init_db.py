"""数据库初始化脚本 — 建表

执行：python -m scripts.init_db
按技术文档 4.2 节表结构创建全部表与索引。
"""
from __future__ import annotations

import sys
import os

# 添加项目根到 path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


SCHEMA_SQL = """
-- ===== 文档元数据表 =====
CREATE TABLE IF NOT EXISTS document_index (
    doc_id          BIGINT PRIMARY KEY,
    file_name       VARCHAR(500) NOT NULL,
    file_path       VARCHAR(1000) NOT NULL,
    file_type       VARCHAR(20) NOT NULL,
    content_hash    VARCHAR(64) NOT NULL,
    page_count      INT,
    upload_time     TIMESTAMPTZ DEFAULT now(),
    parse_status    VARCHAR(20) DEFAULT 'pending',
    fail_stage      VARCHAR(20),
    fail_reason     TEXT
);

-- ===== 知识块索引表 =====
CREATE TABLE IF NOT EXISTS chunk_index (
    chunk_id        BIGINT PRIMARY KEY,
    content_hash    VARCHAR(64) NOT NULL,
    doc_id          BIGINT NOT NULL,
    doc_name        VARCHAR(500) NOT NULL,
    page_number     INT,
    char_start      INT,
    char_end        INT,
    bbox            JSONB,
    chunk_type      VARCHAR(20),
    content         TEXT NOT NULL,
    vector_id       VARCHAR(100),
    created_at      TIMESTAMPTZ DEFAULT now(),
    FOREIGN KEY (doc_id) REFERENCES document_index(doc_id)
);

-- 正向查询索引（文件→块列表）
CREATE INDEX IF NOT EXISTS idx_chunk_index_doc_id ON chunk_index(doc_id);
-- 去重唯一约束：同一文件内相同内容去重
CREATE UNIQUE INDEX IF NOT EXISTS idx_chunk_dedup ON chunk_index(content_hash, doc_id);

-- ===== 分类目录表 =====
CREATE TABLE IF NOT EXISTS category (
    category_id     BIGINT PRIMARY KEY,
    name            VARCHAR(200) NOT NULL,
    parent_id       BIGINT,
    description     TEXT,
    created_at      TIMESTAMPTZ DEFAULT now()
);

-- ===== 块-分类多对多关联表（单一数据源） =====
CREATE TABLE IF NOT EXISTS chunk_category (
    chunk_id        BIGINT NOT NULL,
    category_id     BIGINT NOT NULL,
    assigned_by     VARCHAR(20) DEFAULT 'ai',
    confidence      FLOAT,
    PRIMARY KEY (chunk_id, category_id),
    FOREIGN KEY (chunk_id) REFERENCES chunk_index(chunk_id) ON DELETE CASCADE,
    FOREIGN KEY (category_id) REFERENCES category(category_id) ON DELETE CASCADE
);

-- ===== 补偿队列表 =====
CREATE TABLE IF NOT EXISTS compensation_queue (
    id          BIGSERIAL PRIMARY KEY,
    op_type     VARCHAR(20) NOT NULL,
    target_id   VARCHAR(100) NOT NULL,
    status      VARCHAR(20) DEFAULT 'pending',
    retries     INT DEFAULT 0,
    fail_reason TEXT,
    created_at  TIMESTAMPTZ DEFAULT now(),
    updated_at  TIMESTAMPTZ DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_compensation_status ON compensation_queue(status);
"""


def init_database(host: str = "localhost", port: int = 5432,
                  database: str = "knowledge_base", user: str = "admin",
                  password: str = ""):
    """初始化数据库：创建全部表与索引"""
    import psycopg2
    print(f"连接数据库 {host}:{port}/{database} ...")
    conn = psycopg2.connect(
        host=host, port=port, dbname=database, user=user, password=password
    )
    try:
        with conn.cursor() as cur:
            cur.execute(SCHEMA_SQL)
        conn.commit()
        print("✓ 全部表与索引创建完成")
        # 打印已创建的表
        with conn.cursor() as cur:
            cur.execute("""
                SELECT table_name FROM information_schema.tables
                WHERE table_schema = 'public' ORDER BY table_name
            """)
            tables = [r[0] for r in cur.fetchall()]
            print(f"  表: {', '.join(tables)}")
    finally:
        conn.close()


if __name__ == "__main__":
    from config import load_config

    config = load_config("config.yaml")
    pg_cfg = config.storage.get("postgres", {})
    init_database(
        host=pg_cfg.get("host", "localhost"),
        port=pg_cfg.get("port", 5432),
        database=pg_cfg.get("database", "knowledge_base"),
        user=pg_cfg.get("user", "admin"),
        password=pg_cfg.get("password", "")
    )
