"""业务逻辑层（自研核心）

所有业务逻辑在此层实现，仅依赖 interfaces/ 中的 Protocol，不 import 任何 adapter。
"""
from services.encoding import SnowflakeGenerator, content_hash
from services.file_service import FileService
from services.classify_service import ClassifyService
from services.rag_service import RagService
from services.trace_service import trace_references, trace_references_fallback
from services.lifecycle_service import LifecycleService
from services.concurrency import (
    GlobalTaskQueue, GpuSemaphore, LlmTokenBucket
)
from services.compensation import CompensationReconciler
from services.chunker import StructureAwareChunker, CharTokenCounter

__all__ = [
    "SnowflakeGenerator", "content_hash",
    "FileService", "ClassifyService", "RagService",
    "trace_references", "trace_references_fallback",
    "LifecycleService",
    "GlobalTaskQueue", "GpuSemaphore", "LlmTokenBucket",
    "CompensationReconciler",
    "StructureAwareChunker", "CharTokenCounter",
]
