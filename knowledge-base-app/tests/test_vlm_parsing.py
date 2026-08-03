"""VLM adapter 解析逻辑单元测试

验证方案A/B/C 的 parse_document 真实解析逻辑（不依赖真实模型）：
- paddleocr_vl._markdown_to_chunks：markdown → Chunk 切分
- paddleocr_vl._extract_markdown / _extract_page_count：多形态 result 兼容
- mineru_vlm._find_markdown_file / _collect_images：产物文件定位
- minicpm_vlm：单图路径直接理解（mock understand_image）

mock 策略：patch _get_model / understand_image，注入构造的 markdown 字符串。
"""
from __future__ import annotations

import os
import tempfile
from unittest.mock import MagicMock, patch

import pytest

from adapters.paddleocr_vl import (
    PaddleOCRVLModel, _markdown_to_chunks, _infer_chunk_type,
    _split_text_by_structure,
)
from adapters.mineru_vlm import MinerUModel
from adapters.minicpm_vlm import MiniCPMVModel
from models.chunk import Chunk


# ========== _markdown_to_chunks 切分逻辑 ==========

class TestMarkdownToChunks:
    def test_empty_markdown_returns_empty(self):
        assert _markdown_to_chunks("") == []
        assert _markdown_to_chunks("   \n  ") == []

    def test_simple_paragraph(self):
        md = "这是第一段文本，描述系统功能。"
        chunks = _markdown_to_chunks(md)
        assert len(chunks) == 1
        assert chunks[0].content == md
        assert chunks[0].chunk_type == "text"
        assert chunks[0].char_start == 0
        assert chunks[0].char_end == len(md)

    def test_heading_splits_sections(self):
        md = "# 标题一\n段落一内容\n\n# 标题二\n段落二内容"
        chunks = _markdown_to_chunks(md)
        # 标题一作为边界：section1 = "# 标题一\n段落一内容" → 2 段（标题、段落）
        # 标题二同理，最终 >=2 个 chunk
        contents = [c.content for c in chunks]
        assert any("段落一内容" in c for c in contents)
        assert any("段落二内容" in c for c in contents)

    def test_fenced_table_block_preserved(self):
        md = "前文\n\n```\n| 列1 | 列2 |\n|----|----|\n| a | b |\n```\n\n后文"
        chunks = _markdown_to_chunks(md)
        table_chunks = [c for c in chunks if c.chunk_type == "table"]
        assert len(table_chunks) >= 1
        # 表格块整体保留
        assert "|" in table_chunks[0].content
        # 前后文仍切为 text
        text_contents = [c.content for c in chunks if c.chunk_type == "text"]
        assert any("前文" in c for c in text_contents)
        assert any("后文" in c for c in text_contents)

    def test_pipe_table_block(self):
        md = "| 名称 | 值 |\n|---|---|\n| x | 1 |\n| y | 2 |"
        chunks = _markdown_to_chunks(md)
        table_chunks = [c for c in chunks if c.chunk_type == "table"]
        assert len(table_chunks) == 1
        assert "名称" in table_chunks[0].content
        assert "y" in table_chunks[0].content

    def test_chunks_ordered_by_char_start(self):
        md = "# H1\n段落一\n\n## H2\n段落二"
        chunks = _markdown_to_chunks(md)
        starts = [c.char_start for c in chunks]
        assert starts == sorted(starts)

    def test_injected_fields_left_zero(self):
        """切分阶段 chunk_id/doc_id/content_hash 留空，由 file_service 注入"""
        md = "测试内容"
        chunks = _markdown_to_chunks(md)
        assert chunks[0].chunk_id == 0
        assert chunks[0].doc_id == 0
        assert chunks[0].content_hash == ""


# ========== _infer_chunk_type ==========

class TestInferChunkType:
    def test_pipe_row_is_table(self):
        assert _infer_chunk_type("| a | b |") == "table"

    def test_formula_dollar(self):
        assert _infer_chunk_type("$$E=mc^2$$") == "formula"

    def test_formula_paren(self):
        assert _infer_chunk_type("\\(x^2\\)") == "formula"

    def test_plain_text(self):
        assert _infer_chunk_type("普通段落文本") == "text"


# ========== PaddleOCRVLModel result 兼容提取 ==========

class TestPaddleOCRResultExtraction:
    def test_extract_markdown_from_object_attr(self):
        result = MagicMock()
        result.markdown = "# 标题\n内容"
        assert PaddleOCRVLModel._extract_markdown(result) == "# 标题\n内容"

    def test_extract_markdown_from_dict(self):
        result = {"markdown": "字典形式 markdown"}
        assert PaddleOCRVLModel._extract_markdown(result) == "字典形式 markdown"

    def test_extract_markdown_from_dict_md_content_fallback(self):
        result = {"md_content": "备用字段"}
        assert PaddleOCRVLModel._extract_markdown(result) == "备用字段"

    def test_extract_markdown_from_string(self):
        assert PaddleOCRVLModel._extract_markdown("直接字符串") == "直接字符串"

    def test_extract_markdown_none(self):
        assert PaddleOCRVLModel._extract_markdown(None) == ""

    def test_extract_markdown_unknown_type_returns_empty(self):
        assert PaddleOCRVLModel._extract_markdown(12345) == ""

    def test_extract_page_count_from_attr(self):
        result = MagicMock()
        result.page_count = 10
        result.num_pages = None
        assert PaddleOCRVLModel._extract_page_count(result) == 10

    def test_extract_page_count_from_dict(self):
        assert PaddleOCRVLModel._extract_page_count({"pages": 5}) == 5

    def test_extract_page_count_missing(self):
        assert PaddleOCRVLModel._extract_page_count(MagicMock()) is None


# ========== PaddleOCRVLModel.parse_document 集成（mock model） ==========

class TestPaddleOCRVLModelParse:
    def test_parse_document_with_mock_model(self):
        """mock _get_model 返回构造的 markdown，验证解析流程"""
        model = PaddleOCRVLModel()
        mock_inner = MagicMock()
        mock_inner.predict.return_value = MagicMock(
            markdown="# 标题\n段落内容", page_count=3
        )
        with patch.object(model, "_get_model", return_value=mock_inner):
            parsed = model.parse_document("/tmp/test.pdf")

        assert parsed.metadata["parser"] == "paddleocr_vl"
        assert parsed.metadata["page_count"] == 3
        assert len(parsed.chunks) >= 1
        assert any("段落内容" in c.content for c in parsed.chunks)

    def test_understand_image_returns_markdown(self):
        model = PaddleOCRVLModel()
        mock_inner = MagicMock()
        mock_inner.predict.return_value = MagicMock(markdown="图片描述文本")
        with patch.object(model, "_get_model", return_value=mock_inner):
            result = model.understand_image("/tmp/img.png", "描述这张图")
        assert result == "图片描述文本"

    def test_requires_gpu_false(self):
        assert PaddleOCRVLModel().requires_gpu is False


# ========== MinerU 产物定位 ==========

class TestMinerUArtifacts:
    def test_find_markdown_file_locates_md(self, tmp_path):
        # 构造产物目录结构
        sub = tmp_path / "doc1" / "auto"
        sub.mkdir(parents=True)
        md_path = sub / "doc1.md"
        md_path.write_text("# 内容", encoding="utf-8")
        found = MinerUModel._find_markdown_file(str(tmp_path))
        assert found is not None
        assert found.endswith("doc1.md")

    def test_find_markdown_file_none_when_absent(self, tmp_path):
        (tmp_path / "a.txt").write_text("x", encoding="utf-8")
        assert MinerUModel._find_markdown_file(str(tmp_path)) is None

    def test_collect_images_finds_png_jpg(self, tmp_path):
        (tmp_path / "img1.png").write_bytes(b"x")
        (tmp_path / "sub").mkdir()
        (tmp_path / "sub" / "img2.jpg").write_bytes(b"y")
        (tmp_path / "note.txt").write_text("z", encoding="utf-8")
        images = MinerUModel._collect_images(str(tmp_path))
        assert len(images) == 2
        assert all(ib.page_number == 1 for ib in images)

    def test_collect_images_empty_when_no_images(self, tmp_path):
        (tmp_path / "a.md").write_text("x", encoding="utf-8")
        assert MinerUModel._collect_images(str(tmp_path)) == []

    def test_invalid_backend_raises(self):
        with pytest.raises(ValueError, match="未知 MinerU 后端"):
            MinerUModel(backend="invalid")

    def test_requires_gpu_by_backend(self):
        assert MinerUModel(backend="vlm").requires_gpu is True
        assert MinerUModel(backend="pipeline").requires_gpu is False


# ========== MinerU parse_document（mock do_parse + 产物文件） ==========

def _stub_mineru_modules(fake_do_parse, fake_read_fn):
    """构造 mineru.cli.common 模块的 stub（mineru 未安装时用）。

    返回 (sys.modules 字典, 还原用备份) 供 patch.dict 使用。
    """
    import sys
    import types

    mineru_mod = types.ModuleType("mineru")
    cli_mod = types.ModuleType("mineru.cli")
    common_mod = types.ModuleType("mineru.cli.common")
    common_mod.do_parse = fake_do_parse
    common_mod.read_fn = fake_read_fn
    mineru_mod.cli = cli_mod
    cli_mod.common = common_mod

    stub = {
        "mineru": mineru_mod,
        "mineru.cli": cli_mod,
        "mineru.cli.common": common_mod,
    }
    return stub


class TestMinerUParseDocument:
    def test_parse_document_reads_markdown_output(self, tmp_path):
        """mock do_parse 写入 markdown 文件，验证读取+切分"""
        model = MinerUModel(backend="pipeline", output_dir=str(tmp_path))

        def fake_do_parse(output_dir, pdf_bytes_list, backend):
            os.makedirs(output_dir, exist_ok=True)
            with open(os.path.join(output_dir, "result.md"), "w",
                      encoding="utf-8") as f:
                f.write("# 标题\n段落内容")

        def fake_read_fn(path):
            return b"fake pdf bytes"

        stub = _stub_mineru_modules(fake_do_parse, fake_read_fn)
        with patch.dict("sys.modules", stub, clear=False):
            parsed = model.parse_document("/tmp/test.pdf")

        assert parsed.metadata["parser"] == "mineru"
        assert parsed.metadata["backend"] == "pipeline"
        assert len(parsed.chunks) >= 1
        assert any("段落内容" in c.content for c in parsed.chunks)

    def test_parse_document_no_markdown_returns_empty(self, tmp_path):
        model = MinerUModel(backend="pipeline", output_dir=str(tmp_path))

        def fake_do_parse(output_dir, pdf_bytes_list, backend):
            os.makedirs(output_dir, exist_ok=True)
            # 不写 markdown

        stub = _stub_mineru_modules(fake_do_parse, lambda path: b"x")
        with patch.dict("sys.modules", stub, clear=False):
            parsed = model.parse_document("/tmp/test.pdf")

        assert parsed.chunks == []
        assert "error" in parsed.metadata


# ========== MiniCPM-V 单图路径 ==========

class TestMiniCPMVModel:
    def test_single_image_path_calls_understand_image(self, tmp_path):
        """单图文件直接走 understand_image，不渲染分页"""
        model = MiniCPMVModel()
        img_path = tmp_path / "photo.png"
        img_path.write_bytes(b"fake img")

        with patch.object(model, "understand_image",
                          return_value="# 图\n图片描述") as mock_ui:
            parsed = model.parse_document(str(img_path))

        mock_ui.assert_called_once()
        assert len(parsed.images) == 1
        assert parsed.images[0].description == "# 图\n图片描述"
        assert parsed.metadata["page_count"] == 1

    def test_requires_gpu_true(self):
        assert MiniCPMVModel().requires_gpu is True

    def test_parse_image_no_description_yields_empty_chunks(self, tmp_path):
        model = MiniCPMVModel()
        img_path = tmp_path / "empty.png"
        img_path.write_bytes(b"x")
        with patch.object(model, "understand_image", return_value=""):
            parsed = model.parse_document(str(img_path))
        assert parsed.chunks == []
        assert len(parsed.images) == 1
