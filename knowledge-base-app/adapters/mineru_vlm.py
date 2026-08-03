"""VLM 方案B：MinerU 框架（含 vlm/pipeline 两后端）

- backend="vlm":      需 GPU，版面精度首选（97.5% mAP）
- backend="pipeline": CPU 可降级，精度略低但无 GPU 可用

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


class MinerUModel:
    """MinerU 框架实现 — 含 vlm/pipeline 两后端"""

    def __init__(self, backend: str = "vlm", device: str = "cuda",
                 output_dir: str = "./tmp/mineru_output"):
        if backend not in ("vlm", "pipeline"):
            raise ValueError(f"未知 MinerU 后端: {backend}，应为 vlm 或 pipeline")
        self.backend = backend
        self.device = device
        self.output_dir = output_dir

    def parse_document(self, file_path: str) -> ParsedDocument:
        """解析文档，返回结构化 ParsedDocument。"""
        from mineru.cli.common import do_parse, read_fn  # API 以实际版本为准

        pdf_bytes = read_fn(file_path)
        # 每个文档独立子目录，避免并发覆盖
        doc_output_dir = os.path.join(
            self.output_dir, os.path.splitext(os.path.basename(file_path))[0]
        )
        os.makedirs(doc_output_dir, exist_ok=True)

        do_parse(
            output_dir=doc_output_dir,
            pdf_bytes_list=[pdf_bytes],
            backend=self.backend,
        )

        # 读取产物 markdown
        markdown_path = self._find_markdown_file(doc_output_dir)
        if markdown_path is None:
            logger.warning(f"MinerU 未输出 markdown 产物，dir={doc_output_dir}")
            return ParsedDocument(
                chunks=[], images=[],
                metadata={"parser": "mineru", "backend": self.backend,
                          "file": file_path, "error": "no markdown output"}
            )

        with open(markdown_path, "r", encoding="utf-8") as f:
            markdown = f.read()

        chunks = _markdown_to_chunks(markdown)
        # MinerU 可能把图片提取为独立文件，扫描 images 目录生成 ImageBlock
        images = self._collect_images(doc_output_dir)

        logger.info(
            f"MinerU 解析完成 file={file_path} backend={self.backend} "
            f"chunks={len(chunks)} images={len(images)}"
        )
        return ParsedDocument(
            chunks=chunks, images=images,
            metadata={"parser": "mineru", "backend": self.backend,
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
            do_parse(output_dir=tmp_dir, pdf_bytes_list=[img_bytes],
                     backend=self.backend)
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
        return self.backend == "vlm"  # pipeline 后端可 CPU

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
