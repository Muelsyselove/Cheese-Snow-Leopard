"""文档生命周期管理 — 删除/更新/分类变更链路

所有跨系统清理操作入 compensation_queue，由 reconciler 异步执行保证最终一致。
"""
from __future__ import annotations

import logging

logger = logging.getLogger(__name__)


class LifecycleService:
    """文档生命周期管理"""

    def __init__(self, pg_repo, qdrant_store, minio_repo, compensation,
                 file_service=None):
        self.pg = pg_repo
        self.qdrant = qdrant_store
        self.minio = minio_repo
        self.compensation = compensation
        self.file_service = file_service

    def delete_document(self, doc_id: int):
        """删除文档：级联清理 PG chunk_index + chunk_category + Qdrant 向量 + MinIO 原始文件。
        清理操作入 compensation_queue，由 reconciler 异步执行保证最终一致。
        """
        # 1. 标记 document_index.parse_status = 'deleting'（软删除起点）
        self.pg.update_parse_status(doc_id, "deleting")
        # 2. 入队清理任务（reconciler 逆序执行：Qdrant → PG → MinIO）
        chunk_ids = self.pg.list_chunk_ids(doc_id)
        chunk_id_strs = [f"chunk_{cid}" for cid in chunk_ids]
        self.compensation.enqueue("delete_qdrant",
                                  ",".join(chunk_id_strs))
        self.compensation.enqueue("delete_pg_chunks", str(doc_id))  # 含 chunk_category 关联
        self.compensation.enqueue("delete_pg_doc", str(doc_id))
        file_path = self.pg.get_file_path(doc_id)
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
