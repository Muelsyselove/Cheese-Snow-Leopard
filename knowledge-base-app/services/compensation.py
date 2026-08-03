"""补偿队列 reconciler — 保证跨系统最终一致性

后台定时扫描 compensation_queue，执行待处理操作。
每步独立 try/except，确保单步失败不阻断后续步骤。
"""
from __future__ import annotations

import logging
import threading
from time import sleep

logger = logging.getLogger(__name__)

MAX_RETRIES = 5


class CompensationReconciler:
    """补偿队列 reconciler"""

    def __init__(self, pg_repo, qdrant_store=None, minio_repo=None):
        self.pg = pg_repo
        self.qdrant = qdrant_store
        self.minio = minio_repo
        self._stop_event = threading.Event()

    def enqueue(self, op_type: str, target_id: str):
        """入队补偿任务"""
        self.pg.enqueue_compensation(op_type, target_id)

    def run_once(self):
        """执行一轮补偿任务扫描"""
        for task in self.pg.list_pending_compensations():
            try:
                self._execute(task)
                self.pg.mark_compensation_done(task.id)
            except Exception as e:
                task.retries += 1
                if task.retries >= MAX_RETRIES:
                    self.pg.mark_compensation_failed(task.id, str(e))
                    logger.error(f"补偿任务最终失败 {task.id}: {e}")
                else:
                    self.pg.update_compensation_retries(task.id, task.retries)
                    logger.warning(
                        f"补偿任务重试 {task.id} (第 {task.retries} 次): {e}"
                    )

    def run_forever(self, interval: int = 30):
        """后台循环执行（间隔 30 秒）"""
        while not self._stop_event.is_set():
            try:
                self.run_once()
            except Exception as e:
                logger.error(f"补偿 reconciler 异常: {e}")
            self._stop_event.wait(interval)

    def stop(self):
        self._stop_event.set()

    def _execute(self, task):
        """执行单个补偿任务。每个分支独立，单步失败不影响其他。"""
        if task.op_type == "delete_qdrant":
            chunk_ids = task.target_id.split(",")
            self.qdrant.delete(chunk_ids)
        elif task.op_type == "delete_pg_chunks":
            self.pg.delete_chunks_by_doc(int(task.target_id))
        elif task.op_type == "delete_pg_doc":
            self.pg.delete_document(int(task.target_id))
        elif task.op_type == "delete_minio":
            self.minio.delete(task.target_id)
        elif task.op_type == "upsert_qdrant":
            # Qdrant 重试需要原始 chunks 数据，这里仅标记，由 FileService 重跑
            logger.info(f"Qdrant upsert 补偿需 FileService 重跑: {task.target_id}")
        else:
            logger.warning(f"未知补偿操作类型: {task.op_type}")
