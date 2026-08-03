"""编码服务 — Snowflake ID 生成 + SHA-256 内容指纹

编码格式约定（贯穿全系统）：
- DB 存储：BIGINT
- prompt/正则/集合：字符串 "chunk_<snowflake_id>"
- DB 查询：int(cid_str.removeprefix("chunk_"))
"""
from __future__ import annotations

import hashlib
import threading
import time
from typing import Optional


class SnowflakeGenerator:
    """Snowflake 64 位 ID 生成器

    桌面应用为单机单进程，无需分布式 workerId 协调。
    在 config.yaml 中配置固定 worker_id（默认 1）。

    结构：[1 bit 符号位][41 bit 时间戳][10 bit workerId][12 bit 序列号]
    """

    # 各部分位数
    WORKER_ID_BITS = 10
    SEQUENCE_BITS = 12
    MAX_WORKER_ID = (1 << WORKER_ID_BITS) - 1  # 1023
    MAX_SEQUENCE = (1 << SEQUENCE_BITS) - 1     # 4095

    # 位移
    WORKER_ID_SHIFT = SEQUENCE_BITS
    TIMESTAMP_SHIFT = SEQUENCE_BITS + WORKER_ID_BITS

    # 起始时间戳（2024-01-01，可调整）
    EPOCH = 1704067200000

    def __init__(self, worker_id: int = 1, datacenter_id: int = 0):
        if worker_id < 0 or worker_id > self.MAX_WORKER_ID:
            raise ValueError(
                f"worker_id 必须在 0-{self.MAX_WORKER_ID} 之间，实际: {worker_id}"
            )
        self.worker_id = worker_id
        self.datacenter_id = datacenter_id
        self.sequence = 0
        self.last_timestamp = -1
        self._lock = threading.Lock()

    def next_id(self) -> int:
        """生成下一个 Snowflake ID"""
        with self._lock:
            timestamp = int(time.time() * 1000)
            if timestamp < self.last_timestamp:
                raise RuntimeError(
                    f"时钟回拨: 当前 {timestamp} < 上次 {self.last_timestamp}"
                )
            if timestamp == self.last_timestamp:
                self.sequence = (self.sequence + 1) & self.MAX_SEQUENCE
                if self.sequence == 0:
                    # 当前毫秒序列号耗尽，等待下一毫秒
                    timestamp = self._wait_next_millis(self.last_timestamp)
            else:
                self.sequence = 0
            self.last_timestamp = timestamp
            return (
                ((timestamp - self.EPOCH) << self.TIMESTAMP_SHIFT)
                | (self.worker_id << self.WORKER_ID_SHIFT)
                | self.sequence
            )

    def _wait_next_millis(self, last_timestamp: int) -> int:
        timestamp = int(time.time() * 1000)
        while timestamp <= last_timestamp:
            timestamp = int(time.time() * 1000)
        return timestamp


def content_hash(text: str) -> str:
    """SHA-256 内容指纹（用于去重与完整性校验）

    去重键为 (content_hash, doc_id)：同一文件内相同内容去重，跨文件不去重。
    """
    return hashlib.sha256(text.encode("utf-8")).hexdigest()
