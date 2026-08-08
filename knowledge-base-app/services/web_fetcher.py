"""网页抓取服务 — 内置 URL 导入（纯 stdlib，零新增依赖）

流程：
1. fetch URL（浏览器 UA，跟随重定向，限制大小）
2. 正文提取（readability-lite：article/main/关键词容器打分 + 链接密度惩罚）
3. HTML → Markdown（保留标题/列表/引用/代码块结构，供结构感知分块）
4. 写临时 .md 文件，复用 FileService.import_document 走完整导入管道
   （解析 → 分块 → AI 分类 → 向量化 → 写存储），网页文档与本地文件同权。

直接文件链接（content-type 为 pdf/docx/图片/纯文本/markdown）跳过正文提取，
按原始字节落盘后走同一导入管道。
"""
from __future__ import annotations

import gzip
import logging
import os
import re
import tempfile
import urllib.request
import zlib
from html.parser import HTMLParser

logger = logging.getLogger(__name__)

MAX_BYTES = 8 * 1024 * 1024  # 网页正文 8MB 上限
DEFAULT_TIMEOUT = 20

USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36"
)

# content-type → 直接文件导入扩展名
_DIRECT_TYPES = {
    "application/pdf": ".pdf",
    "application/vnd.openxmlformats-officedocument.wordprocessingml.document": ".docx",
    "image/png": ".png",
    "image/jpeg": ".jpg",
    "text/plain": ".txt",
    "text/markdown": ".md",
}


class FetchError(Exception):
    """网页抓取失败"""


# ============================================================
# HTML 解析：DOM-lite 树 + 正文打分 + Markdown 序列化
# ============================================================
_SKIP_TAGS = {
    "script", "style", "noscript", "template", "iframe", "svg",
    "canvas", "form", "button", "select", "textarea", "option",
    "nav", "footer", "header", "aside",
}
_CONTAINER_BONUS = re.compile(
    r"article|content|post|entry|main|body|detail|text", re.I)
_CONTAINER_PENALTY = re.compile(
    r"comment|sidebar|widget|related|recommend|footer|nav|menu|ad", re.I)


class _Node:
    __slots__ = ("tag", "attrs", "children")

    def __init__(self, tag: str, attrs: dict):
        self.tag = tag
        self.attrs = attrs
        self.children: list = []  # _Node | str


class _TreeBuilder(HTMLParser):
    """把 body 解析为轻量节点树，同时捕获 <title>"""

    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.title = ""
        self.root = _Node("document", {})
        self._stack = [self.root]
        self._skip_depth = 0
        self._in_title = False

    def handle_starttag(self, tag, attrs):
        tag = tag.lower()
        attrs_d = dict(attrs)
        if tag == "title":
            self._in_title = True
            return
        if tag in _SKIP_TAGS:
            self._skip_depth += 1
            return
        if self._skip_depth:
            return
        node = _Node(tag, attrs_d)
        self._stack[-1].children.append(node)
        # void 元素不入栈
        if tag not in ("br", "hr", "img", "meta", "link", "input"):
            self._stack.append(node)

    def handle_startendtag(self, tag, attrs):
        tag = tag.lower()
        if tag in _SKIP_TAGS or self._skip_depth:
            return
        self._stack[-1].children.append(_Node(tag, dict(attrs)))

    def handle_endtag(self, tag):
        tag = tag.lower()
        if tag == "title":
            self._in_title = False
            return
        if tag in _SKIP_TAGS:
            if self._skip_depth:
                self._skip_depth -= 1
            return
        if self._skip_depth:
            return
        # 弹出到匹配标签（容错：未闭合标签直接跳过）
        for i in range(len(self._stack) - 1, 0, -1):
            if self._stack[i].tag == tag:
                del self._stack[i:]
                break

    def handle_data(self, data):
        if self._in_title:
            self.title += data
            return
        if self._skip_depth:
            return
        if data and data.strip():
            self._stack[-1].children.append(data)


def _text_of(node: _Node) -> str:
    parts = []

    def _walk(n):
        for c in n.children:
            if isinstance(c, str):
                parts.append(c)
            else:
                _walk(c)
    _walk(node)
    return "".join(parts)


def _link_text_len(node: _Node) -> int:
    total = [0]

    def _walk(n, in_a):
        for c in n.children:
            if isinstance(c, str):
                if in_a:
                    total[0] += len(c.strip())
            else:
                _walk(c, in_a or c.tag == "a")
    _walk(node, False)
    return total[0]


def _pick_main(root: _Node) -> _Node:
    """正文容器打分：关键词容器加分，链接密度惩罚，段落数加分"""
    best, best_score = root, 0.0

    def _score(n: _Node) -> float:
        text_len = len(_text_of(n).strip())
        if text_len < 200:
            return 0.0
        link_density = _link_text_len(n) / max(text_len, 1)
        bonus = 1.0
        ident = f"{n.attrs.get('id', '')} {n.attrs.get('class', '')}"
        if n.tag in ("article", "main"):
            bonus += 0.6
        if _CONTAINER_BONUS.search(ident):
            bonus += 0.4
        if _CONTAINER_PENALTY.search(ident):
            bonus -= 0.5
        paras = sum(1 for c in n.children
                    if not isinstance(c, str) and c.tag == "p")
        return (text_len + paras * 120) * max(bonus, 0.2) * (1 - link_density)

    def _visit(n: _Node):
        nonlocal best, best_score
        if n.tag in ("article", "main", "div", "section", "body"):
            s = _score(n)
            if s > best_score:
                best, best_score = n, s
        for c in n.children:
            if not isinstance(c, str):
                _visit(c)
    _visit(root)
    return best


_MD_BLOCK = {
    "p", "div", "section", "article", "main", "ul", "ol", "table",
    "tr", "figure", "figcaption", "blockquote", "pre", "body", "document",
}


def _to_markdown(node: _Node, out: list, depth: int = 0):
    """节点树 → Markdown 片段（追加到 out，块间以换行分隔）"""
    tag = node.tag
    if tag in ("h1", "h2", "h3", "h4", "h5", "h6"):
        level = int(tag[1])
        text = re.sub(r"\s+", " ", _text_of(node)).strip()
        if text:
            out.append("\n\n" + "#" * min(level + 1, 6) + " " + text + "\n\n")
        return
    if tag == "hr":
        out.append("\n---\n")
        return
    if tag == "br":
        out.append("\n")
        return
    if tag == "pre":
        text = _text_of(node).strip("\n")
        if text.strip():
            out.append("\n\n```\n" + text + "\n```\n\n")
        return
    if tag == "li":
        out.append("- ")
        for c in node.children:
            if isinstance(c, str):
                out.append(re.sub(r"\s+", " ", c))
            else:
                _to_markdown(c, out, depth + 1)
        out.append("\n")
        return
    if tag == "img":
        alt = (node.attrs.get("alt") or "").strip()
        if alt:
            out.append(f"[图片: {alt}]")
        return
    if tag == "a":
        text = re.sub(r"\s+", " ", _text_of(node)).strip()
        if text:
            out.append(text)
        return
    if tag in ("td", "th"):
        text = re.sub(r"\s+", " ", _text_of(node)).strip()
        out.append(text + " | ")
        return
    if tag == "blockquote":
        inner: list = []
        for c in node.children:
            if isinstance(c, str):
                inner.append(re.sub(r"\s+", " ", c))
            else:
                _to_markdown(c, inner, depth + 1)
        text = "".join(inner).strip()
        if text:
            lines = ["> " + ln.strip()
                     for ln in text.splitlines() if ln.strip()]
            out.append("\n\n" + "\n".join(lines) + "\n\n")
        return
    # 普通块级 / 行内元素
    if tag in _MD_BLOCK:
        out.append("\n\n")
    for c in node.children:
        if isinstance(c, str):
            # 与浏览器一致的空白收敛（pre 已在上方提前返回，不受影响）
            out.append(re.sub(r"\s+", " ", c))
        else:
            _to_markdown(c, out, depth + 1)
    if tag in _MD_BLOCK:
        out.append("\n\n")


def extract_content(html: str) -> tuple[str, str]:
    """从 HTML 提取 (title, markdown 正文)"""
    parser = _TreeBuilder()
    parser.feed(html)
    parser.close()
    title = re.sub(r"\s+", " ", parser.title).strip()
    main = _pick_main(parser.root)
    out: list = []
    _to_markdown(main, out)
    text = "".join(out)
    # 收敛多余空行
    text = re.sub(r"\n[ \t]*\n[ \t]*\n+", "\n\n", text)
    # 清理行首零散分隔符
    lines = [ln.rstrip() for ln in text.splitlines()]
    text = "\n".join(lines).strip()
    return title, text


# ============================================================
# 网络抓取
# ============================================================
def _decode_body(raw: bytes, headers) -> str:
    """按 Content-Encoding / charset 解码响应体"""
    encoding = (headers.get("Content-Encoding") or "").lower()
    if "gzip" in encoding:
        raw = gzip.decompress(raw)
    elif "deflate" in encoding:
        raw = zlib.decompress(raw)
    content_type = headers.get("Content-Type") or ""
    m = re.search(r"charset=([\w\-]+)", content_type, re.I)
    charset = m.group(1) if m else None
    if charset is None:
        head = raw[:4096].decode("ascii", errors="ignore")
        m = re.search(r'charset=["\']?([\w\-]+)', head, re.I)
        charset = m.group(1) if m else "utf-8"
    try:
        return raw.decode(charset, errors="replace")
    except LookupError:
        return raw.decode("utf-8", errors="replace")


def fetch_page(url: str, timeout: int = DEFAULT_TIMEOUT) -> dict:
    """抓取 URL，返回 {url, title, text, content_type, raw}

    - HTML 页面：提取正文转 Markdown 放入 text
    - 直接文件链接（pdf/docx/图片/txt/md）：text 为空，raw 为原始字节
    """
    url = (url or "").strip()
    if not re.match(r"^https?://", url, re.I):
        raise FetchError(f"仅支持 http/https 链接: {url or '(空)'}")

    req = urllib.request.Request(url, headers={
        "User-Agent": USER_AGENT,
        "Accept": "text/html,application/xhtml+xml,application/pdf,"
                  "text/plain,image/*;q=0.8,*/*;q=0.5",
        "Accept-Language": "zh-CN,zh;q=0.9,en;q=0.8",
    })
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            final_url = resp.geturl()
            headers = resp.headers
            content_type = (headers.get("Content-Type") or "").split(";")[0]\
                .strip().lower()
            chunks = []
            total = 0
            while True:
                buf = resp.read(64 * 1024)
                if not buf:
                    break
                chunks.append(buf)
                total += len(buf)
                if total > MAX_BYTES:
                    raise FetchError(f"页面超过大小上限（{MAX_BYTES // 1024 // 1024}MB）")
            raw = b"".join(chunks)
    except FetchError:
        raise
    except Exception as e:
        raise FetchError(f"抓取失败: {e}") from e

    if content_type in _DIRECT_TYPES:
        return {"url": final_url, "title": "", "text": "",
                "content_type": content_type, "raw": raw}

    html = _decode_body(raw, headers)
    title, text = extract_content(html)
    if not text.strip():
        raise FetchError("未能提取网页正文（页面可能为空或需登录）")
    return {"url": final_url, "title": title, "text": text,
            "content_type": content_type or "text/html", "raw": b""}


# ============================================================
# 导入管道对接
# ============================================================
def _safe_filename(name: str, default: str = "webpage") -> str:
    name = re.sub(r'[\\/:*?"<>|\r\n\t]+', " ", (name or "").strip())
    name = re.sub(r"\s+", " ", name).strip(" .")
    if not name:
        name = default
    return name[:80]


def import_from_url(url: str, file_service, progress_cb=None) -> int:
    """抓取 URL 并通过 FileService 走完整导入管道。

    Args:
        url: http/https 链接（网页或直接文件链接）
        file_service: FileService 实例
        progress_cb: 进度回调 callable(percent, message)
    Returns:
        doc_id
    """
    def _report(pct: int, msg: str):
        if progress_cb is not None:
            try:
                progress_cb(pct, msg)
            except Exception:
                pass

    _report(2, "抓取网页")
    page = fetch_page(url)
    ext = _DIRECT_TYPES.get(page["content_type"])

    try:
        from utils.paths import get_tmp_dir
        base_tmp = get_tmp_dir()
    except Exception:
        base_tmp = None
    tmp_dir = tempfile.mkdtemp(prefix="web_", dir=base_tmp)

    if ext is not None:
        # 直接文件链接：按原始字节落盘
        name = os.path.basename(page["url"].split("?")[0]) or f"download{ext}"
        if not name.lower().endswith(ext):
            name = _safe_filename(os.path.splitext(name)[0]) + ext
        local_path = os.path.join(tmp_dir, _safe_filename(name))
        with open(local_path, "wb") as f:
            f.write(page["raw"])
    else:
        title = page["title"] or page["url"]
        md = f"# {title}\n\n> 来源: {page['url']}\n\n{page['text']}\n"
        local_path = os.path.join(tmp_dir, _safe_filename(title) + ".md")
        with open(local_path, "w", encoding="utf-8") as f:
            f.write(md)

    try:
        logger.info(f"网页已抓取 {page['url']} → {local_path}")
        return file_service.import_document(local_path, progress_cb=progress_cb)
    finally:
        try:
            if os.path.exists(local_path):
                os.remove(local_path)
            os.rmdir(tmp_dir)
        except OSError as e:
            logger.warning(f"清理网页临时文件失败: {e}")
