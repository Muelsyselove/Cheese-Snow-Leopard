"""文档分块接口 — 结构感知（structure-aware）分块。

技术文档 3.4 分块策略：
- 以 Markdown 标题/段落/表格为原子单元
- 目标块大小：200-400 tokens（config.chunking.target_tokens）
- 重叠比例：10-20%（config.chunking.overlap_ratio）
- 每个 chunk 携带元数据：doc_id、页码、bbox、chunk_type（text/image/table/formula）

chunker 属于自研核心逻辑：编码生成（Snowflake + SHA-256）由 file_service 在分块后统一注入，
chunker 仅负责把 ParsedDocument 中的粗粒度文本块切分为目标 token 数的小块，
图片/表格/公式块原样保留（已是合适的粒度）。
"""
from __future__ import annotations

from typing import Protocol, TYPE_CHECKING

if TYPE_CHECKING:
    from models.chunk import Chunk
    from interfaces.parser import ParsedDocument


class TokenCounter(Protocol):
    """Token 计数抽象 — 用于按 token 数控制块大小。

    业务层默认使用 services.chunker.CharTokenCounter（纯字符近似，无第三方依赖）；
    需要精确计数时注入真实 tokenizer 适配器（BGE-M3 / Qwen3 tokenizer）。
    """

    def count(self, text: str) -> int:
        """返回文本的 token 数估计"""
        ...


class Chunker(Protocol):
    """文档分块接口 — 将 ParsedDocument 切分为目标 token 数的 Chunk 列表。

    契约：
    - 输入 parsed.chunks 中的文本块可能为粗粒度（整页/大段落），需进一步切分
    - 图片/表格/公式块原样保留，不参与切分
    - 输出 Chunk 的 chunk_id / doc_id / content_hash 由 file_service 在分块后注入，
      chunker 不负责生成这些字段
    - 位置元数据（page_number / bbox）从源块继承，char_start/char_end 按切分位置计算
    """

    def split(self, parsed: "ParsedDocument") -> list["Chunk"]:
        """将解析结果切分为目标 token 数的知识块列表"""
        ...
