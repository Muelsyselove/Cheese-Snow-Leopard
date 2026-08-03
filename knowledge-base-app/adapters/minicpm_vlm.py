"""VLM 方案C：MiniCPM-V 4.5（通用图像理解·需 GPU）

解析策略（技术文档 3.4 + 6.3）：
- MiniCPM-V 偏通用图像理解，文档版面解析需配合 PyMuPDF 分页渲染逐页理解
- 用 PyMuPDF 将 PDF 各页渲染为图片，逐页调用 understand_image 提取结构化文本
- 每页输出按段落切分为 Chunk，page_number 为当前页码
- 非文档类图片直接 understand_image 输出描述
"""
from __future__ import annotations

import logging
import os
from typing import Optional

from interfaces.parser import DocumentParser, ParsedDocument, ImageBlock
from models.chunk import Chunk

# 复用方案A 的 markdown 切分逻辑
from adapters.paddleocr_vl import _markdown_to_chunks

logger = logging.getLogger(__name__)

# 默认逐页理解 prompt（引导模型输出结构化 markdown）
_DEFAULT_PAGE_PROMPT = (
    "请识别并输出这一页文档的结构化内容，使用 markdown 格式："
    "标题用 # 标记，表格用 | 分隔，公式用 $$ 包裹，其余按段落输出。"
)


class MiniCPMVModel:
    """MiniCPM-V 4.5 实现 — 通用图像理解，需 GPU"""

    def __init__(self, model_path: str = "openbmb/MiniCPM-V-4_5",
                 quantization: str = "awq",
                 page_dpi: int = 200,
                 page_prompt: str = _DEFAULT_PAGE_PROMPT):
        self.model_path = model_path
        self.quantization = quantization
        self.page_dpi = page_dpi  # 渲染 DPI，越高精度越好越慢
        self.page_prompt = page_prompt
        self._pipe = None

    def _get_pipe(self):
        if self._pipe is None:
            from lmdeploy import pipeline
            self._pipe = pipeline(self.model_path)
        return self._pipe

    def parse_document(self, file_path: str) -> ParsedDocument:
        """MiniCPM-V 偏通用图像理解，文档版面解析需配合分页渲染逐页理解。"""
        ext = os.path.splitext(file_path)[1].lower()
        if ext in (".png", ".jpg", ".jpeg", ".bmp", ".webp"):
            # 单图直接理解
            desc = self.understand_image(file_path, self.page_prompt)
            chunks = _markdown_to_chunks(desc) if desc else []
            return ParsedDocument(
                chunks=chunks,
                images=[ImageBlock(image_path=file_path, page_number=1,
                                   bbox=[0, 0, 0, 0], description=desc)],
                metadata={"parser": "minicpm_v", "file": file_path,
                          "page_count": 1}
            )

        # PDF / 其他文档：PyMuPDF 分页渲染为图片，逐页理解
        page_images = self._render_pdf_to_images(file_path)
        all_chunks: list[Chunk] = []
        images: list[ImageBlock] = []

        for page_no, img_path in page_images:
            try:
                desc = self.understand_image(img_path, self.page_prompt)
            except Exception as e:
                logger.warning(f"MiniCPM-V 第 {page_no} 页理解失败: {e}")
                desc = ""
            if not desc:
                continue
            page_chunks = _markdown_to_chunks(desc)
            # 回填页码
            for c in page_chunks:
                c.page_number = page_no
            all_chunks.extend(page_chunks)
            images.append(ImageBlock(
                image_path=img_path, page_number=page_no,
                bbox=[0, 0, 0, 0], description=desc
            ))

        logger.info(
            f"MiniCPM-V 解析完成 file={file_path} pages={len(page_images)} "
            f"chunks={len(all_chunks)}"
        )
        return ParsedDocument(
            chunks=all_chunks, images=images,
            metadata={"parser": "minicpm_v", "file": file_path,
                      "page_count": len(page_images)}
        )

    def understand_image(self, image_path: str, prompt: str) -> str:
        """单图理解"""
        from lmdeploy.vl import load_image
        pipe = self._get_pipe()
        image = load_image(image_path)
        response = pipe((prompt, image))
        return response.text

    @property
    def requires_gpu(self) -> bool:
        return True

    # ------------------------------------------------------------------
    # PDF 分页渲染
    # ------------------------------------------------------------------
    def _render_pdf_to_images(self, file_path: str) -> list[tuple[int, str]]:
        """用 PyMuPDF 将 PDF 各页渲染为 PNG，返回 [(page_no, image_path)]。

        输出目录基于文件名，渲染失败时返回空列表。
        """
        try:
            import fitz  # PyMuPDF
        except ImportError:
            logger.error("PyMuPDF 未安装，无法渲染 PDF 分页")
            return []

        out_dir = os.path.join("./tmp/minicpm_pages",
                               os.path.splitext(os.path.basename(file_path))[0])
        os.makedirs(out_dir, exist_ok=True)

        pages: list[tuple[int, str]] = []
        try:
            doc = fitz.open(file_path)
        except Exception as e:
            logger.error(f"PyMuPDF 打开失败 file={file_path}: {e}")
            return pages

        try:
            zoom = self.page_dpi / 72.0  # PDF 默认 72 DPI
            matrix = fitz.Matrix(zoom, zoom)
            for i, page in enumerate(doc, start=1):
                try:
                    pix = page.get_pixmap(matrix=matrix)
                    img_path = os.path.join(out_dir, f"page_{i:04d}.png")
                    pix.save(img_path)
                    pages.append((i, img_path))
                except Exception as e:
                    logger.warning(f"渲染第 {i} 页失败: {e}")
        finally:
            doc.close()

        return pages
