"""文档解析接口（统一文档/图片解析，含 VLM 职责）。

合并了原 DocumentParser 与 VisionLanguageModel 的职责：
- parse_document: 文档版面解析 + OCR + 图片理解，输出结构化 ParsedDocument
- understand_image: 单独图片理解（用于图片直接导入场景，可选实现）

图片块的 content 字段为 VLM 输出的描述文本，下游统一走文本 Embedding。
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Protocol, TYPE_CHECKING

if TYPE_CHECKING:
    from models.chunk import Chunk


@dataclass
class ImageBlock:
    """文档中提取的图片块"""
    image_path: str               # 图片存储路径
    page_number: int              # 所在页码
    bbox: list[float]             # 页面坐标框 [x, y, w, h]
    description: str = ""         # VLM 输出的图片描述文本（用于向量化）
    chunk_type: str = "image"


@dataclass
class ParsedDocument:
    """文档解析结果"""
    chunks: list["Chunk"]         # 解析出的知识块（含文本/表格/公式/图片块）
    images: list[ImageBlock]      # 独立图片块（描述文本已写入对应 Chunk.content）
    metadata: dict = field(default_factory=dict)  # 页数、解析器版本等


class DocumentParser(Protocol):
    """统一文档解析接口 — VLM（PaddleOCR-VL/MinerU/MiniCPM-V）均为该接口的实现。

    图片块的 content 字段为 VLM 输出的描述文本，下游统一走文本 Embedding。
    """

    def parse_document(self, file_path: str) -> ParsedDocument:
        """解析文档，返回结构化 ParsedDocument"""
        ...

    def understand_image(self, image_path: str, prompt: str) -> str:
        """单独图片理解（用于图片直接导入场景）"""
        ...

    @property
    def requires_gpu(self) -> bool:
        """是否需要 GPU：方案A=False, 方案B(vlm)=True, 方案C=True"""
        ...
