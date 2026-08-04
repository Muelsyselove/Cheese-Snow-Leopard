"""Embedding 方案A：BGE-M3（三模态 dense + sparse + colbert）

BGE-M3 模式：sparse 向量由客户端 BGEM3FlagModel 计算 lexical_weights 后上传，
与 dense 同源，向量空间一致。
"""
from __future__ import annotations

import logging
import os
import threading
from typing import Optional, Callable

from interfaces.embedder import Embedder, EmbeddingResult

logger = logging.getLogger(__name__)


class BgeM3Embedder:
    """BGE-M3 实现 — 三模态向量"""

    # 模型加载锁：避免多个导入线程并发加载同一模型
    _load_lock = threading.Lock()

    def __init__(self, model_name: str = "BAAI/bge-m3", use_fp16: bool = True):
        self.model_name = model_name
        self.use_fp16 = use_fp16
        self._model = None

    @staticmethod
    def _resolve_fp16(use_fp16: bool) -> bool:
        """CPU 环境下禁用 fp16，避免加载/推理卡死"""
        if not use_fp16:
            return False
        try:
            import torch
            return torch.cuda.is_available()
        except Exception:
            return False

    # 镜像下载时跳过非必需文件（.DS_Store 等隐蔽文件在镜像端返回 403，
    # 会导致整个 snapshot_download 失败，进而让向量化阶段卡死）
    _IGNORE_PATTERNS = ["*.DS_Store", "imgs/*", "**/.DS_Store"]

    @staticmethod
    def _is_cached(cache_dir: str, model_name: str) -> bool:
        """判断模型是否已下载到标准 HF 缓存结构（cache_dir/models--org--repo/）。"""
        return BgeM3Embedder._resolve_local_model_dir(cache_dir, model_name) is not None

    @staticmethod
    def _resolve_local_model_dir(cache_dir: str, model_name: str) -> Optional[str]:
        """返回本地快照目录路径（含 config.json 的 snapshot），未缓存返回 None。"""
        repo_cache = os.path.join(cache_dir, "models--" + model_name.replace("/", "--"))
        snapshots = os.path.join(repo_cache, "snapshots")
        if not os.path.isdir(snapshots):
            return None
        for d in sorted(os.listdir(snapshots)):
            p = os.path.join(snapshots, d)
            if os.path.isdir(p) and os.path.exists(os.path.join(p, "config.json")):
                return p
        return None

    def _ensure_downloaded(self, cache_dir: str):
        """通过 hf-hub 镜像下载模型到标准缓存结构（仅当未缓存时）。"""
        from huggingface_hub import snapshot_download
        if self._is_cached(cache_dir, self.model_name):
            logger.info(f"[BGE-M3] 模型已缓存: {cache_dir}")
            return
        # 禁用 Xet 后端（镜像不支持，会 401 认证失败），改用普通 HTTP 下载
        os.environ.setdefault("HF_HUB_DISABLE_XET", "1")
        logger.info(f"[BGE-M3] 模型未缓存，开始下载: {self.model_name}")
        snapshot_download(
            self.model_name,
            cache_dir=cache_dir,
            ignore_patterns=self._IGNORE_PATTERNS,
        )
        logger.info(f"[BGE-M3] 模型下载完成 → {cache_dir}")

    def preload(self, progress_cb: Optional[Callable[[int, str], None]] = None):
        """预下载并加载模型（应用启动时调用，避免导入时才下载导致卡顿）。

        Args:
            progress_cb: 可选进度回调 callable(percent, message)
        """
        cache_dir = self._get_cache_dir()
        os.environ.setdefault("HF_ENDPOINT", "https://hf-mirror.com")
        if not self._is_cached(cache_dir, self.model_name) and progress_cb:
            progress_cb(5, "模型下载中，首次使用需下载（约 2GB）")
        self._ensure_downloaded(cache_dir)
        if progress_cb:
            progress_cb(50, "模型下载完成，加载中")
        # 下载（或已缓存）后正式加载
        self._get_model()
        if progress_cb:
            progress_cb(100, "模型就绪")

    def _get_model(self):
        if self._model is not None:
            return self._model
        with self._load_lock:
            if self._model is not None:
                return self._model
            from FlagEmbedding import BGEM3FlagModel
            # 使用本地模型缓存目录（data/models），优先离线加载，避免连接 huggingface.co 失败
            cache_dir = self._get_cache_dir()
            # 国内网络 huggingface.co 常不可达，默认走 hf-mirror 镜像
            os.environ.setdefault("HF_ENDPOINT", "https://hf-mirror.com")
            os.environ.setdefault("HF_HUB_DISABLE_XET", "1")
            fp16 = self._resolve_fp16(self.use_fp16)
            try:
                # 确保模型已下载到本地缓存
                self._ensure_downloaded(cache_dir)
                # 传入本地快照目录，绕过 FlagEmbedding 内部 snapshot_download（
                # 其固定下载 .DS_Store 等文件，在镜像端会 403 导致卡死）
                local_dir = self._resolve_local_model_dir(cache_dir, self.model_name)
                if local_dir is None:
                    raise RuntimeError("BGE-M3 模型缓存校验失败，未找到模型快照")
                self._model = BGEM3FlagModel(
                    local_dir,
                    use_fp16=fp16,
                    cache_dir=cache_dir,
                )
                logger.info(f"[BGE-M3] 从本地缓存加载模型: {local_dir}")
            except Exception as e:
                logger.error(f"[BGE-M3] 模型加载失败: {e}", exc_info=True)
                raise RuntimeError(f"无法加载 BGE-M3 模型: {e}") from e
        return self._model

    @staticmethod
    def _get_cache_dir() -> str:
        """返回模型缓存目录（data/models），不存在则创建"""
        try:
            from utils.paths import get_models_dir
            return get_models_dir()
        except Exception:
            default = os.path.join(
                os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                "data", "models",
            )
            os.makedirs(default, exist_ok=True)
            return default

    def encode(self, texts: list[str]) -> list[EmbeddingResult]:
        """批量编码文本（文档侧）"""
        model = self._get_model()
        result = model.encode(texts, return_dense=True, return_sparse=True,
                               return_colbert_vecs=True)
        results = []
        for i in range(len(texts)):
            results.append(EmbeddingResult(
                dense=result["dense_vecs"][i].tolist(),
                sparse={k: float(v) for k, v in result["lexical_weights"][i].items()},
                colbert=[v.tolist() for v in result["colbert_vecs"][i]]
            ))
        return results

    def encode_query(self, query: str) -> EmbeddingResult:
        """编码查询文本"""
        return self.encode([query])[0]

    @property
    def supports_sparse(self) -> bool:
        return True

    @property
    def supports_colbert(self) -> bool:
        return True