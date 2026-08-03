"""Embedding 方案A：BGE-M3（三模态 dense + sparse + colbert）

BGE-M3 模式：sparse 向量由客户端 BGEM3FlagModel 计算 lexical_weights 后上传，
与 dense 同源，向量空间一致。
"""
from __future__ import annotations

from typing import Optional

from interfaces.embedder import Embedder, EmbeddingResult


class BgeM3Embedder:
    """BGE-M3 实现 — 三模态向量"""

    def __init__(self, model_name: str = "BAAI/bge-m3", use_fp16: bool = True):
        self.model_name = model_name
        self.use_fp16 = use_fp16
        self._model = None

    def _get_model(self):
        if self._model is None:
            from FlagEmbedding import BGEM3FlagModel
            self._model = BGEM3FlagModel(
                self.model_name,
                use_fp16=self.use_fp16
            )
        return self._model

    def encode(self, texts: list[str]) -> list[EmbeddingResult]:
        """批量编码文本（文档侧）"""
        model = self._get_model()
        result = model.encode(texts, return_dense=True, return_sparse=True,
                               return_colbert_vecs=True)
        results = []
        for i in range(len(texts)):
            results.append(EmbeddingResult(
                dense=result["dense_vecs"][i].tolist(),
                sparse={k: float(v) for k, v in result["lexical_weights"][i].items()},
                colbert=[v.tolist() for v in result["colbert_vecs"][i]]
            ))
        return results

    def encode_query(self, query: str) -> EmbeddingResult:
        """编码查询文本"""
        return self.encode([query])[0]

    @property
    def supports_sparse(self) -> bool:
        return True

    @property
    def supports_colbert(self) -> bool:
        return True
