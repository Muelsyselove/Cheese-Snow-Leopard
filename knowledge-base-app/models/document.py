"""文档模型"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Optional


@dataclass
class Document:
    """文档元数据 — 文件级正向索引"""
    doc_id: int                                    # Snowflake 业务ID
    file_name: str                                 # 原始文件名
    file_path: str                                 # 对象存储路径
    file_type: str                                 # pdf/docx/png...
    content_hash: str                              # SHA-256 文件指纹
    parse_status: str = "pending"                  # 见状态机：pending/parsing/embedding/classifying/storing/completed/failed/deleting
    fail_stage: Optional[str] = None               # 失败时记录阶段
    fail_reason: Optional[str] = None              # 失败原因
    page_count: Optional[int] = None
    upload_time: Optional[str] = None


# parse_status 状态机
PARSE_STATUS = {
    "pending":      "已入库待解析",
    "parsing":      "VLM 解析中",
    "embedding":    "向量化中",
    "classifying":  "AI 分类中",
    "storing":      "写存储中",
    "completed":    "完成",
    "failed":       "失败（见 fail_stage）",
    "deleting":     "删除中",
}
