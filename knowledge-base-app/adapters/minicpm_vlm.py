"""VLM 方案C：MiniCPM-V 4.5（通用图像理解·需 GPU）"""
from __future__ import annotations

from typing import Optional

from interfaces.parser import DocumentParser, ParsedDocument, ImageBlock
from models.chunk import Chunk


class MiniCPMVModel:
    """MiniCPM-V 4.5 实现 — 通用图像理解，需 GPU"""

    def __init__(self, model_path: str = "openbmb/MiniCPM-V-4_5",
                 quantization: str = "awq"):
        self.model_path = model_path
        self.quantization = quantization
        self._pipe = None

    def _get_pipe(self):
        if self._pipe is None:
            from lmdeploy import pipeline
            self._pipe = pipeline(self.model_path)
        return self._pipe

    def parse_document(self, file_path: str) -> ParsedDocument:
        """MiniCPM-V 偏通用图像理解，文档版面解析需配合分页渲染逐页理解"""
        # TODO: 用 PyMuPDF 渲染 PDF 各页为图片，逐页调用 understand_image
        chunks: list[Chunk] = []
        images: list[ImageBlock] = []
        return ParsedDocument(chunks=chunks, images=images,
                              metadata={"parser": "minicpm_v", "file": file_path})

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
