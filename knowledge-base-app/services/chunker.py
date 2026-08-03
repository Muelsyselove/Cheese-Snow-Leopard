"""结构感知分块器 — 自研核心逻辑。

技术文档 3.4 分块策略：
- 以 Markdown 标题/段落/表格为原子单元（structure-aware）
- 目标块大小 target_tokens（默认 300），重叠 overlap_ratio（默认 0.15）
- 小于 min_chunk_tokens 的尾块合并到前一块，避免碎片
- 图片/表格/公式块原样保留（切分会破坏结构）

算法分层（由粗到细）：
1. 段落为基本累积单元（空行分隔），Markdown 标题行（#）作为硬分节边界
2. 单段落超过 target_tokens 时按句子（。.!?）切分
3. 句子仍超长时按 target_tokens 字符硬切（兜底，保证不超长）

元数据契约：
- page_number / bbox 从源块继承
- char_start / char_end 为相对于源块 content 的字符偏移
- chunk_id / doc_id / doc_name / content_hash 由 file_service 在分块后注入
"""
from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Optional

from interfaces.chunker import Chunker, TokenCounter
from interfaces.parser import ParsedDocument
from models.chunk import Chunk


# ---------------------------------------------------------------------------
# Token 计数器
# ---------------------------------------------------------------------------
class CharTokenCounter:
    """基于字符的近似 token 计数器（无第三方依赖）。

    估算规则（适配中英混合的 BGE-M3 / Qwen3 tokenizer 特性）：
    - CJK 字符（含中文/日文/韩文/全角符号）：1 字符 ≈ 1 token
    - 其他字符（英文/数字/ASCII 符号）：约 4 字符 ≈ 1 token

    精度足以用于块大小控制；需精确计数时可注入真实 tokenizer 适配器。
    """

    # CJK 统一表意文字及常见全角字符范围
    _CJK_RANGES = (
        (0x4E00, 0x9FFF),    # CJK 统一表意文字
        (0x3400, 0x4DBF),    # CJK 扩展 A
        (0x3000, 0x303F),    # CJK 符号和标点
        (0xFF00, 0xFFEF),    # 全角字符
        (0x3040, 0x309F),    # 平假名
        (0x30A0, 0x30FF),    # 片假名
        (0xAC00, 0xD7AF),    # 韩文音节
    )

    @classmethod
    def _is_cjk(cls, ch: str) -> bool:
        cp = ord(ch)
        for lo, hi in cls._CJK_RANGES:
            if lo <= cp <= hi:
                return True
        return False

    def count(self, text: str) -> int:
        if not text:
            return 0
        cjk = 0
        other = 0
        for ch in text:
            if self._is_cjk(ch):
                cjk += 1
            else:
                other += 1
        # 非 CJK 每 4 字符约 1 token，向上取整
        return cjk + (other + 3) // 4


# ---------------------------------------------------------------------------
# 内部数据结构
# ---------------------------------------------------------------------------
@dataclass
class _Span:
    """文本片段，记录在源块 content 中的字符偏移"""
    text: str
    start: int   # 相对源块 content 的起始偏移
    end: int     # 相对源块 content 的结束偏移（ exclusive）


# ---------------------------------------------------------------------------
# 结构感知分块器
# ---------------------------------------------------------------------------
class StructureAwareChunker(Chunker):
    """结构感知分块器

    配置项（来自 config.chunking）：
    - target_tokens: 目标块 token 数（默认 300）
    - overlap_ratio: 重叠比例（默认 0.15）
    - min_chunk_tokens: 最小块 token 数，尾块不足则合并（默认 50）
    """

    # Markdown 标题行正则（# ~ ######）
    _HEADING_RE = re.compile(r"^(#{1,6})\s+\S")
    # 句子分隔符（中英文句末标点 + 换行）
    _SENTENCE_SPLIT_RE = re.compile(r"(?<=[。！？!?\.])\s+")

    def __init__(self, target_tokens: int = 300, overlap_ratio: float = 0.15,
                 min_chunk_tokens: int = 50, token_counter: Optional[TokenCounter] = None):
        if target_tokens <= 0:
            raise ValueError(f"target_tokens 必须为正数，实际: {target_tokens}")
        if not (0.0 <= overlap_ratio < 1.0):
            raise ValueError(f"overlap_ratio 须在 [0, 1)，实际: {overlap_ratio}")
        if min_chunk_tokens < 0:
            raise ValueError(f"min_chunk_tokens 不可为负，实际: {min_chunk_tokens}")
        if min_chunk_tokens >= target_tokens:
            raise ValueError(
                f"min_chunk_tokens({min_chunk_tokens}) 须小于 target_tokens({target_tokens})"
            )

        self.target_tokens = target_tokens
        self.overlap_ratio = overlap_ratio
        self.min_chunk_tokens = min_chunk_tokens
        self.overlap_tokens = int(target_tokens * overlap_ratio)
        self.counter = token_counter or CharTokenCounter()

    # ---------------- 公共入口 ----------------
    def split(self, parsed: ParsedDocument) -> list[Chunk]:
        """将 ParsedDocument 切分为目标 token 数的 Chunk 列表。

        - text 块：结构感知切分
        - image / table / formula 块：原样保留
        """
        result: list[Chunk] = []
        for src in parsed.chunks:
            if src.chunk_type == "text":
                result.extend(self._split_text_block(src))
            else:
                # 图片/表格/公式块原样保留，不参与切分
                result.append(self._clone_block(src))
        return result

    # ---------------- 文本块切分 ----------------
    def _split_text_block(self, src: Chunk) -> list[Chunk]:
        """对单个文本块执行结构感知切分"""
        text = src.content
        if not text or not text.strip():
            return []

        # 是否含 Markdown 标题行（标题为硬语义边界，即便总长未超 target 也按节切分）
        has_heading = any(
            self._HEADING_RE.match(line.strip())
            for line in text.split("\n")
        )

        # 无标题且单块未超目标，直接返回（克隆并保留元数据）
        if not has_heading and self.counter.count(text) <= self.target_tokens:
            return [self._clone_block(src)]

        spans = self._split_into_spans(text)
        if not spans:
            return []

        # 累积切块
        chunks = self._accumulate(spans, src)
        return chunks

    def _split_into_spans(self, text: str) -> list[_Span]:
        """将文本按段落/标题边界分割为 span 列表，保留字符偏移。

        - 空行分隔段落
        - Markdown 标题行作为独立 span（硬分节边界）
        - 单段落过长时按句子进一步切分
        """
        spans: list[_Span] = []
        # 按行遍历，累积段落
        para_start: Optional[int] = None
        para_lines: list[str] = []

        def flush_para(end_idx: int):
            """把当前累积的段落输出为 span"""
            nonlocal para_start, para_lines
            if para_start is None or not para_lines:
                para_start = None
                para_lines = []
                return
            # 段落文本（含内部换行，保留结构）
            joined = "\n".join(para_lines)
            # 去掉尾部空行产生的多余换行
            joined = joined.rstrip()
            if joined:
                spans.append(_Span(text=joined, start=para_start, end=end_idx))
            para_start = None
            para_lines = []

        idx = 0
        lines = text.split("\n")
        for i, line in enumerate(lines):
            is_last = (i == len(lines) - 1)
            stripped = line.strip()
            line_end = idx + len(line)

            if not stripped:
                # 空行 → 段落边界
                flush_para(idx)
            elif self._HEADING_RE.match(stripped):
                # 标题行 → 先结束当前段落，标题独立成 span
                flush_para(idx)
                spans.append(_Span(text=line, start=idx, end=line_end))
            else:
                if para_start is None:
                    para_start = idx
                para_lines.append(line)

            # 推进到下一行起点（+1 为换行符）
            idx = line_end + 1

        flush_para(idx)

        # 过长 span 按句子切分
        refined: list[_Span] = []
        for sp in spans:
            if self.counter.count(sp.text) <= self.target_tokens:
                refined.append(sp)
            else:
                refined.extend(self._split_long_span(sp))
        return refined

    def _split_long_span(self, span: _Span) -> list[_Span]:
        """过长 span 按句子切分；句子仍超长按字符硬切（兜底）"""
        # 按句子分割，保留每句在 span 内的偏移
        sentences: list[_Span] = []
        pos = 0
        text = span.text
        last = 0
        for m in self._SENTENCE_SPLIT_RE.finditer(text):
            end = m.end()
            sent = text[last:end].strip()
            if sent:
                sentences.append(_Span(
                    text=sent,
                    start=span.start + last,
                    end=span.start + end,
                ))
            last = end
        # 尾部剩余
        if last < len(text):
            tail = text[last:].strip()
            if tail:
                sentences.append(_Span(
                    text=tail,
                    start=span.start + last,
                    end=span.end,
                ))

        if not sentences:
            return [span]

        # 句子仍超长 → 按字符硬切
        result: list[_Span] = []
        for sent in sentences:
            if self.counter.count(sent.text) <= self.target_tokens:
                result.append(sent)
            else:
                result.extend(self._hard_split_by_chars(sent))
        return result

    def _hard_split_by_chars(self, span: _Span) -> list[_Span]:
        """字符级硬切（兜底）：按 token 数近似估算字符步长切分"""
        text = span.text
        total = len(text)
        # 估算每 target_tokens 对应的字符数
        sample_tokens = self.counter.count(text)
        if sample_tokens <= 0:
            return [span]
        chars_per_token = total / sample_tokens
        step = max(1, int(self.target_tokens * chars_per_token))
        result: list[_Span] = []
        s = 0
        while s < total:
            e = min(s + step, total)
            piece = text[s:e]
            result.append(_Span(text=piece, start=span.start + s, end=span.start + e))
            s = e
        return result

    # ---------------- 累积切块 + overlap + 尾块合并 ----------------
    def _accumulate(self, spans: list[_Span], src: Chunk) -> list[Chunk]:
        """累积 span 到目标 token 数，处理 overlap 与尾块合并"""
        result: list[Chunk] = []
        current_spans: list[_Span] = []
        current_tokens = 0
        prev_block_text: Optional[str] = None  # 上一块的文本，用于取 overlap

        def make_chunk(spans_list: list[_Span]) -> Chunk:
            # 相邻 span 在源文本中连续（end==start）时无缝拼接，
            # 否则用换行分隔（保留段落/标题边界结构）
            parts: list[str] = []
            for i, s in enumerate(spans_list):
                if i == 0:
                    parts.append(s.text)
                else:
                    prev = spans_list[i - 1]
                    sep = "" if s.start == prev.end else "\n"
                    parts.append(sep)
                    parts.append(s.text)
            content = "".join(parts)
            return Chunk(
                chunk_id=0,              # 占位，file_service 注入
                content_hash="",         # 占位，file_service 注入
                doc_id=src.doc_id,
                doc_name=src.doc_name,
                content=content,
                chunk_type="text",
                page_number=src.page_number,
                char_start=spans_list[0].start,
                char_end=spans_list[-1].end,
                bbox=src.bbox,
            )

        def emit():
            nonlocal prev_block_text
            if not current_spans:
                return
            chunk = make_chunk(current_spans)
            result.append(chunk)
            prev_block_text = chunk.content

        for sp in spans:
            sp_tokens = self.counter.count(sp.text)

            # 标题行是硬边界：遇到标题先切出当前块
            is_heading = bool(self._HEADING_RE.match(sp.text.strip()))

            if current_spans and (
                is_heading
                or current_tokens + sp_tokens > self.target_tokens
            ):
                # 当前块已满或遇到硬边界 → 切出
                emit()
                current_spans = []
                current_tokens = 0

                # overlap：从前块尾部取一段作为新块开头
                if prev_block_text and self.overlap_tokens > 0:
                    ov_span = self._take_overlap_span(prev_block_text, src)
                    if ov_span is not None:
                        current_spans.append(ov_span)
                        current_tokens = self.counter.count(ov_span.text)

            # 加入当前块
            current_spans.append(sp)
            current_tokens += sp_tokens

        # 尾块处理
        if current_spans:
            if (current_tokens < self.min_chunk_tokens
                    and result and prev_block_text is not None):
                # 尾块过小 → 合并到前一块（连续切片无缝拼接）
                last = result[-1]
                tail_parts: list[str] = []
                for i, s in enumerate(current_spans):
                    if i == 0:
                        tail_parts.append(s.text)
                    else:
                        prev = current_spans[i - 1]
                        sep = "" if s.start == prev.end else "\n"
                        tail_parts.append(sep)
                        tail_parts.append(s.text)
                tail_text = "".join(tail_parts)
                # 尾块开头与前块末尾连续则无缝，否则换行
                sep = "" if (current_spans[0].start == last.char_end) else "\n"
                last.content = last.content + sep + tail_text
                last.char_end = current_spans[-1].end
            else:
                emit()

        return result

    def _take_overlap_span(self, prev_text: str, src: Chunk) -> Optional[_Span]:
        """从前一块文本尾部取约 overlap_tokens 数量的内容，在句子边界尽量对齐。

        严格限制 overlap 不超过前块长度（避免整块重复）。
        返回 span.start/end 为相对源块 content 的偏移。
        """
        if self.overlap_tokens <= 0 or not prev_text:
            return None

        # 估算 overlap 对应的字符数
        total_tokens = self.counter.count(prev_text)
        if total_tokens <= 0:
            return None
        chars_per_token = len(prev_text) / total_tokens
        target_chars = int(self.overlap_tokens * chars_per_token)

        # overlap 不应超过前块长度的一半（避免整块重复）
        max_chars = len(prev_text) // 2
        if target_chars <= 0 or max_chars <= 0:
            return None
        target_chars = min(target_chars, max_chars)

        # 从尾部向前定位起点
        start_char = len(prev_text) - target_chars
        # 在起点附近向后找句子结束符，对齐到句子边界（避免截断句子）
        align_start = start_char
        search_end = min(start_char + 20, len(prev_text))
        for i in range(start_char, search_end):
            if prev_text[i] in "。！？!?\n":
                align_start = i + 1
                break

        overlap_text = prev_text[align_start:]
        if not overlap_text:
            return None

        # 映射回源块偏移
        base = src.content.find(prev_text)
        if base >= 0:
            abs_start = base + align_start
            abs_end = base + len(prev_text)
        else:
            abs_start = align_start
            abs_end = len(prev_text)

        return _Span(text=overlap_text, start=abs_start, end=abs_end)

    # ---------------- 辅助 ----------------
    @staticmethod
    def _clone_block(src: Chunk) -> Chunk:
        """克隆非文本块（image/table/formula），原样保留"""
        return Chunk(
            chunk_id=src.chunk_id,
            content_hash=src.content_hash,
            doc_id=src.doc_id,
            doc_name=src.doc_name,
            content=src.content,
            chunk_type=src.chunk_type,
            page_number=src.page_number,
            char_start=src.char_start,
            char_end=src.char_end,
            bbox=src.bbox,
            vector_id=src.vector_id,
            categories=list(src.categories),
            created_at=src.created_at,
        )
