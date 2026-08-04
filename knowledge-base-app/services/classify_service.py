"""AI 分类服务 — 多归属分类

需求⑤：一个知识可属于多个分类。
chunk_category 关联表为单一数据源，Qdrant payload 在写入/更新时从关联表读取。
"""
from __future__ import annotations

import json
import logging
from typing import Optional

from interfaces.llm import LLMClient
from models.chunk import Chunk
from models.category import ChunkCategory

logger = logging.getLogger(__name__)


class ClassifyService:
    """AI 分类 + 多归属"""

    def __init__(self, llm: LLMClient, category_repo=None, snowflake=None):
        self.llm = llm
        self.category_repo = category_repo
        self.snowflake = snowflake

    def classify(self, chunks: list[Chunk]) -> list[list[ChunkCategory]]:
        """对知识块批量分类，返回每个块的分类关联列表"""
        # 获取所有可选分类
        categories = self.category_repo.list_all_categories() if self.category_repo else []
        if not categories:
            return [[] for _ in chunks]

        category_names = [c.name for c in categories]
        results = []
        for chunk in chunks:
            classifications = self._classify_one(chunk, category_names, categories)
            results.append(classifications)
        return results

    def _classify_one(self, chunk: Chunk, category_names: list[str],
                      categories) -> list[ChunkCategory]:
        """对单个知识块分类（块已由分块器分段，超长文档天然分段提交）。

        参考现有分类，允许一个块同时属于多个分类。
        """
        prompt = (
            f"请对以下知识片段进行分类提取。可参考现有分类，允许多选（可同时属于多个分类）。\n"
            f"现有分类: {category_names}\n\n"
            f"知识片段: {chunk.content}\n\n"
            f"返回 JSON 格式: [{{\"category\": \"分类名\", \"confidence\": 0.95}}]"
        )
        try:
            resp = self.llm.chat([
                {"role": "system", "content": "你是知识分类助手，严格返回 JSON"},
                {"role": "user", "content": prompt}
            ])
            content = resp["content"]
            # 解析 JSON
            import re
            match = re.search(r'\[.*\]', content, re.DOTALL)
            if not match:
                return []
            items = json.loads(match.group())
            result = []
            cat_map = {c.name: c.category_id for c in categories}
            for item in items:
                cat_name = item.get("category", "")
                confidence = float(item.get("confidence", 0.5))
                if cat_name in cat_map and confidence >= 0.5:
                    result.append(ChunkCategory(
                        chunk_id=chunk.chunk_id,
                        category_id=cat_map[cat_name],
                        confidence=confidence,
                        assigned_by="ai"
                    ))
            return result
        except Exception as e:
            logger.warning(f"分类失败 chunk_id={chunk.chunk_id}: {e}")
            return []
