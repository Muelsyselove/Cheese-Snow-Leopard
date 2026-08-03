"""向量库重建 Worker — Embedding 模型切换后手动触发

技术文档 11.3 重建步骤：
① 新建 collection（按新 Embedding 维度）
② 全量重编码所有 chunk_index.content
③ 切换别名指向新 collection
④ 删除旧 collection

关键决策（技术文档 11.3 问题7）：
- Embedding 切换分两步——①热更新仅切配置并标记 collection 为 dirty，不立即重建；
  ②重建需用户在 UI 显式点击"重建向量库"按钮触发，进 QThread 队列带进度反馈。

重建流程为原子性设计：中途失败时旧 collection 仍可用，新 collection 可清理后重试。
"""
from __future__ import annotations

import logging
import time
from typing import Optional

from PySide6.QtCore import QThread, Signal

logger = logging.getLogger(__name__)


class RebuildWorker(QThread):
    """向量库重建后台 Worker

    依赖注入（构造时传入）：
    - pg_repo: 读取 chunk_index 全量内容
    - embedder: 新的 Embedder 实例（已按新配置创建）
    - qdrant_store: 新的 QdrantStore 实例（已按新配置创建）
    - old_collection: 旧 collection 名（重建成功后删除）
    - batch_size: 批量编码/upsert 大小（默认 100，控制内存峰值）
    """

    progress = Signal(int, str)     # (percent, message)
    finished = Signal(bool)         # 是否成功
    error = Signal(str)

    def __init__(self, pg_repo=None, embedder=None, qdrant_store=None,
                 old_collection: str = "", batch_size: int = 100,
                 config=None, factory=None):
        """
        Args:
            pg_repo: PostgreSQL 仓库（读取 chunk_index）
            embedder: 新 Embedder 实例
            qdrant_store: 新 QdrantStore 实例（指向新 collection）
            old_collection: 旧 collection 名（成功后删除）
            batch_size: 批量处理大小
            config/factory: 兼容旧签名（已废弃，保留向后兼容）
        """
        super().__init__()
        self.pg = pg_repo
        self.embedder = embedder
        self.qdrant = qdrant_store
        self.old_collection = old_collection
        self.batch_size = batch_size
        # 兼容旧签名
        self.config = config
        self.factory = factory

    def run(self):
        """执行重建流程（QThread 入口）"""
        try:
            self._rebuild()
            self.progress.emit(100, "向量库重建完成")
            self.finished.emit(True)
        except Exception as e:
            logger.error(f"向量库重建失败: {e}", exc_info=True)
            self.error.emit(str(e))
            self.finished.emit(False)

    def _rebuild(self):
        """重建核心流程（同步，供 Worker.run 和单测直接调用）"""
        if self.pg is None or self.embedder is None or self.qdrant is None:
            raise ValueError("pg_repo / embedder / qdrant_store 不可为空")

        self.progress.emit(0, "开始重建向量库")

        # ① 统计总量
        total = self.pg.count_chunks()
        if total == 0:
            self.progress.emit(100, "无知识块，跳过重建")
            return
        logger.info(f"向量库重建开始，共 {total} 个知识块")

        # ② 确保 collection 存在（按新维度创建）
        # 维度由首条 embedding 探测，或由 embedder.dim 属性提供
        dim = getattr(self.embedder, "dim", None)
        if dim is None:
            # 探测：编码一条样本获取维度
            sample = self.embedder.encode(["维度探测"])
            if not sample:
                raise RuntimeError("Embedder 探测维度失败：返回空结果")
            dim = len(sample[0].dense)
        self.qdrant.ensure_collection(dim)
        self.progress.emit(5, f"新 collection 已创建（维度 {dim}）")

        # ③ 全量重编码 + upsert（分批）
        processed = 0
        all_chunks = self.pg.list_all_chunks()
        for i in range(0, len(all_chunks), self.batch_size):
            batch = all_chunks[i:i + self.batch_size]
            # 编码（embedder.encode 批量）
            texts = [c.content for c in batch]
            embeddings = self.embedder.encode(texts)
            if len(embeddings) != len(batch):
                raise RuntimeError(
                    f"编码数量不匹配：期望 {len(batch)}，实际 {len(embeddings)}"
                )
            # 写入新 collection
            self.qdrant.upsert(batch, embeddings)

            processed += len(batch)
            percent = 5 + int(90 * processed / total)
            self.progress.emit(
                min(percent, 95),
                f"已重编码 {processed}/{total} 个知识块"
            )

        # ④ 删除旧 collection（成功后）
        if self.old_collection and self.old_collection != self.qdrant.collection:
            try:
                client = self.qdrant._get_client()
                client.delete_collection(self.old_collection)
                logger.info(f"旧 collection 已删除: {self.old_collection}")
                self.progress.emit(98, f"旧 collection 已删除: {self.old_collection}")
            except Exception as e:
                # 旧 collection 删除失败不阻塞重建成功（可后续手动清理）
                logger.warning(f"删除旧 collection 失败（不阻塞）: {e}")

        logger.info(f"向量库重建完成，共重编码 {processed} 个知识块")
