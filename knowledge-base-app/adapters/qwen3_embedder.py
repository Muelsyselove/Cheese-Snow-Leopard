"""Embedding 方案B：Qwen3-Embedding（纯 dense，CMTEB 中文榜首）

Qwen3-Embedding 官方推荐：query 加 instruction 前缀，document 不加。
CMTEB 榜单成绩即带 instruction 测得，不加会显著降低召回。

模型仅输出 dense，sparse 降级为 Qdrant 服务端 qdrant/bm25 模型转换。
"""
from __future__ import annotations

from typing import Optional

from interfaces.embedder import Embedder, EmbeddingResult


class Qwen3Embedder:
    """Qwen3-Embedding 实现 — 纯 dense"""

    # Qwen3-Embedding 官方推荐 query instruction 前缀
    _QUERY_INSTRUCTION = (
        "Instruct: Given a web search query, retrieve relevant passages "
        "that answer the query.\nquery: "
    )

    def __init__(self, model_name: str = "Qwen/Qwen3-Embedding-0.6B",
                 max_length: int = 8192,
                 query_instruction: Optional[str] = None):
        self.model_name = model_name
        self.max_length = max_length
        self.query_instruction = query_instruction or self._QUERY_INSTRUCTION
        self._model = None
        self._tokenizer = None

    def _load(self):
        if self._model is None:
            import torch
            from transformers import AutoModel, AutoTokenizer
            self._tokenizer = AutoTokenizer.from_pretrained(
                self.model_name, trust_remote_code=True
            )
            self._model = AutoModel.from_pretrained(
                self.model_name, trust_remote_code=True
            )
            self._torch = torch

    def encode(self, texts: list[str]) -> list[EmbeddingResult]:
        """批量编码文本（文档侧：不加 instruction）"""
        self._load()
        torch = self._torch
        inputs = self._tokenizer(
            texts, padding=True, truncation=True,
            max_length=self.max_length, return_tensors="pt"
        )
        with torch.no_grad():
            outputs = self._model(**inputs)
        dense_vecs = self._last_token_pool(
            outputs.last_hidden_state, inputs["attention_mask"]
        )
        dense_vecs = torch.nn.functional.normalize(dense_vecs, p=2, dim=1)
        return [EmbeddingResult(dense=v.tolist()) for v in dense_vecs]

    def encode_query(self, query: str) -> EmbeddingResult:
        """编码查询文本（查询侧：加 instruction 前缀）"""
        return self.encode([self.query_instruction + query])[0]

    def _last_token_pool(self, last_hidden_state, attention_mask):
        """取最后一个非 padding token 的隐藏状态作为向量"""
        import torch
        left_padding = (attention_mask[:, -1].sum() == attention_mask.shape[0])
        if left_padding:
            return last_hidden_state[:, -1]
        sequence_lengths = attention_mask.sum(dim=1) - 1
        return last_hidden_state[
            torch.arange(last_hidden_state.size(0)), sequence_lengths
        ]

    @property
    def supports_sparse(self) -> bool:
        return False

    @property
    def supports_colbert(self) -> bool:
        return False
