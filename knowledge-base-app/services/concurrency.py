"""并发控制 — 全局任务队列 + GPU 信号量 + LLM 令牌桶

批量导入时多个 ParseWorker 并发跑 VLM 推理易引发 GPU OOM，
LLM API 并发过高触发 429。需全局并发控制。
"""
from __future__ import annotations

import threading
from collections import deque
from time import monotonic


class GlobalTaskQueue:
    """全局导入任务队列，限制并发数，防止资源过载"""

    def __init__(self, max_concurrent: int):
        self._sem = threading.Semaphore(max_concurrent)
        self._queue: deque = deque()
        self._lock = threading.Lock()

    def submit(self, task):
        """提交任务到队列"""
        with self._lock:
            self._queue.append(task)

    def worker_loop(self):
        """工作循环：从队列取任务，受信号量限制并发"""
        while True:
            with self._lock:
                if not self._queue:
                    break
                task = self._queue.popleft()
            with self._sem:  # 限制并发
                task.run()


class GpuSemaphore:
    """GPU 信号量：限制同时在 GPU 上跑的 VLM 推理数（单 GPU 建议 1）"""

    def __init__(self, max_gpu_tasks: int = 1):
        self._sem = threading.Semaphore(max_gpu_tasks)

    def acquire(self):
        self._sem.acquire()

    def release(self):
        self._sem.release()

    def __enter__(self):
        self.acquire()
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        self.release()


class LlmTokenBucket:
    """LLM API 令牌桶：按 RPM + TPM 双维限流，避免 429"""

    def __init__(self, rpm: int, tpm: int):
        self._rpm = rpm
        self._tpm = tpm
        self._req_count = 0
        self._token_count = 0
        self._window_start = monotonic()
        self._lock = threading.Lock()

    def acquire(self, est_tokens: int):
        """获取令牌（按请求数 + 估算 token 数双维限流）"""
        with self._lock:
            now = monotonic()
            if now - self._window_start >= 60:
                self._req_count = 0
                self._token_count = 0
                self._window_start = now
            if (self._req_count >= self._rpm or
                    self._token_count + est_tokens > self._tpm):
                wait = 60 - (now - self._window_start)
                if wait > 0:
                    threading.Event().wait(wait)
                self._req_count = 0
                self._token_count = 0
                self._window_start = monotonic()
            self._req_count += 1
            self._token_count += est_tokens
