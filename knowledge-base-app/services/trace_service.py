"""溯源解析服务（非 AI）— 系统级溯源核心

完全不依赖 AI，由系统代码完成：
1. 正则提取 AI 输出中的块 ID（字符串形式 chunk_<id>）
2. 过滤幻觉 ID（仅保留 retrieved_chunk_ids 集合内的）
3. 查询 DB 映射回原始文件/页码/坐标
"""
from __future__ import annotations

import logging
import re
from typing import Optional

from utils.exceptions import TraceError

logger = logging.getLogger(__name__)

# 与 7.1 编码格式约定一致：匹配 【chunk_<snowflake_id>】
_CITATION_RE = re.compile(r'【(chunk_\d+)】')


def trace_references(answer: str, retrieved_chunk_ids: set) -> list:
    """从 AI 输出中解析块 ID，映射回原始文件。

    Args:
        answer: AI 生成的答案文本
        retrieved_chunk_ids: 本轮检索命中的 chunk_id 字符串集合（格式 "chunk_<id>"）
    Returns:
        结构化引用列表，过滤掉 AI 幻觉的 ID
    Raises:
        TraceError: DB 查询失败时抛出
    """
    # 1. 正则提取答案中的所有块ID（字符串形式 chunk_<id>）
    cited_ids = set(_CITATION_RE.findall(answer))

    # 2. 过滤幻觉ID——仅采纳检索结果集内的ID
    valid_ids = cited_ids & retrieved_chunk_ids

    # 3. 查询数据库，映射回原始文件与位置
    references = []
    for cid_str in valid_ids:
        # 字符串转 BIGINT 用于 DB 查询
        chunk_id_int = int(cid_str.removeprefix("chunk_"))
        try:
            # TODO: 替换为真实的 db 查询
            chunk = _query_chunk(chunk_id_int)
        except Exception as e:
            raise TraceError(
                f"溯源 DB 查询失败 chunk_id={cid_str}: {e}"
            ) from e

        if chunk is None:
            # ID 在集合内但 DB 查不到，记录但不阻断
            logger.warning(f"chunk_id={cid_str} 在集合内但 DB 查不到")
            continue

        references.append({
            "chunk_id": cid_str,                  # 对外统一返回字符串形式
            "source_file": chunk.doc_name,        # 参考了哪篇文章
            "page": chunk.page_number,            # 第几页
            "position": chunk.bbox,               # 页面坐标
            "type": chunk.chunk_type,             # text/image/table
            "excerpt": chunk.content[:200]        # 内容摘要
        })

    return references


def trace_references_fallback(answer: str, retrieved_chunk_ids: set) -> list:
    """回退机制：AI 未标注任何引用时，使用 retrieved_chunks 作为引用来源"""
    references = []
    for cid_str in retrieved_chunk_ids:
        chunk_id_int = int(cid_str.removeprefix("chunk_"))
        try:
            chunk = _query_chunk(chunk_id_int)
        except Exception as e:
            raise TraceError(
                f"溯源 DB 查询失败 chunk_id={cid_str}: {e}"
            ) from e
        if chunk is None:
            continue
        references.append({
            "chunk_id": cid_str,
            "source_file": chunk.doc_name,
            "page": chunk.page_number,
            "position": chunk.bbox,
            "type": chunk.chunk_type,
            "excerpt": chunk.content[:200]
        })
    return references


def _query_chunk(chunk_id: int):
    """查询 chunk_index 表（骨架：返回 None，集成时接入真实 DB）"""
    # TODO: 接入真实 PG 查询
    return None
