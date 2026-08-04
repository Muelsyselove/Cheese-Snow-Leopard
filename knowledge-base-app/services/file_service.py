"""文件管理服务 — 文档导入全流程编排

失败保留 + 状态机恢复 + 补偿队列策略：
- 失败时保留记录并标记 failed + fail_stage
- 重启后扫描 pending/failed 记录从 fail_stage 恢复
- 跨系统清理操作入 compensation_queue，由 reconciler 异步执行
"""
from __future__ import annotations

import logging
import os
import tempfile
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

    def list_documents(self) -> list[Document]:
        """返回全部已导入文档（用于启动时恢复文件树）"""
        try:
            return self.pg.list_all_documents()
        except Exception as e:
            logger.error(f"查询文档列表失败: {e}")
            return []

    def import_document(self, file_path: str, progress_cb=None) -> int:
        """文档导入全流程。
        失败时保留记录 + 标记 failed + fail_stage，清理操作入 compensation_queue。

        Args:
            file_path: 待导入文件路径
            progress_cb: 可选进度回调 callable(percent, message)，用于上报阶段进度
        """
        from services.encoding import content_hash as compute_hash

        def _report(percent: int, msg: str):
            if progress_cb is not None:
                try:
                    progress_cb(percent, msg)
                except Exception:
                    pass

        doc_id = self.snowflake.next_id()

        # 阶段 1: 上传原始文件 + 写 document_index(parsing)
        _report(5, "上传文件")
        file_path_stored = self.minio.upload(file_path)
        # 计算文件级 content_hash + 提取元数据
        file_name = os.path.basename(file_path)
        file_type = os.path.splitext(file_name)[1].lstrip(".").lower() or "unknown"
        with open(file_path, "rb") as f:
            file_hash = compute_hash(f.read().decode("utf-8", errors="replace"))
        self.pg.insert_document(
            doc_id, file_name, file_path_stored, file_type, file_hash,
            parse_status="parsing"
        )
        try:
            # 阶段 2: 解析 + 分块
            _report(15, "解析文档")
            parsed = self.parser.parse_document(file_path)
            chunks = self.chunker.split(parsed)
            for chunk in chunks:
                chunk.chunk_id = self.snowflake.next_id()
                chunk.doc_id = doc_id
                chunk.doc_name = file_name
                chunk.content_hash = compute_hash(chunk.content)
            if not chunks:
                _report(100, "完成（无有效内容）")
                self.pg.update_parse_status(doc_id, "completed")
                logger.info(f"文档导入成功（空内容） doc_id={doc_id}")
                return doc_id

            # 阶段 3: AI 分类（参考现有分类、允许多分类；分块已分段，逐个提交）
            _report(45, "AI 分类")
            self.pg.update_parse_status(doc_id, "classifying")
            classifications = self.classify.classify(chunks)

            # 阶段 4: 向量化（基于提取出的知识块内容）
            _report(70, "向量化")
            self.pg.update_parse_status(doc_id, "embedding")
            embeddings = self.embedder.encode([c.content for c in chunks])

            # 阶段 5: 写 chunk_index + chunk_category
            _report(80, "写入存储")
            self.pg.update_parse_status(doc_id, "storing")
            self.pg.insert_chunks(chunks, classifications)

            # 阶段 6: 写 Qdrant（先确保 collection 存在且 schema 匹配，失败时入补偿队列）
            _report(90, "写入向量库")
            try:
                dim = len(embeddings[0].dense) if embeddings else 0
                self.qdrant.ensure_collection(dim)
                self.qdrant.upsert(chunks, embeddings)
            except Exception as qe:
                self.compensation.enqueue("delete_pg_chunks", str(doc_id))
                self.compensation.enqueue("upsert_qdrant",
                                          ",".join(c.chunk_id_str for c in chunks))
                raise StorageError(f"Qdrant 写入失败，已入补偿队列: {qe}") from qe

            # 阶段 7: 完成
            _report(100, "完成")
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
        """应用启动时扫描 pending/failed 记录，从 fail_stage 恢复。"""
        statuses = ["pending", "parsing", "embedding",
                    "classifying", "storing", "failed"]
        for doc in self.pg.list_by_status(statuses):
            stage = doc.fail_stage or doc.parse_status
            logger.info(f"恢复文档 doc_id={doc.doc_id} 从 stage={stage}")
            try:
                self._resume_from_stage(doc, stage)
            except Exception as e:
                # 单文档恢复失败不影响其他文档
                logger.error(f"恢复文档失败 doc_id={doc.doc_id} stage={stage}: {e}",
                             exc_info=True)
                self.pg.update_parse_status(
                    doc.doc_id, "failed",
                    fail_stage=stage, fail_reason=f"resume: {e}"
                )

    # ------------------------------------------------------------------
    # 幂等恢复：按 stage 清理半成品后从该阶段起点重跑
    # ------------------------------------------------------------------
    # 状态机重跑起点映射（fail_stage → 重跑起点阶段）：
    #   pending/parsing    → 解析阶段（chunks 尚未生成，无需清理）
    #   embedding          → 重新解析+分块+编码（chunks 在内存，PG/Qdrant 无半成品）
    #   classifying        → 重新分类（embeddings 已生成但未落库，无需清理）
    #   storing/failed@storing → 清理已写入的 chunk_index + Qdrant 半成品后重新写入
    #   completed          → 跳过
    #
    # 设计原则：
    # - chunk_index / Qdrant 是"已完成产物"，storing 阶段中途失败需清理后重跑
    # - parsing/embedding/classifying 阶段产物仅在内存或临时态，重跑天然幂等
    # - 清理走 pg.delete_chunks_by_doc + qdrant.delete，避免补偿队列时序问题
    # ------------------------------------------------------------------

    # storing 阶段失败需清理的半成品范围
    _STAGES_NEED_CLEANUP = {"storing", "failed"}

    def _resume_from_stage(self, doc: Document, stage: str):
        """从指定阶段恢复执行（幂等：先清理该阶段半成品再重跑）。

        Args:
            doc: 文档元数据（含 file_path 指向 MinIO 中的原始文件）
            stage: 失败时记录的阶段（pending/parsing/embedding/classifying/storing）
        """
        # completed 文档不恢复
        if stage in ("completed", "deleting"):
            logger.info(f"文档无需恢复 doc_id={doc.doc_id} stage={stage}")
            return

        # storing 阶段失败：chunk_index / Qdrant 可能有半成品，先清理
        if stage in self._STAGES_NEED_CLEANUP:
            self._cleanup_doc_chunks(doc.doc_id)

        # 重跑：从 MinIO 拉回原始文件，重新走 parse→embed→classify→store 全流程
        local_path = self._fetch_original_file(doc)
        try:
            self._rerun_pipeline(doc, local_path)
        finally:
            # 清理临时文件
            try:
                if local_path and os.path.exists(local_path):
                    os.remove(local_path)
            except OSError as e:
                logger.warning(f"清理临时文件失败 {local_path}: {e}")

    def _cleanup_doc_chunks(self, doc_id: int):
        """清理文档在 PG chunk_index + Qdrant 中的半成品（幂等）。

        storing 阶段中途失败时，chunk_index 可能已部分写入、Qdrant 可能未写入。
        两者都按 doc_id 范围清理，已删除的不会报错。
        """
        chunk_ids = self.pg.list_chunk_ids(doc_id)
        if chunk_ids:
            cid_strs = [f"chunk_{cid}" for cid in chunk_ids]
            try:
                self.qdrant.delete(cid_strs)
            except Exception as e:
                # Qdrant 清理失败不阻塞 PG 清理（可能 Qdrant 还没写入）
                logger.warning(f"Qdrant 清理失败 doc_id={doc_id}（可能未写入）: {e}")
            self.pg.delete_chunks_by_doc(doc_id)
            logger.info(f"已清理半成品 doc_id={doc_id} chunks={len(chunk_ids)}")

    def _fetch_original_file(self, doc: Document) -> str:
        """从 MinIO 拉回原始文件到本地临时路径，供重新解析。"""
        try:
            from utils.paths import get_tmp_dir
            base_tmp = get_tmp_dir()
        except Exception:
            base_tmp = None
        if base_tmp:
            import tempfile as _tf
            tmp_dir = _tf.mkdtemp(prefix="resume_", dir=base_tmp)
        else:
            tmp_dir = tempfile.mkdtemp(prefix="resume_")
        local_path = os.path.join(tmp_dir, doc.file_name)
        self.minio.download(doc.file_path, local_path)
        logger.debug(f"已拉回原始文件 doc_id={doc.doc_id} → {local_path}")
        return local_path

    def _rerun_pipeline(self, doc: Document, local_path: str):
        """重跑 parse→embed→classify→store 全流程（复用 import_document 逻辑）。

        与首次导入的区别：
        - 不重新生成 doc_id，复用原 doc_id
        - 不重新上传 MinIO（文件已在）
        - 不重新 insert_document（document_index 已存在）
        - 失败仍标记 failed + fail_stage，成功置 completed
        """
        from services.encoding import content_hash as compute_hash

        doc_id = doc.doc_id
        file_name = doc.file_name

        # 标记 parsing（重置状态机）
        self.pg.update_parse_status(doc_id, "parsing",
                                     fail_stage=None, fail_reason=None)
        try:
            # 阶段 2: 解析 + 分块
            parsed = self.parser.parse_document(local_path)
            chunks = self.chunker.split(parsed)
            for chunk in chunks:
                chunk.chunk_id = self.snowflake.next_id()
                chunk.doc_id = doc_id
                chunk.doc_name = file_name
                chunk.content_hash = compute_hash(chunk.content)
            if not chunks:
                self.pg.update_parse_status(doc_id, "completed")
                return

            # 阶段 3: AI 分类
            self.pg.update_parse_status(doc_id, "classifying")
            classifications = self.classify.classify(chunks)

            # 阶段 4: 向量化
            self.pg.update_parse_status(doc_id, "embedding")
            embeddings = self.embedder.encode([c.content for c in chunks])

            # 阶段 5: 写 chunk_index + chunk_category
            self.pg.update_parse_status(doc_id, "storing")
            self.pg.insert_chunks(chunks, classifications)

            # 阶段 6: 写 Qdrant（先确保 collection 存在且 schema 匹配）
            try:
                dim = len(embeddings[0].dense) if embeddings else 0
                self.qdrant.ensure_collection(dim)
                self.qdrant.upsert(chunks, embeddings)
            except Exception as qe:
                self.compensation.enqueue("delete_pg_chunks", str(doc_id))
                self.compensation.enqueue("upsert_qdrant",
                                          ",".join(c.chunk_id_str for c in chunks))
                raise StorageError(f"Qdrant 写入失败，已入补偿队列: {qe}") from qe

            # 阶段 7: 完成
            self.pg.update_parse_status(doc_id, "completed")
            logger.info(f"文档恢复成功 doc_id={doc_id}")
        except Exception as e:
            stage = self.pg.get_parse_status(doc_id) or "parse"
            self.pg.update_parse_status(doc_id, "failed",
                                         fail_stage=stage, fail_reason=str(e))
            logger.error(f"文档恢复失败 doc_id={doc_id} stage={stage}: {e}")
            raise
