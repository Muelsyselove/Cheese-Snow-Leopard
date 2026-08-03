"""VLM 方案A：PaddleOCR-VL-0.9B（CPU 可运行·无 GPU 首选）

注：API 以 paddleocr 实际导出为准，此处为骨架实现，集成时需核对版本。
"""
from __future__ import annotations

import hashlib
from typing import Optional

from interfaces.parser import DocumentParser, ParsedDocument, ImageBlock
from models.chunk import Chunk


class PaddleOCRVLModel:
    """PaddleOCR-VL-0.9B 实现 — CPU 可运行"""

    def __init__(self, model_dir: Optional[str] = None, lang: str = "ch"):
        self.model_dir = model_dir
        self.lang = lang
        self._model = None

    def _get_model(self):
        if self._model is None:
            from paddleocr import PaddleOCRVL  # 延迟导入
            self._model = PaddleOCRVL()
        return self._model

    def parse_document(self, file_path: str) -> ParsedDocument:
        """解析文档，返回结构化 ParsedDocument"""
        model = self._get_model()
        result = model.predict(file_path)
        # TODO: 实现真实解析逻辑，将 result.markdown / result.layout 转为 Chunk 列表
        chunks: list[Chunk] = []
        images: list[ImageBlock] = []
        return ParsedDocument(chunks=chunks, images=images,
                              metadata={"parser": "paddleocr_vl", "file": file_path})

    def understand_image(self, image_path: str, prompt: str) -> str:
        """单独图片理解"""
        model = self._get_model()
        result = model.predict(image_path)
        return result.markdown

    @property
    def requires_gpu(self) -> bool:
        return False


def _content_hash(text: str) -> str:
    """SHA-256 内容指纹"""
    return hashlib.sha256(text.encode("utf-8")).hexdigest()
