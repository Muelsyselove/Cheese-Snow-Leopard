"""VLM 方案A：PaddleOCR-VL-0.9B（CPU 可运行·无 GPU 首选）

注：API 以 paddleocr 实际导出为准，本实现按 paddleocr>=2.7 的 predict() 返回
带 markdown / layout / json 字段的对象约定。版本差异通过 _extract_markdown 适配。

解析输出约定（技术文档 3.4 分块策略）：
- markdown 文本按标题/段落/表格原子单元切分为粗粒度 Chunk（chunker 后续精切）
- 图片块从 layout 提取，content 暂留占位（由 understand_image 生成描述后回填）
- 所有 Chunk 的 chunk_id / doc_id / content_hash 由 file_service 后续注入
"""
from __future__ import annotations

import logging
import re
from typing import Optional

from interfaces.parser import DocumentParser, ParsedDocument, ImageBlock
from models.chunk import Chunk

logger = logging.getLogger(__name__)


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
        """解析文档，返回结构化 ParsedDocument。

        将 model.predict 输出的 markdown 文本按结构切分为粗粒度 Chunk：
        - 一级/二级标题作为分块边界
        - 表格块（```...``` 或 |...|）整体保留，chunk_type="table"
        - 其余按段落（空行分隔）切分，chunk_type="text"
        """
        model = self._get_model()
        result = model.predict(file_path)

        markdown = self._extract_markdown(result)
        page_count = self._extract_page_count(result)
        chunks = _markdown_to_chunks(markdown, page_total=page_count)
        images: list[ImageBlock] = []  # PaddleOCR-VL 默认输出 markdown，图片块由内联文本表征

        logger.info(
            f"PaddleOCR-VL 解析完成 file={file_path} chunks={len(chunks)} "
            f"pages={page_count}"
        )
        return ParsedDocument(
            chunks=chunks, images=images,
            metadata={"parser": "paddleocr_vl", "file": file_path,
                      "page_count": page_count}
        )

    def understand_image(self, image_path: str, prompt: str) -> str:
        """单独图片理解，返回 markdown 文本"""
        model = self._get_model()
        result = model.predict(image_path)
        return self._extract_markdown(result)

    @property
    def requires_gpu(self) -> bool:
        return False

    # ------------------------------------------------------------------
    # 兼容多版本的 result 字段提取
    # ------------------------------------------------------------------
    @staticmethod
    def _extract_markdown(result) -> str:
        """从 paddleocr predict 结果中提取 markdown 文本。

        兼容多种返回形态：对象属性 markdown / dict markdown / 直接字符串。
        """
        if result is None:
            return ""
        # 对象属性 result.markdown
        md = getattr(result, "markdown", None)
        if isinstance(md, str):
            return md
        # dict result["markdown"]
        if isinstance(result, dict):
            md = result.get("markdown") or result.get("md_content") or ""
            if isinstance(md, str):
                return md
        # 直接返回字符串
        if isinstance(result, str):
            return result
        logger.warning(f"PaddleOCR 结果未能提取 markdown，类型={type(result)}")
        return ""

    @staticmethod
    def _extract_page_count(result) -> Optional[int]:
        """从结果中提取页数（可能不存在）"""
        for attr in ("page_count", "num_pages", "pages"):
            val = getattr(result, attr, None)
            if isinstance(val, int) and val > 0:
                return val
        if isinstance(result, dict):
            for key in ("page_count", "num_pages", "pages"):
                val = result.get(key)
                if isinstance(val, int) and val > 0:
                    return val
        return None


# ==================================================================
# Markdown → Chunk 切分（粗粒度，供 chunker 进一步精切）
# ==================================================================

# 表格块识别：``` fenced code 或连续 | ... | 行
_TABLE_FENCE_RE = re.compile(r"```[^\n]*\n.*?\n```", re.DOTALL)
_TABLE_PIPE_RE = re.compile(r"^(\|.*\|)\s*$", re.MULTILINE)
# 标题行识别（# ~ ######）
_HEADING_RE = re.compile(r"^(#{1,6})\s+(.*)$", re.MULTILINE)


def _markdown_to_chunks(markdown: str, page_total: Optional[int] = None) -> list[Chunk]:
    """将 markdown 文本按结构切分为粗粒度 Chunk 列表。

    切分策略（技术文档 3.4）：
    1. 先抽取 fenced code / 表格块为独立 table 类块
    2. 剩余文本按标题边界分段，再按空行切段落
    3. 每段生成一个 Chunk，chunk_type=text（默认）/table（表格）
    """
    if not markdown or not markdown.strip():
        return []

    chunks: list[Chunk] = []
    char_cursor = 0  # 全局字符偏移，用于 char_start/char_end

    # ① 先抽 fenced 表格/代码块，标记其区间后从主文本移除
    table_spans: list[tuple[int, int, str]] = []  # (start, end, content)
    for m in _TABLE_FENCE_RE.finditer(markdown):
        table_spans.append((m.start(), m.end(), m.group(0)))
    # 连续 | ... | 行也算表格块（合并相邻 pipe 行为一个块）
    pipe_consumed: list[tuple[int, int]] = []  # 已合并的区间，避免重复
    for m in _TABLE_PIPE_RE.finditer(markdown):
        start = m.start()
        # 跳过已被合并进某 pipe 块的行
        if any(s <= start < e for s, e in pipe_consumed):
            continue
        # 跳过与 fenced 块重叠的行
        if any(s[0] <= start < s[1] for s in table_spans):
            continue
        # 向后扩展到连续的 pipe 行整体
        # 找到当前行末的换行符，逐行向下判断是否仍为 pipe 行
        end = m.end()
        # 跳过当前行末的 \n（若有），定位到下一行起点
        while end < len(markdown) and markdown[end] in "\r\n":
            end += 1
        # 逐行扩展
        while end < len(markdown):
            nl_pos = markdown.find("\n", end)
            if nl_pos == -1:
                # 最后一行（无尾随 \n）
                line = markdown[end:]
            else:
                line = markdown[end:nl_pos]
            stripped = line.strip()
            if stripped.startswith("|") and stripped.endswith("|") and stripped != "|":
                # 仍是 pipe 行，end 推进到该行末（含 \n）
                end = nl_pos + 1 if nl_pos != -1 else len(markdown)
            else:
                break
        pipe_consumed.append((start, end))
        table_spans.append((start, end, markdown[start:end]))

    table_spans.sort(key=lambda s: s[0])
    # 构造非表格区间列表
    non_table_segments: list[tuple[int, int]] = []
    prev = 0
    for s, e, _ in table_spans:
        if s > prev:
            non_table_segments.append((prev, s))
        prev = e
    if prev < len(markdown):
        non_table_segments.append((prev, len(markdown)))

    # ② 表格块直接生成 Chunk
    for s, e, content in table_spans:
        content = content.strip()
        if not content:
            continue
        chunks.append(Chunk(
            chunk_id=0,  # 由 file_service 注入
            content_hash="",  # 由 file_service 注入
            doc_id=0,  # 由 file_service 注入
            doc_name="",
            content=content,
            chunk_type="table",
            page_number=1,
            char_start=s,
            char_end=e,
        ))

    # ③ 非表格区间按标题/段落切分
    for seg_start, seg_end in non_table_segments:
        seg_text = markdown[seg_start:seg_end]
        for piece, rel_start, rel_end in _split_text_by_structure(seg_text):
            abs_start = seg_start + rel_start
            abs_end = seg_start + rel_end
            chunk_type = _infer_chunk_type(piece)
            chunks.append(Chunk(
                chunk_id=0,
                content_hash="",
                doc_id=0,
                doc_name="",
                content=piece,
                chunk_type=chunk_type,
                page_number=1,
                char_start=abs_start,
                char_end=abs_end,
            ))

    # 按 char_start 排序，保持文档顺序
    chunks.sort(key=lambda c: (c.char_start or 0, c.char_end or 0))
    logger.debug(f"markdown 切分完成: {len(chunks)} 个粗粒度块")
    return chunks


def _split_text_by_structure(text: str) -> list[tuple[str, int, int]]:
    """按标题边界与空行切分段落，返回 (片段文本, 相对起点, 相对终点) 列表。"""
    pieces: list[tuple[str, int, int]] = []
    # 标题位置作为分块边界
    boundaries = [m.start() for m in _HEADING_RE.finditer(text)]
    boundaries.append(len(text))

    prev = 0
    for b in boundaries:
        section = text[prev:b]
        if section.strip():
            # section 内再按空行切段落
            para_start = 0
            for m in re.finditer(r"\n\s*\n", section):
                para = section[para_start:m.start()].strip()
                if para:
                    pieces.append((para, prev + para_start, prev + m.start()))
                para_start = m.end()
            tail = section[para_start:].strip()
            if tail:
                pieces.append((tail, prev + para_start, prev + len(section)))
        prev = b
    return pieces


def _infer_chunk_type(text: str) -> str:
    """根据文本特征推断块类型（image 占位由 file_service 处理，此处只识别 table/formula）。"""
    stripped = text.strip()
    if stripped.startswith("|") and stripped.endswith("|"):
        return "table"
    if stripped.startswith("$$") or stripped.startswith("\\("):
        return "formula"
    return "text"


def _content_hash(text: str) -> str:
    """SHA-256 内容指纹（保留兼容旧调用）"""
    import hashlib
    return hashlib.sha256(text.encode("utf-8")).hexdigest()
