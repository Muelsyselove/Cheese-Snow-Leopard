"""知识库桌面应用 — 接口隔离层。

业务逻辑仅依赖此包中的 Protocol，不 import 任何第三方库。
第三方库仅在 adapters/ 中引入，通过依赖注入传入业务层。
"""
from interfaces.parser import DocumentParser, ParsedDocument, ImageBlock
from interfaces.embedder import Embedder, EmbeddingResult
from interfaces.vectorstore import VectorStore
from interfaces.llm import LLMClient

__all__ = [
    "DocumentParser",
    "ParsedDocument",
    "ImageBlock",
    "Embedder",
    "EmbeddingResult",
    "VectorStore",
    "LLMClient",
]
