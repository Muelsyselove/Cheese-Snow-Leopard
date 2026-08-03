"""文件管理服务 — 文档导入全流程编排

失败保留 + 状态机恢复 + 补偿队列策略：
- 失败时保留记录并标记 failed + fail_stage
- 重启后扫描 pending/failed 记录从 fail_stage 恢复
- 跨系统清理操作入 compensation_queue，由 reconciler 异步执行
"""
from __future__ import annotations

import logging
from typing import Optional

from interfaces.parser import DocumentParser, ParsedDocument
from interfaces.embedder import Embedder
from interfaces.llm import LLMClient
from models.chunk import Chunk
from models.document import Document
from utils.exceptions import StorageError

logger = logging.getLogger(__name__)


class FileService:
    """文件管理 + 导入 + 全流程编排"""

    def __init__(self, parser: DocumentParser, embedder: Embedder,
                 llm: LLMClient, snowflake, chunker, pg_repo, minio_repo,
                 qdrant_store, classify_service, compensation):
        self.parser = parser
        self.embedder = embedder
        self.llm = llm
        self.snowflake = snowflake
        self.chunker = chunker
        self.pg = pg_repo
        self.minio = minio_repo
        self.qdrant = qdrant_store
        self.classify = classify_service
        self.compensation = compensation

    def import_document(self, file_path: str) -> int:
        """文档导入全流程。
        失败时保留记录 + 标记 failed + fail_stage，清理操作入 compensation_queue。
        """
        doc_id = self.snowflake.next_id()

        # 阶段 1: 上传原始文件 + 写 document_index(parsing)
        file_path_stored = self.minio.upload(file_path)
        self.pg.insert_document(doc_id, file_path, file_path_stored,
                                 parse_status="parsing")
        try:
            # 阶段 2: 解析 + 分块 + 编码
            parsed = self.parser.parse_document(file_path)
            chunks = self.chunker.split(parsed)
            from services.encoding import content_hash
            for chunk in chunks:
                chunk.chunk_id = self.snowflake.next_id()
                chunk.doc_id = doc_id
                chunk.content_hash = content_hash(chunk.content)
            self.pg.update_parse_status(doc_id, "embedding")

            # 阶段 3: 向量化
            embeddings = self.embedder.encode([c.content for c in chunks])
            self.pg.update_parse_status(doc_id, "classifying")

            # 阶段 4: LLM 分类
            classifications = self.classify.classify(chunks)
            self.pg.update_parse_status(doc_id, "storing")

            # 阶段 5: 写 chunk_index + chunk_category
            self.pg.insert_chunks(chunks, classifications)

            # 阶段 6: 写 Qdrant（最后一步，失败时入补偿队列）
            try:
                self.qdrant.upsert(chunks, embeddings)
            except Exception as qe:
                self.compensation.enqueue("delete_pg_chunks", str(doc_id))
                self.compensation.enqueue("upsert_qdrant",
                                          ",".join(c.chunk_id_str for c in chunks))
                raise StorageError(f"Qdrant 写入失败，已入补偿队列: {qe}") from qe

            # 阶段 7: 完成
            self.pg.update_parse_status(doc_id, "completed")
            logger.info(f"文档导入成功 doc_id={doc_id}")
            return doc_id

        except Exception as e:
            # 失败保留：标记 failed + fail_stage，不删除数据
            stage = self.pg.get_parse_status(doc_id) or "parse"
            self.pg.update_parse_status(doc_id, "failed",
                                         fail_stage=stage, fail_reason=str(e))
            logger.error(f"文档导入失败 doc_id={doc_id} stage={stage}: {e}")
            raise

    def resume_interrupted(self):
        """应用启动时扫描 pending/failed 记录，从 fail_stage 恢复"""
        statuses = ["pending", "parsing", "embedding",
                    "classifying", "storing", "failed"]
        for doc in self.pg.list_by_status(statuses):
            stage = doc.fail_stage or doc.parse_status
            logger.info(f"恢复文档 doc_id={doc.doc_id} 从 stage={stage}")
            self._resume_from_stage(doc, stage)

    def _resume_from_stage(self, doc: Document, stage: str):
        """从指定阶段恢复执行（幂等：先清理该阶段半成品再重跑）"""
        # TODO: 按 stage 分支实现幂等恢复逻辑
        pass
