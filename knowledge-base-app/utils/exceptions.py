"""异常体系 — 所有业务异常的基类与子类"""
from __future__ import annotations


class KnowledgeBaseError(Exception):
    """所有业务异常的基类"""
    pass


class ParseError(KnowledgeBaseError):
    """文档解析失败"""
    pass


class EmbedError(KnowledgeBaseError):
    """向量化失败"""
    pass


class RetrievalError(KnowledgeBaseError):
    """检索失败"""
    pass


class LLMError(KnowledgeBaseError):
    """LLM API 调用失败"""
    pass


class StorageError(KnowledgeBaseError):
    """存储系统（MinIO/PG/Qdrant）写入失败"""
    pass


class TraceError(KnowledgeBaseError):
    """溯源解析失败（如 DB 查询失败）"""
    pass
