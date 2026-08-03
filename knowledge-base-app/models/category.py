"""分类模型"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Optional


@dataclass
class Category:
    """知识分类"""
    category_id: int                               # 分类ID
    name: str                                      # 分类名称
    parent_id: Optional[int] = None                # 父分类ID（支持多级）
    description: str = ""
    chunk_count: int = 0                           # 该分类下知识块数（冗余字段）


@dataclass
class ChunkCategory:
    """知识块-分类多对多关联（单一数据源）"""
    chunk_id: int
    category_id: int
    confidence: float = 1.0                        # AI 分配置信度
    assigned_by: str = "ai"                        # ai / manual
