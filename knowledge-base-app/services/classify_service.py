"""AI 分类服务 — 预置分类树 + 受限分类 + 新分类审批 + 多归属

需求④：知识库管家 AI 对导入内容进行提取分类。
- 应用启动时把 presets.knowledge_taxonomy.PRESET_TAXONOMY 种子写入分类表（幂等）。
- 分类时硬性规定 AI 只能从现有分类树中选择 1~3 条完整路径（从一级开始）。
- 若现有分类均不合适，AI 可通过 propose_new 提议新分类：
  - 有 approval_hook（GUI 环境）时阻塞等待用户审批决定最终路径；
  - 无 approval_hook（CLI 环境）时直接归入 ["其他", "未分类"]，不自动建类。
- 一个知识可同时属于多个分类路径（多归属），每条路径都建关联。
- 分类结果同时写入 chunk.categories（扁平含祖先，供向量库过滤）与
  chunk.category_paths（完整层级路径，供目录遍历检索与溯源）。
"""
from __future__ import annotations

import json
import logging
import re
from typing import Optional

from interfaces.llm import LLMClient
from models.chunk import Chunk
from models.category import ChunkCategory
from presets.knowledge_taxonomy import PRESET_TAXONOMY

logger = logging.getLogger(__name__)

# 每个分类路径的最大层级深度（信息技术/编程/Python开发 之类 1~3 级）
MAX_DEPTH = 4

# AI 提议新分类被拒绝/无法审批时的兜底路径
FALLBACK_PATH = ["其他", "未分类"]


class ClassifyService:
    """AI 层级分类 + 受限选类 + 新分类审批 + 多归属"""

    def __init__(self, llm: LLMClient, category_repo=None, snowflake=None,
                 approval_hook=None):
        """
        Args:
            llm: LLM 客户端
            category_repo: 分类仓库（PG），缺失时分类退化为空关联
            snowflake: ID 生成器
            approval_hook: 新分类审批回调，签名
                hook(suggested_path: list[str], content_preview: str,
                     doc_name: str) -> list[str] | None
                返回最终使用的分类路径；返回 None 表示归入 ["其他", "未分类"]。
        """
        self.llm = llm
        self.category_repo = category_repo
        self.snowflake = snowflake
        self.approval_hook = approval_hook

    # ---------------------------------------------------------- 预置种子
    def ensure_preset_taxonomy(self) -> None:
        """把 PRESET_TAXONOMY 种子写入 category 表（幂等）。

        按 (parent_id, name.lower()) 查重，已存在则跳过；缺失的用
        snowflake.next_id() 生成 ID 逐级创建。
        """
        if self.category_repo is None or self.snowflake is None:
            logger.warning("category_repo 或 snowflake 缺失，跳过预置分类种子写入")
            return
        index = self._build_category_index()

        def _walk(node: dict, prefix: list[str]) -> None:
            for name, children in node.items():
                path = prefix + [name]
                self._ensure_category_path(path, index)
                if isinstance(children, dict) and children:
                    _walk(children, path)

        _walk(PRESET_TAXONOMY, [])
        logger.info("预置分类树种子写入完成")

    def classify(self, chunks: list[Chunk]) -> list[list[ChunkCategory]]:
        """对知识块批量分类，返回每个块的分类关联列表。

        副作用：同时填充每个 chunk 的 categories（扁平含祖先）与
        category_paths（完整层级路径），供后续向量库写入过滤字段。
        若后端无分类表（category_repo 缺失），则只返回空关联，不阻塞导入。
        """
        if self.category_repo is None or self.snowflake is None:
            return [[] for _ in chunks]

        # 每次调用重建现有分类索引（(parent_id, name_lower) -> category_id）
        cat_index = self._build_category_index()
        results = []
        for chunk in chunks:
            classifications = self._classify_one(chunk, cat_index)
            results.append(classifications)
        return results

    # ---------------------------------------------------------- 建类
    def _build_category_index(self) -> dict:
        """构建 (parent_id, name_lower) -> category_id 索引。"""
        index = {}
        try:
            categories = self.category_repo.list_all_categories()
        except Exception as e:
            logger.warning(f"读取现有分类失败: {e}")
            categories = []
        for c in categories:
            index[(c.parent_id, c.name.strip().lower())] = c.category_id
        return index

    def _build_tree_text(self) -> str:
        """从 DB 构建现有分类树的缩进文本（注入 prompt 用）。"""
        try:
            categories = self.category_repo.list_all_categories()
        except Exception as e:
            logger.warning(f"读取分类树失败: {e}")
            return "（分类树读取失败）"
        if not categories:
            return "（暂无分类）"

        children_map: dict = {}
        for c in categories:
            children_map.setdefault(c.parent_id, []).append(c)

        lines: list[str] = []
        visited: set = set()

        def _walk(parent_id, depth: int) -> None:
            for c in sorted(children_map.get(parent_id, []),
                            key=lambda x: x.name):
                if c.category_id in visited:
                    continue
                visited.add(c.category_id)
                lines.append("  " * depth + "- " + c.name)
                _walk(c.category_id, depth + 1)

        _walk(None, 0)
        # 兜底：父节点缺失的孤儿分类也列出，避免 AI 看不到
        for c in sorted(categories, key=lambda x: x.name):
            if c.category_id not in visited:
                lines.append("- " + c.name)
        return "\n".join(lines)

    def _ensure_category_path(self, path: list[str], index: dict) -> int:
        """确保分类路径存在，返回最细层级分类 ID。

        沿父链逐级查找，缺失则用 snowflake 生成 ID 并创建，同时写入索引避免重复。
        """
        parent_id = None
        leaf_id = None
        for name in path:
            name = (name or "").strip()
            if not name:
                continue
            key = (parent_id, name.lower())
            cid = index.get(key)
            if cid is None:
                cid = self.snowflake.next_id()
                try:
                    self.category_repo.insert_category(cid, name, parent_id, "")
                except Exception as e:
                    logger.warning(f"创建分类失败 {name}: {e}")
                    # 创建失败可能导致并发冲突，回退查询一次
                    cid = self._lookup_fallback(name, parent_id) or cid
                index[key] = cid
            leaf_id = cid
            parent_id = cid
        return leaf_id

    def _lookup_fallback(self, name: str, parent_id: Optional[int]):
        """并发下 insert 冲突时，重新查询该分类 ID（尽力而为）。"""
        try:
            for c in self.category_repo.list_all_categories():
                if c.name.strip().lower() == name.lower() \
                        and c.parent_id == parent_id:
                    return c.category_id
        except Exception:
            pass
        return None

    # ---------------------------------------------------------- 新分类审批
    def _resolve_proposed_path(self, proposed: list[str],
                               chunk: Chunk) -> list[str]:
        """处理 AI 提议的新分类路径。

        有 approval_hook 时阻塞等待用户决定：
        - hook 返回路径：使用该路径；
        - hook 返回 None 或调用异常：归入 ["其他", "未分类"]。
        无 approval_hook（CLI 环境）时直接归入 ["其他", "未分类"]，不自动建类。
        """
        if self.approval_hook is None:
            logger.info(f"无审批回调，新分类提议 {proposed} 归入 {FALLBACK_PATH}")
            return list(FALLBACK_PATH)
        try:
            decided = self.approval_hook(
                list(proposed), (chunk.content or "")[:200], chunk.doc_name)
        except Exception as e:
            logger.warning(f"新分类审批回调调用失败: {e}")
            return list(FALLBACK_PATH)
        if decided is None:
            return list(FALLBACK_PATH)
        final = [str(p).strip() for p in decided if str(p).strip()]
        return final or list(FALLBACK_PATH)

    # ---------------------------------------------------------- 单个块分类
    def _classify_one(self, chunk: Chunk, index: dict) -> list[ChunkCategory]:
        """对单个知识块分类。

        硬性规定模型只能从现有分类树中选择 1~3 条完整路径（从一级开始）；
        均不合适时允许通过 propose_new 提议新分类（走审批/兜底）。
        解析出若干 (path, confidence)，逐条建类并生成关联。
        """
        tree_text = self._build_tree_text()
        prompt = (
            "请对以下知识片段进行分类提取。\n"
            "硬性规定：只能从下面的现有分类树中选择 1~3 条最贴切的完整路径"
            "（必须从一级分类开始，逐级列出），不得编造树中不存在的分类。\n"
            "一个内容可同时属于多个分类路径，每条都要返回。\n\n"
            f"现有分类树：\n{tree_text}\n\n"
            "如果你认为所有现有分类都不合适，允许通过 \"propose_new\" 字段"
            "提议一条新分类路径（如 [\"一级\",\"二级\"]），此时 \"path\" 可为空数组。\n\n"
            f"知识片段: {chunk.content}\n\n"
            "返回 JSON 数组，每项格式：\n"
            '[{"path": ["一级","二级"], "confidence": 0.9, "propose_new": null}]'
        )
        try:
            resp = self.llm.chat([
                {"role": "system",
                 "content": "你是知识库管家，负责把知识分门别类。严格返回 JSON。"},
                {"role": "user", "content": prompt}
            ])
            content = resp.get("content", "") or ""
            items = self._parse_json_array(content)
        except Exception as e:
            logger.warning(f"分类 LLM 调用失败 chunk_id={chunk.chunk_id}: {e}")
            return []

        result = []
        flat_names: list[str] = []
        paths: list[list[str]] = []
        for item in items:
            try:
                confidence = float(item.get("confidence", 0.5))
            except (TypeError, ValueError):
                confidence = 0.5
            if confidence < 0.5:
                continue

            # 新分类提议：走审批回调或兜底 ["其他","未分类"]
            propose_new = item.get("propose_new")
            proposed = []
            if isinstance(propose_new, list):
                proposed = [str(p).strip() for p in propose_new
                            if str(p).strip()]
            if proposed:
                path = self._resolve_proposed_path(proposed, chunk)
            else:
                path = [str(p).strip() for p in (item.get("path") or [])]
                path = [p for p in path if p]
            if not path:
                continue
            # 截断超过 MAX_DEPTH 的路径
            if len(path) > MAX_DEPTH:
                path = path[:MAX_DEPTH]
            leaf_id = self._ensure_category_path(path, index)
            if leaf_id is None:
                continue
            result.append(ChunkCategory(
                chunk_id=chunk.chunk_id,
                category_id=leaf_id,
                confidence=confidence,
                assigned_by="ai",
            ))
            paths.append(path)
            for name in path:
                if name not in flat_names:
                    flat_names.append(name)

        # 写入扁平分类名（含祖先）与完整路径，供向量库过滤与溯源
        chunk.categories = flat_names
        chunk.category_paths = paths
        return result

    @staticmethod
    def _parse_json_array(content: str) -> list[dict]:
        """从模型输出中稳健地解析 JSON 数组。"""
        if not content:
            return []
        # 优先直接解析
        try:
            data = json.loads(content)
            if isinstance(data, list):
                return [d for d in data if isinstance(d, dict)]
        except Exception:
            pass
        # 回退：提取第一个 [...] 片段
        match = re.search(r'\[.*\]', content, re.DOTALL)
        if match:
            try:
                data = json.loads(match.group())
                if isinstance(data, list):
                    return [d for d in data if isinstance(d, dict)]
            except Exception:
                pass
        return []
