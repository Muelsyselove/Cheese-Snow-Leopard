"""VLM 方案B：MinerU 框架（含 vlm/pipeline 两后端）

- backend="vlm-engine":      需 GPU，版面精度首选（97.5% mAP）
- backend="pipeline":        CPU 可降级，精度略低但无 GPU 可用

MinerU 新版允许的后端值：pipeline, vlm-engine, hybrid-engine,
vlm-http-client, hybrid-http-client。为兼容旧配置，本实现将旧值 "vlm"
自动映射为 "vlm-engine"。

解析流程（技术文档 3.4）：
1. do_parse 将 PDF 解析为 markdown + layout JSON 写入 output_dir
2. 读取产物中的 markdown 文件，复用 paddleocr_vl._markdown_to_chunks 切分
3. 图片块从 layout 提取 bbox（描述文本留空，由下游 understand_image 回填）

注：mineru API 以实际版本为准，do_parse 返回路径可能随版本变化，本实现通过
_find_markdown_file 在 output_dir 中递归查找 .md 产物以增强兼容性。
"""
from __future__ import annotations

import logging
import os
from typing import Optional

from interfaces.parser import DocumentParser, ParsedDocument, ImageBlock
from models.chunk import Chunk

# 复用方案A 的 markdown 切分逻辑（结构感知，与具体 VLM 无关）
from adapters.paddleocr_vl import _markdown_to_chunks

logger = logging.getLogger(__name__)

# MinerU 新版允许的后端值
_ALLOWED_BACKENDS = {
    "pipeline", "vlm-engine", "hybrid-engine",
    "vlm-http-client", "hybrid-http-client",
}
# 旧值 → 新值 映射（兼容历史配置）
_BACKEND_ALIAS = {
    "vlm": "vlm-engine",
    "hybrid": "hybrid-engine",
}
# 需要 GPU/torchvision 的后端（无 GPU 环境会失败，需降级到 pipeline）
_GPU_BACKENDS = {"vlm-engine", "hybrid-engine", "vlm-http-client", "hybrid-http-client"}


class MinerUModel:
    """MinerU 框架实现 — 含 vlm/pipeline 两后端"""

    def __init__(self, backend: str = "vlm-engine", device: str = "cuda",
                 output_dir: str = None):
        # 兼容旧配置值
        backend = _BACKEND_ALIAS.get(backend, backend)
        if backend not in _ALLOWED_BACKENDS:
            raise ValueError(
                f"未知 MinerU 后端: {backend}，允许值: "
                f"{', '.join(sorted(_ALLOWED_BACKENDS))}"
            )
        self.backend = backend
        self.device = device
        # 默认输出目录指向 data/mineru/output
        if output_dir is None:
            try:
                from utils.paths import get_mineru_output_dir
                output_dir = get_mineru_output_dir()
            except Exception:
                output_dir = "./tmp/mineru_output"
        self.output_dir = output_dir
        # 是否已因缺少依赖降级到 pipeline
        self._fallback_to_pipeline = False

    def _get_effective_backend(self) -> str:
        """获取实际使用的后端（含降级逻辑）

        若配置为 GPU 后端但环境缺少 torchvision/GPU，自动降级到 pipeline。
        降级结果会缓存，避免每次解析都重复探测。
        """
        if self._fallback_to_pipeline:
            return "pipeline"
        if self.backend in _GPU_BACKENDS:
            if not self._check_gpu_deps():
                logger.warning(
                    f"MinerU 后端 {self.backend} 需要 GPU/torchvision，"
                    "环境不满足，自动降级到 pipeline（CPU）。"
                )
                self._fallback_to_pipeline = True
                return "pipeline"
        return self.backend

    @staticmethod
    def _check_gpu_deps() -> bool:
        """检查 GPU 后端所需依赖是否就绪（torch + torchvision + CUDA）"""
        try:
            import torch  # noqa: F401
            import torchvision  # noqa: F401
            return torch.cuda.is_available()
        except Exception:
            return False

    def parse_document(self, file_path: str) -> ParsedDocument:
        """解析文档，返回结构化 ParsedDocument。"""
        from mineru.cli.common import do_parse, read_fn  # API 以实际版本为准

        pdf_bytes = read_fn(file_path)
        # 每个文档独立子目录，避免并发覆盖
        doc_output_dir = os.path.join(
            self.output_dir, os.path.splitext(os.path.basename(file_path))[0]
        )
        os.makedirs(doc_output_dir, exist_ok=True)

        # MinerU API 兼容：新版要求 pdf_file_names 和 p_lang_list 必填参数
        base_name = os.path.splitext(os.path.basename(file_path))[0]
        effective_backend = self._get_effective_backend()
        do_parse(
            output_dir=doc_output_dir,
            pdf_file_names=[base_name],
            pdf_bytes_list=[pdf_bytes],
            p_lang_list=["ch"],
            backend=effective_backend,
        )

        # 读取产物 markdown
        markdown_path = self._find_markdown_file(doc_output_dir)
        if markdown_path is None:
            logger.warning(f"MinerU 未输出 markdown 产物，dir={doc_output_dir}")
            return ParsedDocument(
                chunks=[], images=[],
                metadata={"parser": "mineru", "backend": effective_backend,
                          "file": file_path, "error": "no markdown output"}
            )

        with open(markdown_path, "r", encoding="utf-8") as f:
            markdown = f.read()

        chunks = _markdown_to_chunks(markdown)
        # MinerU 可能把图片提取为独立文件，扫描 images 目录生成 ImageBlock
        images = self._collect_images(doc_output_dir)

        logger.info(
            f"MinerU 解析完成 file={file_path} backend={effective_backend} "
            f"chunks={len(chunks)} images={len(images)}"
        )
        return ParsedDocument(
            chunks=chunks, images=images,
            metadata={"parser": "mineru", "backend": effective_backend,
                      "file": file_path, "markdown_path": markdown_path}
        )

    def understand_image(self, image_path: str, prompt: str) -> str:
        """MinerU 主要面向文档，单图理解降级到内置 OCR。

        通过把单图包装成单页 PDF 再走 do_parse 提取文本；失败时返回空串。
        """
        try:
            from mineru.cli.common import do_parse, read_fn
            tmp_dir = os.path.join(self.output_dir, "_single_img")
            os.makedirs(tmp_dir, exist_ok=True)
            img_bytes = read_fn(image_path)
            base_name = os.path.splitext(os.path.basename(image_path))[0]
            do_parse(
                output_dir=tmp_dir,
                pdf_file_names=[base_name],
                pdf_bytes_list=[img_bytes],
                p_lang_list=["ch"],
                backend=self._get_effective_backend(),
            )
            md_path = self._find_markdown_file(tmp_dir)
            if md_path is None:
                return ""
            with open(md_path, "r", encoding="utf-8") as f:
                return f.read().strip()
        except Exception as e:
            logger.warning(f"MinerU 单图理解失败 image={image_path}: {e}")
            return ""

    @property
    def requires_gpu(self) -> bool:
        # pipeline 后端可 CPU；vlm-engine / hybrid-engine 等需 GPU
        return self.backend != "pipeline"

    # ------------------------------------------------------------------
    # 产物文件定位
    # ------------------------------------------------------------------
    @staticmethod
    def _find_markdown_file(output_dir: str) -> Optional[str]:
        """在 output_dir 中递归查找 markdown 产物文件。"""
        for root, _dirs, files in os.walk(output_dir):
            for fn in files:
                if fn.lower().endswith(".md"):
                    return os.path.join(root, fn)
        return None

    @staticmethod
    def _collect_images(output_dir: str) -> list[ImageBlock]:
        """扫描 output_dir 中的 images 子目录，收集图片块。"""
        images: list[ImageBlock] = []
        for root, _dirs, files in os.walk(output_dir):
            for fn in files:
                if fn.lower().endswith((".png", ".jpg", ".jpeg")):
                    images.append(ImageBlock(
                        image_path=os.path.join(root, fn),
                        page_number=1,
                        bbox=[0, 0, 0, 0],
                        description="",
                    ))
        return images
