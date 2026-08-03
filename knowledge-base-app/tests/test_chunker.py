"""文档分块器单元测试 — 结构感知分块 + token 计数"""
from __future__ import annotations

import pytest

from interfaces.parser import ParsedDocument
from models.chunk import Chunk
from services.chunker import CharTokenCounter, StructureAwareChunker


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


class TestCharTokenCounter:

    def test_empty(self):
        counter = CharTokenCounter()
        assert counter.count("") == 0

    def test_cjk(self):
        counter = CharTokenCounter()
        assert counter.count("知识库") == 3

    def test_ascii(self):
        counter = CharTokenCounter()
        assert counter.count("abcd") == 1
        assert counter.count("abc") == 1
        assert counter.count("abcdefgh") == 2

    def test_mixed(self):
        counter = CharTokenCounter()
        assert counter.count("知识库abc") == 4


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
        with pytest.raises(ValueError):
            StructureAwareChunker(target_tokens=100, min_chunk_tokens=100)


class TestChunkerSplit:

    def test_short_text_not_split(self):
        chunker = StructureAwareChunker(target_tokens=300, min_chunk_tokens=50)
        text = "这是一段简短的文本，不需要切分。"
        result = chunker.split(_parsed(_make_text_chunk(text)))
        assert len(result) == 1
        assert result[0].content == text
        assert result[0].chunk_type == "text"

    def test_empty_content(self):
        chunker = StructureAwareChunker()
        result = chunker.split(_parsed(_make_text_chunk("")))
        assert result == []
        result = chunker.split(_parsed(_make_text_chunk("   \n  \n  ")))
        assert result == []

    def test_long_text_split_into_multiple(self):
        target = 50
        chunker = StructureAwareChunker(
            target_tokens=target, overlap_ratio=0.1, min_chunk_tokens=10
        )
        text = "段落一。" * 40 + "段落二。" * 40 + "段落三。" * 40
        result = chunker.split(_parsed(_make_text_chunk(text)))
        assert len(result) >= 2
        for c in result[:-1]:
            assert CharTokenCounter().count(c.content) <= target * 1.2

    def test_overlap_between_chunks(self):
        chunker = StructureAwareChunker(
            target_tokens=30, overlap_ratio=0.3, min_chunk_tokens=5
        )
        text = "。".join(f"第{i}句话内容" for i in range(50))
        result = chunker.split(_parsed(_make_text_chunk(text)))
        assert len(result) >= 2
        if len(result) >= 2:
            tail = result[0].content[-3:]
            assert tail in result[1].content

    def test_tail_merge(self):
        chunker = StructureAwareChunker(
            target_tokens=30, overlap_ratio=0.0, min_chunk_tokens=20
        )
        text = "内容块。" * 30 + "短"
        result = chunker.split(_parsed(_make_text_chunk(text)))
        assert result[-1].content != "短"
        assert "短" in result[-1].content

    def test_heading_as_boundary(self):
        chunker = StructureAwareChunker(
            target_tokens=1000, overlap_ratio=0.0, min_chunk_tokens=5
        )
        text = "# 标题一\n" + "内容一。" * 10 + "\n\n# 标题二\n" + "内容二。" * 10
        result = chunker.split(_parsed(_make_text_chunk(text)))
        assert len(result) == 2
        assert result[0].content.startswith("# 标题一")
        assert result[1].content.startswith("# 标题二")

    def test_non_text_block_preserved(self):
        chunker = StructureAwareChunker(target_tokens=10, min_chunk_tokens=2)
        text_chunk = _make_text_chunk("一段较长文本内容需要切分。" * 5)
        img_chunk = _make_non_text_chunk("图片描述", chunk_type="image")
        table_chunk = _make_non_text_chunk("| a | b |", chunk_type="table")
        result = chunker.split(_parsed(text_chunk, img_chunk, table_chunk))
        types = [c.chunk_type for c in result]
        assert "image" in types
        assert "table" in types
        img = next(c for c in result if c.chunk_type == "image")
        assert img.content == "图片描述"

    def test_char_offset_in_source(self):
        chunker = StructureAwareChunker(
            target_tokens=20, overlap_ratio=0.0, min_chunk_tokens=5
        )
        text = "第一段内容在此。" + "第二段内容在此。" + "第三段内容在此。"
        result = chunker.split(_parsed(_make_text_chunk(text)))
        assert len(result) >= 1
        for c in result:
            assert 0 <= c.char_start < c.char_end <= len(text)
            assert text[c.char_start:c.char_end] in c.content or \
                   c.content.strip() in text

    def test_metadata_inherited(self):
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
        chunker = StructureAwareChunker(
            target_tokens=15, overlap_ratio=0.0, min_chunk_tokens=3
        )
        text = "这是第一句话。这是第二句话。这是第三句话。这是第四句话。这是第五句话。"
        result = chunker.split(_parsed(_make_text_chunk(text)))
        assert len(result) >= 2

    def test_custom_token_counter(self):
        class FixedCounter:
            def count(self, text: str) -> int:
                return len(text)

        chunker = StructureAwareChunker(
            target_tokens=10, overlap_ratio=0.0, min_chunk_tokens=3,
            token_counter=FixedCounter()
        )
        text = "a" * 25
        result = chunker.split(_parsed(_make_text_chunk(text)))
        assert len(result) == 3


class TestChunkerContract:

    def test_chunker_protocol_satisfied(self):
        from interfaces.chunker import Chunker
        chunker = StructureAwareChunker()
        assert hasattr(chunker, "split")
        assert isinstance(chunker, Chunker) if hasattr(Chunker, "__protocol__") else True

    def test_output_chunks_need_id_injection(self):
        chunker = StructureAwareChunker(
            target_tokens=10, overlap_ratio=0.0, min_chunk_tokens=3
        )
        result = chunker.split(_parsed(_make_text_chunk("一段较长文本内容。" * 5)))
        assert len(result) >= 1
        for c in result:
            assert c.chunk_id == 0
            assert c.content_hash == ""
