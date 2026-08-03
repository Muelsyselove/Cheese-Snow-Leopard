"""VLM 方案B：MinerU 框架（含 vlm/pipeline 两后端）

- backend="vlm":      需 GPU，版面精度首选（97.5% mAP）
- backend="pipeline": CPU 可降级，精度略低但无 GPU 可用
"""
from __future__ import annotations

from typing import Optional

from interfaces.parser import DocumentParser, ParsedDocument, ImageBlock
from models.chunk import Chunk


class MinerUModel:
    """MinerU 框架实现 — 含 vlm/pipeline 两后端"""

    def __init__(self, backend: str = "vlm", device: str = "cuda"):
        if backend not in ("vlm", "pipeline"):
            raise ValueError(f"未知 MinerU 后端: {backend}，应为 vlm 或 pipeline")
        self.backend = backend
        self.device = device

    def parse_document(self, file_path: str) -> ParsedDocument:
        """解析文档，返回结构化 ParsedDocument"""
        from mineru.cli.common import do_parse, read_fn  # API 以实际版本为准
        pdf_bytes = read_fn(file_path)
        do_parse(
            output_dir="./tmp",
            pdf_bytes_list=[pdf_bytes],
            backend=self.backend,
        )
        # TODO: 读取 do_parse 输出的 markdown + layout，转为 Chunk 列表
        chunks: list[Chunk] = []
        images: list[ImageBlock] = []
        return ParsedDocument(
            chunks=chunks, images=images,
            metadata={"parser": "mineru", "backend": self.backend, "file": file_path}
        )

    def understand_image(self, image_path: str, prompt: str) -> str:
        """MinerU 主要面向文档，单图理解可降级到内置 OCR"""
        # TODO: 实现单图理解
        return ""

    @property
    def requires_gpu(self) -> bool:
        return self.backend == "vlm"  # pipeline 后端可 CPU
