"""文档生命周期管理 — 删除/更新/分类变更链路

所有跨系统清理操作入 compensation_queue，由 reconciler 异步执行保证最终一致。
"""
from __future__ import annotations

import logging
import time
from typing import Optional

logger = logging.getLogger(__name__)


class LifecycleService:
    """文档生命周期管理"""

    def __init__(self, pg_repo, qdrant_store, minio_repo, compensation,
                 file_service=None, factory=None, embedder=None):
        self.pg = pg_repo
        self.qdrant = qdrant_store
        self.minio = minio_repo
        self.compensation = compensation
        self.file_service = file_service
        self.factory = factory
        self.embedder = embedder

    def delete_document(self, doc_id: int):
        """删除文档：级联清理 PG chunk_index + chunk_category + Qdrant 向量 + MinIO 原始文件。
        清理操作入 compensation_queue，由 reconciler 异步执行保证最终一致。
        """
        # 1. 标记 document_index.parse_status = 'deleting'（软删除起点）
        self.pg.update_parse_status(doc_id, "deleting")
        # 2. 入队清理任务（reconciler 逆序执行：Qdrant → PG → MinIO）
        # 注意：delete_qdrant 只存 doc_id，由 reconciler 执行时再解析 chunk_id 列表，
        # 避免把全量 chunk_id 拼进 target_id（VARCHAR(100)）导致长度溢出。
        self.compensation.enqueue("delete_qdrant", str(doc_id))
        self.compensation.enqueue("delete_pg_chunks", str(doc_id))  # 含 chunk_category 关联
        self.compensation.enqueue("delete_pg_doc", str(doc_id))
        file_path = self.pg.get_file_path(doc_id)
        # 若文件路径缺失（如 document_index 记录已不存在），跳过 MinIO 清理，
        # 避免把 null 写入 target_id 触发 NOT NULL 约束报错。
        if file_path:
            self.compensation.enqueue("delete_minio", file_path)
        logger.info(f"文档删除任务已入队 doc_id={doc_id}")

    def update_document(self, doc_id: int, new_file_path: str) -> int:
        """更新文档：等价于 delete + import。
        重新解析生成新 chunk_id，旧 chunk 全部清理。
        期间检索可能命中新旧块，可接受（最终一致）。
        """
        self.delete_document(doc_id)
        return self.file_service.import_document(new_file_path)

    def update_chunk_categories(self, chunk_id: int, category_ids: list[int]):
        """分类变更：更新 chunk_category 关联表（单一数据源），
        同步刷新 Qdrant payload 的 categories 字段。
        """
        self.pg.upsert_chunk_categories(chunk_id, category_ids)
        cats = self.pg.get_category_names(chunk_id)  # 从关联表读取
        cid_str = f"chunk_{chunk_id}"
        self.qdrant.update_payload(cid_str, {"categories": cats})
        logger.info(f"分类变更已同步 chunk_id={cid_str}")

    # ========== 知识库全量重置 ==========

    def reset_all(self) -> bool:
        """清空全部知识数据：PG 表 + Qdrant collection + 对象存储。

        每步独立 try/except 记录日志，互不影响；任一步失败返回 False。
        """
        ok = True
        try:
            self.pg.clear_all_knowledge()
            logger.info("PG 知识数据已清空")
        except Exception as e:
            ok = False
            logger.error(f"PG 知识数据清空失败: {e}", exc_info=True)
        try:
            self.qdrant.drop_collection()
            logger.info("Qdrant collection 已删除")
        except Exception as e:
            ok = False
            logger.error(f"Qdrant collection 删除失败: {e}", exc_info=True)
        try:
            self.minio.clear()
            logger.info("对象存储已清空")
        except Exception as e:
            ok = False
            logger.error(f"对象存储清空失败: {e}", exc_info=True)
        return ok

    # ========== 向量库重建（技术文档 11.3 问题7） ==========

    def rebuild_vector_store(self, new_embedder=None, new_collection_name: Optional[str] = None,
                             batch_size: int = 100):
        """触发向量库重建（用户点击'重建向量库'按钮调用）。

        原子性设计：新建 collection → 全量重编码 → 切换 → 删除旧 collection。
        中途失败时旧 collection 仍可用，新 collection 可清理后重试。

        Args:
            new_embedder: 新 Embedder 实例（None 时用 factory 按当前配置创建）
            new_collection_name: 新 collection 名（None 时自动生成带时间戳后缀，
                                 避免与旧 collection 同名）
            batch_size: 批量编码/upsert 大小

        Returns:
            RebuildWorker 实例（已配置，未启动）。调用方连接 progress/finished/error
            信号后调用 .start()。
        """
        from workers.rebuild_worker import RebuildWorker
        from adapters.qdrant_store import QdrantStore

        # ① 新 embedder 实例
        embedder = new_embedder
        if embedder is None:
            if self.factory is None:
                raise ValueError("new_embedder 与 factory 不能同时为空")
            embedder = self.factory.create_embedder()

        # ② 新 qdrant_store 指向新 collection（与旧 collection 隔离）
        if new_collection_name is None:
            new_collection_name = f"{self.qdrant.collection}_rebuild_{int(time.time())}"

        new_qdrant = QdrantStore(
            host=self.qdrant.host, port=self.qdrant.port,
            collection=new_collection_name,
            sparse_support=embedder.supports_sparse
        )

        old_collection = self.qdrant.collection
        worker = RebuildWorker(
            pg_repo=self.pg, embedder=embedder, qdrant_store=new_qdrant,
            old_collection=old_collection, batch_size=batch_size
        )
        logger.info(f"向量库重建 worker 已创建: old={old_collection}, "
                    f"new={new_collection_name}, batch_size={batch_size}")
        return worker
