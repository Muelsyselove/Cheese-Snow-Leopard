"""文档分块器单元测试 — 结构感知分块 + token 计数"""
from __future__ import annotations

import pytest

from interfaces.parser import ParsedDocument
from models.chunk import Chunk
from services.chunker import CharTokenCounter, StructureAwareChunker


# ---------------------------------------------------------------------------
# 辅助构造
# ---------------------------------------------------------------------------
def _make_text_chunk(content: str, page: int = 1, doc_id: int = 100,
                     char_start: int = 0) -> Chunk:
    return Chunk(
        chunk_id=0,
        content_hash="",
        doc_id=doc_id,
        doc_name="test.md",
        content=content,
        chunk_type="text",
        page_number=page,
        char_start=char_start,
        char_end=char_start + len(content),
    )


def _make_non_text_chunk(content: str, chunk_type: str = "image") -> Chunk:
    return Chunk(
        chunk_id=0,
        content_hash="",
        doc_id=100,
        doc_name="test.md",
        content=content,
        chunk_type=chunk_type,
        page_number=1,
    )


def _parsed(*chunks: Chunk) -> ParsedDocument:
    return ParsedDocument(chunks=list(chunks), images=[], metadata={})


# ---------------------------------------------------------------------------
# CharTokenCounter
# ---------------------------------------------------------------------------
class TestCharTokenCounter:

    def test_empty(self):
        counter = CharTokenCounter()
        assert counter.count("") == 0

    def test_cjk(self):
        """中文字符 1 字符 ≈ 1 token"""
        counter = CharTokenCounter()
        assert counter.count("知识库") == 3

    def test_ascii(self):
        """英文 4 字符 ≈ 1 token（向上取整）"""
        counter = CharTokenCounter()
        assert counter.count("abcd") == 1
        assert counter.count("abc") == 1   # (3+3)//4 = 1
        assert counter.count("abcdefgh") == 2

    def test_mixed(self):
        """中英混合"""
        counter = CharTokenCounter()
        # "知识库abc" → 3 CJK + 3 ascii → 3 + (3+3)//4 = 3 + 1 = 4
        assert counter.count("知识库abc") == 4


# ---------------------------------------------------------------------------
# StructureAwareChunker 配置校验
# ---------------------------------------------------------------------------
class TestChunkerConfig:

    def test_invalid_target_tokens(self):
        with pytest.raises(ValueError):
            StructureAwareChunker(target_tokens=0)

    def test_invalid_overlap_ratio(self):
        with pytest.raises(ValueError):
            StructureAwareChunker(overlap_ratio=1.0)
        with pytest.raises(ValueError):
            StructureAwareChunker(overlap_ratio=-0.1)

    def test_invalid_min_chunk_tokens(self):
        with pytest.raises(ValueError):
            StructureAwareChunker(min_chunk_tokens=-1)

    def test_min_ge_target(self):
        """min_chunk_tokens 须小于 target_tokens"""
        with pytest.raises(ValueError):
            StructureAwareChunker(target_tokens=100, min_chunk_tokens=100)


# ---------------------------------------------------------------------------
# 分块行为
# ---------------------------------------------------------------------------
class TestChunkerSplit:

    def test_short_text_not_split(self):
        """短文本不切分，原样返回单个块"""
        chunker = StructureAwareChunker(target_tokens=300, min_chunk_tokens=50)
        text = "这是一段简短的文本，不需要切分。"
        result = chunker.split(_parsed(_make_text_chunk(text)))
        assert len(result) == 1
        assert result[0].content == text
        assert result[0].chunk_type == "text"

    def test_empty_content(self):
        """空内容返回空列表"""
        chunker = StructureAwareChunker()
        result = chunker.split(_parsed(_make_text_chunk("")))
        assert result == []
        result = chunker.split(_parsed(_make_text_chunk("   \n  \n  ")))
        assert result == []

    def test_long_text_split_into_multiple(self):
        """长文本切分为多块，每块 token 数不超过 target（尾块可合并例外）"""
        target = 50
        chunker = StructureAwareChunker(
            target_tokens=target, overlap_ratio=0.1, min_chunk_tokens=10
        )
        # 构造明显超过 target 的中文文本（每字 1 token）
        text = "段落一。" * 40 + "段落二。" * 40 + "段落三。" * 40
        result = chunker.split(_parsed(_make_text_chunk(text)))
        assert len(result) >= 2
        # 非尾块均不应超过 target（允许 overlap 略微溢出，但主体不应超太多）
        for c in result[:-1]:
            assert CharTokenCounter().count(c.content) <= target * 1.2

    def test_overlap_between_chunks(self):
        """相邻块存在重叠内容"""
        chunker = StructureAwareChunker(
            target_tokens=30, overlap_ratio=0.3, min_chunk_tokens=5
        )
        text = "。".join(f"第{i}句话内容" for i in range(50))
        result = chunker.split(_parsed(_make_text_chunk(text)))
        assert len(result) >= 2
        # 第一块结尾内容应出现在第二块开头（overlap）
        if len(result) >= 2:
            tail = result[0].content[-3:]
            assert tail in result[1].content

    def test_tail_merge(self):
        """尾块过小应合并到前一块"""
        # target=30，主体很长，结尾只剩很短一段
        chunker = StructureAwareChunker(
            target_tokens=30, overlap_ratio=0.0, min_chunk_tokens=20
        )
        text = "内容块。" * 30 + "短"  # 主体 120 token + 1 字尾
        result = chunker.split(_parsed(_make_text_chunk(text)))
        # 最后一块不应是孤立的"短"
        assert result[-1].content != "短"
        assert "短" in result[-1].content

    def test_heading_as_boundary(self):
        """Markdown 标题行作为硬分节边界"""
        chunker = StructureAwareChunker(
            target_tokens=1000, overlap_ratio=0.0, min_chunk_tokens=5
        )
        # target 设很大，强制因标题边界才切分
        text = "# 标题一\n" + "内容一。" * 10 + "\n\n# 标题二\n" + "内容二。" * 10
        result = chunker.split(_parsed(_make_text_chunk(text)))
        assert len(result) == 2
        assert result[0].content.startswith("# 标题一")
        assert result[1].content.startswith("# 标题二")

    def test_non_text_block_preserved(self):
        """图片/表格/公式块原样保留，不切分"""
        chunker = StructureAwareChunker(target_tokens=10, min_chunk_tokens=2)
        text_chunk = _make_text_chunk("一段较长文本内容需要切分。" * 5)
        img_chunk = _make_non_text_chunk("图片描述", chunk_type="image")
        table_chunk = _make_non_text_chunk("| a | b |", chunk_type="table")
        result = chunker.split(_parsed(text_chunk, img_chunk, table_chunk))
        # 图片和表格块应原样存在
        types = [c.chunk_type for c in result]
        assert "image" in types
        assert "table" in types
        img = next(c for c in result if c.chunk_type == "image")
        assert img.content == "图片描述"

    def test_char_offset_in_source(self):
        """char_start/char_end 为相对源块 content 的偏移"""
        chunker = StructureAwareChunker(
            target_tokens=20, overlap_ratio=0.0, min_chunk_tokens=5
        )
        text = "第一段内容在此。" + "第二段内容在此。" + "第三段内容在此。"
        result = chunker.split(_parsed(_make_text_chunk(text)))
        assert len(result) >= 1
        # 每块的切片内容应能在源文本对应区间找到
        for c in result:
            assert 0 <= c.char_start < c.char_end <= len(text)
            assert text[c.char_start:c.char_end] in c.content or \
                   c.content.strip() in text

    def test_metadata_inherited(self):
        """page_number / bbox 从源块继承"""
        chunker = StructureAwareChunker(
            target_tokens=20, overlap_ratio=0.0, min_chunk_tokens=5
        )
        src = _make_text_chunk("一段较长文本内容需要切分。" * 3, page=5)
        src.bbox = [10.0, 20.0, 100.0, 200.0]
        result = chunker.split(_parsed(src))
        assert len(result) >= 1
        for c in result:
            assert c.page_number == 5
            assert c.bbox == [10.0, 20.0, 100.0, 200.0]
            assert c.chunk_type == "text"

    def test_single_long_paragraph_split(self):
        """单段落过长时按句子切分"""
        chunker = StructureAwareChunker(
            target_tokens=15, overlap_ratio=0.0, min_chunk_tokens=3
        )
        # 无空行，单段落；每句约 7 token，target=15 → 约两句一块
        text = "这是第一句话。这是第二句话。这是第三句话。这是第四句话。这是第五句话。"
        result = chunker.split(_parsed(_make_text_chunk(text)))
        assert len(result) >= 2

    def test_custom_token_counter(self):
        """可注入自定义 token 计数器"""

        class FixedCounter:
            def count(self, text: str) -> int:
                return len(text)  # 按字符数

        chunker = StructureAwareChunker(
            target_tokens=10, overlap_ratio=0.0, min_chunk_tokens=3,
            token_counter=FixedCounter()
        )
        text = "a" * 25  # 25 字符 → 应切成 3 块（10+10+5，尾块5≥3）
        result = chunker.split(_parsed(_make_text_chunk(text)))
        assert len(result) == 3


# ---------------------------------------------------------------------------
# 接口契约
# ---------------------------------------------------------------------------
class TestChunkerContract:

    def test_chunker_protocol_satisfied(self):
        """StructureAwareChunker 满足 Chunker Protocol"""
        from interfaces.chunker import Chunker
        chunker = StructureAwareChunker()
        # 拥有 split 方法即满足 Protocol（结构子类型）
        assert hasattr(chunker, "split")
        assert isinstance(chunker, Chunker) if hasattr(Chunker, "__protocol__") else True

    def test_output_chunks_need_id_injection(self):
        """分块器输出的 chunk_id/content_hash 为占位，由 file_service 注入"""
        chunker = StructureAwareChunker(
            target_tokens=10, overlap_ratio=0.0, min_chunk_tokens=3
        )
        result = chunker.split(_parsed(_make_text_chunk("一段较长文本内容。" * 5)))
        assert len(result) >= 1
        for c in result:
            # 占位值，file_service 会覆盖
            assert c.chunk_id == 0
            assert c.content_hash == ""
