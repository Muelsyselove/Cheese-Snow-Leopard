"""Agentic RAG 编排服务

关键技术决策：不使用 LangGraph prebuilt ToolNode（它只把 tool 结果包成 ToolMessage
放回 messages，不会更新自定义状态字段）。改为自定义 tools 节点，在调用检索后显式
写入 state["retrieved_chunks"]，确保系统级溯源兜底通道可用。

注意：本文件不使用 `from __future__ import annotations`，因为 LangGraph 的
StateGraph 在 compile 时会调用 get_type_hints() 解析 TypedDict 注解，
若注解为字符串（lazy evaluation）则无法在函数局部作用域中解析 Annotated 和
自定义 reducer 函数，导致 NameError。
"""
import logging
import json
from typing import Optional, Annotated, TypedDict, Literal

from interfaces.embedder import Embedder
from interfaces.llm import LLMClient
from interfaces.vectorstore import VectorStore
from models.chunk import Chunk

logger = logging.getLogger(__name__)


def _to_openai_messages(messages: list) -> list[dict]:
    """将 langchain 消息对象 / 原始 dict 统一转为 OpenAI dict 格式

    OpenAI SDK 无法序列化 langchain 的 HumanMessage/AIMessage/ToolMessage，
    需在调用前转换为 {"role": ..., "content": ...} 字典。
    """
    result = []
    for m in messages:
        # 已经是 dict
        if isinstance(m, dict):
            result.append(m)
            continue
        # langchain 消息对象
        content = getattr(m, "content", "") or ""
        tool_calls = getattr(m, "tool_calls", None)
        # 判断类型
        cls_name = type(m).__name__
        if cls_name == "HumanMessage":
            result.append({"role": "user", "content": content})
        elif cls_name == "AIMessage":
            msg = {"role": "assistant", "content": content}
            # 转换 tool_calls 为 OpenAI 格式
            if tool_calls:
                openai_calls = []
                for tc in tool_calls:
                    # 已是 OpenAI 格式（含 function/arguments）
                    if isinstance(tc, dict) and "function" in tc:
                        openai_calls.append(tc)
                        continue
                    # langchain dict 格式：{name, args, id, type}
                    if isinstance(tc, dict):
                        openai_calls.append({
                            "id": tc.get("id", ""),
                            "type": "function",
                            "function": {
                                "name": tc.get("name", ""),
                                "arguments": json.dumps(tc.get("args", {}), ensure_ascii=False),
                            },
                        })
                        continue
                    # langchain 对象格式
                    openai_calls.append({
                        "id": getattr(tc, "id", ""),
                        "type": "function",
                        "function": {
                            "name": getattr(tc, "name", ""),
                            "arguments": getattr(tc, "args", ""),
                        },
                    })
                msg["tool_calls"] = openai_calls
            result.append(msg)
        elif cls_name == "ToolMessage":
            result.append({
                "role": "tool",
                "content": content,
                "tool_call_id": getattr(m, "tool_call_id", ""),
            })
        elif cls_name == "SystemMessage":
            result.append({"role": "system", "content": content})
        else:
            # 兜底：尝试按 content 输出为 user 消息
            result.append({"role": "user", "content": content})
    return result


class RagService:
    """Agentic RAG 编排 + 混合检索"""

    def __init__(self, embedder: Embedder, llm: LLMClient,
                 qdrant_store: VectorStore, config: dict):
        self.embedder = embedder
        self.llm = llm
        self.qdrant = qdrant_store
        self.config = config
        self.last_hit_chunk_ids: list[int] = []  # 缓存最近一次检索命中 ID
        self.last_retrieved_chunks: set[str] = set()  # 最近一次流式查询的命中块 ID

    def hybrid_search(self, query: str, top_k: int = 20,
                      filters: Optional[dict] = None) -> list[Chunk]:
        """混合检索：dense + sparse，RRF 融合

        技术文档 6.2 三级管道：
        - Dense 检索 → Qdrant cosine top top_k_dense
        - Sparse 检索 → Qdrant BM25 top top_k_sparse（BGE-M3 客户端 sparse / Qwen3 服务端 bm25）
        - RRF 融合 → final_top_k
        """
        query_vec = self.embedder.encode_query(query)
        # 附加 query_text 供 Qwen3 降级模式的服务端 BM25 使用
        try:
            object.__setattr__(query_vec, "query_text", query)
        except (AttributeError, TypeError):
            if hasattr(query_vec, "__dict__"):
                query_vec.query_text = query

        cfg = self.config or {}
        top_k_dense = cfg.get("top_k_dense", top_k)
        top_k_sparse = cfg.get("top_k_sparse", top_k)
        rrf_k = cfg.get("rrf_k", 60)
        final_top_k = cfg.get("final_top_k", top_k)

        results = self.qdrant.search(
            query_vec,
            top_k=final_top_k,
            filters=filters,
        )
        self.last_hit_chunk_ids = [c.chunk_id for c in results]
        return results

    def query(self, user_question: str, history: list[dict] = None,
              llm=None) -> dict:
        """Agentic RAG 查询，返回答案 + 命中块 ID 集合（字符串形式）

        Args:
            llm: 可选的 LLM 客户端覆盖（用于对话页选择不同模型）
        Returns:
            {"answer": str, "retrieved_chunks": set[str]}
        """
        used_llm = llm or self.llm
        from langgraph.graph import StateGraph, START, END
        from langchain_core.tools import tool
        from langchain_core.messages import ToolMessage, HumanMessage, AIMessage

        retrieved_set: set[str] = set()

        def _append_list(left: list, right: list) -> list:
            return (left or []) + (right or [])

        class AgentState(TypedDict):
            messages: list
            retrieved_chunks: Annotated[list[str], _append_list]

        @tool
        def knowledge_search(query: str) -> str:
            """搜索知识库相关内容"""
            results = self.hybrid_search(query, top_k=20)
            formatted = []
            for chunk in results:
                # chunk_id 统一渲染为 "chunk_<snowflake_id>" 字符串（见 7.1）
                formatted.append(f"【chunk_{chunk.chunk_id}】{chunk.content}")
            return "\n\n".join(formatted) if formatted else "未找到相关内容"

        def chatbot_node(state: AgentState) -> AgentState:
            system = (
                "你是知识库助手。需要查询知识库时使用 knowledge_search 工具。"
                "回答时在引用处标注【chunk_<id>】。"
            )
            # 将 langchain 消息对象转为 OpenAI dict 格式（含 tool_calls / tool_call_id）
            raw_msgs = [{"role": "system", "content": system}]
            raw_msgs.extend(_to_openai_messages(state["messages"]))
            response = used_llm.chat(raw_msgs, tools=[knowledge_search])
            ai_msg = AIMessage(content=response["content"],
                                tool_calls=response.get("tool_calls") or [])
            return {"messages": [ai_msg]}

        def tools_node(state: AgentState) -> AgentState:
            """自定义 tools 节点：执行检索并填充 retrieved_chunks（替代 prebuilt ToolNode）"""
            last_msg = state["messages"][-1]
            tool_messages = []
            hit_chunk_ids: list[str] = []

            for call in getattr(last_msg, "tool_calls", []) or []:
                if call["name"] == "knowledge_search":
                    # 执行检索时同步记录命中 ID（系统级兜底通道）
                    hits = self.last_hit_chunk_ids
                    hit_chunk_ids.extend(f"chunk_{cid}" for cid in hits)
                    result = knowledge_search.invoke(call["args"])
                    tool_messages.append(ToolMessage(
                        content=result, tool_call_id=call["id"], name=call["name"]
                    ))

            return {"messages": tool_messages, "retrieved_chunks": hit_chunk_ids}

        def should_continue(state) -> Literal["tools", "end"]:
            last = state["messages"][-1]
            return "tools" if getattr(last, "tool_calls", None) else "end"

        # 组装状态图
        workflow = StateGraph(AgentState)
        workflow.add_node("chatbot", chatbot_node)
        workflow.add_node("tools", tools_node)
        workflow.add_edge(START, "chatbot")
        workflow.add_conditional_edges("chatbot", should_continue,
                                        {"tools": "tools", "end": END})
        workflow.add_edge("tools", "chatbot")
        rag_agent = workflow.compile()

        # 执行
        messages = history or []
        messages.append({"role": "user", "content": user_question})
        final_state = rag_agent.invoke({"messages": messages, "retrieved_chunks": []})

        retrieved_set = set(final_state.get("retrieved_chunks", []))
        answer = final_state["messages"][-1].content
        return {"answer": answer, "retrieved_chunks": retrieved_set}

    def stream_query(self, user_question: str, history: list[dict] = None,
                     llm=None, thinking: bool = True,
                     should_stop=None):
        """流式 RAG 查询（生成器）。

        手动 agent 循环：检索阶段同样流式输出思考过程，最终回答逐 token 输出。
        yield (kind, text)：
          - "reasoning"  思考过程
          - "content"    正式回答内容
        命中块 ID 写入 self.last_retrieved_chunks，供调用方生成引用。

        Args:
            llm: 可选的 LLM 客户端覆盖
            thinking: 是否启用思考
            should_stop: 返回 True 则中断（用于手动停止）
        """
        used_llm = llm or self.llm
        from langchain_core.tools import tool

        @tool
        def knowledge_search(query: str) -> str:
            """搜索知识库相关内容"""
            results = self.hybrid_search(query, top_k=20)
            formatted = []
            for chunk in results:
                formatted.append(f"【chunk_{chunk.chunk_id}】{chunk.content}")
            return "\n\n".join(formatted) if formatted else "未找到相关内容"

        system = (
            "你是知识库助手。需要查询知识库时使用 knowledge_search 工具。"
            "回答时在引用处标注【chunk_<id>】。"
        )

        raw = [{"role": "system", "content": system}]
        raw.extend(_to_openai_messages(history or []))
        raw.append({"role": "user", "content": user_question})

        retrieved_set: set[str] = set()
        while True:
            if should_stop is not None and should_stop():
                return
            # 流式调用 LLM，收集工具调用增量
            tool_calls: dict[int, dict] = {}
            order: list[int] = []
            full_content = ""
            for kind, text in used_llm.stream_chat(
                    raw, tools=[knowledge_search],
                    thinking=thinking, should_stop=should_stop):
                if kind == "tool_call":
                    data = json.loads(text)
                    idx = data.get("index", 0)
                    if idx not in tool_calls:
                        tool_calls[idx] = {
                            "id": data.get("id") or "",
                            "name": data.get("name") or "",
                            "arguments": "",
                        }
                        order.append(idx)
                    if data.get("arguments"):
                        tool_calls[idx]["arguments"] += data["arguments"]
                    if data.get("name"):
                        tool_calls[idx]["name"] = data["name"]
                    if data.get("id"):
                        tool_calls[idx]["id"] = data["id"]
                elif kind == "reasoning":
                    yield ("reasoning", text)
                elif kind == "content":
                    full_content += text
                    yield ("content", text)

            if not tool_calls:
                # 最终回答结束
                self.last_retrieved_chunks = retrieved_set
                return

            # 工具调用阶段：记录命中并执行工具
            raw.append({
                "role": "assistant",
                "content": full_content or None,
                "tool_calls": [
                    {
                        "id": tool_calls[i]["id"],
                        "type": "function",
                        "function": {
                            "name": tool_calls[i]["name"],
                            "arguments": json.dumps(
                                json.loads(tool_calls[i]["arguments"] or "{}"),
                                ensure_ascii=False),
                        },
                    }
                    for i in order
                ],
            })
            for i in order:
                tc = tool_calls[i]
                name = tc["name"]
                try:
                    args = json.loads(tc["arguments"] or "{}")
                except Exception:
                    args = {}
                if name == "knowledge_search":
                    hits = self.last_hit_chunk_ids
                    retrieved_set.update(f"chunk_{cid}" for cid in hits)
                    result = knowledge_search.invoke(args)
                else:
                    result = "未知工具"
                raw.append({
                    "role": "tool",
                    "content": str(result),
                    "tool_call_id": tc["id"],
                })
