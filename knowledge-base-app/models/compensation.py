"""补偿队列任务模型"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Optional


@dataclass
class CompensationTask:
    """compensation_queue 表的行映射"""
    id: int                                          # 任务ID（Snowflake 或自增）
    op_type: str                                     # delete_qdrant / delete_pg_chunks / delete_pg_doc / delete_minio / upsert_qdrant
    target_id: str                                   # 操作目标 ID
    status: str = "pending"                          # pending / done / failed
    retries: int = 0
    created_at: Optional[str] = None
    updated_at: Optional[str] = None
    fail_reason: Optional[str] = None
