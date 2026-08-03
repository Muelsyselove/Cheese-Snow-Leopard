"""知识块模型"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Optional


@dataclass
class Chunk:
    """知识块 — 检索与溯源的最小单元。

    chunk_id 在 DB 中为 BIGINT；在 prompt/正则/集合中统一渲染为字符串 "chunk_<snowflake_id>"。
    详见技术文档 7.1 编码格式约定。
    """
    chunk_id: int                                   # Snowflake 业务ID（系统生成）
    content_hash: str                               # SHA-256 内容指纹（去重+完整性校验）
    doc_id: int                                     # 来源文件ID
    doc_name: str                                   # 来源文件名（冗余存储便于溯源）
    content: str                                    # 块文本内容（图片块为 VLM 描述文本）
    chunk_type: str = "text"                        # text/table/image/formula
    page_number: Optional[int] = None               # 所在页码
    char_start: Optional[int] = None                # 字符起始偏移
    char_end: Optional[int] = None                  # 字符结束偏移
    bbox: Optional[list[float]] = None              # 页面坐标框 [x, y, w, h]
    vector_id: Optional[str] = None                 # 向量库中的对应ID
    categories: list[str] = field(default_factory=list)  # 所属分类名称列表（从 chunk_category 表读取）
    created_at: Optional[str] = None                # 创建时间

    @property
    def chunk_id_str(self) -> str:
        """对外统一字符串形式 chunk_<snowflake_id>"""
        return f"chunk_{self.chunk_id}"

    @staticmethod
    def parse_chunk_id_str(cid_str: str) -> int:
        """字符串 chunk_<id> 转 BIGINT"""
        return int(cid_str.removeprefix("chunk_"))
