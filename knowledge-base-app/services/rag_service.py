"""Agentic RAG 编排服务

关键技术决策：不使用 LangGraph prebuilt ToolNode（它只把 tool 结果包成 ToolMessage
放回 messages，不会更新自定义状态字段）。改为自定义 tools 节点，在调用检索后显式
写入 state["retrieved_chunks"]，确保系统级溯源兜底通道可用。
"""
from __future__ import annotations

import logging
from typing import Optional

from interfaces.embedder import Embedder
from interfaces.llm import LLMClient
from interfaces.vectorstore import VectorStore
from models.chunk import Chunk

logger = logging.getLogger(__name__)


class RagService:
    """Agentic RAG 编排 + 混合检索"""

    def __init__(self, embedder: Embedder, llm: LLMClient,
                 qdrant_store: VectorStore, config: dict):
        self.embedder = embedder
        self.llm = llm
        self.qdrant = qdrant_store
        self.config = config
        self.last_hit_chunk_ids: list[int] = []  # 缓存最近一次检索命中 ID

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

    def query(self, user_question: str, history: list[dict] = None) -> dict:
        """Agentic RAG 查询，返回答案 + 命中块 ID 集合（字符串形式）

        Returns:
            {"answer": str, "retrieved_chunks": set[str]}
        """
        from langgraph.graph import StateGraph, START, END
        from typing import TypedDict, Annotated, Literal
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
            messages = [{"role": "system", "content": system}, *state["messages"]]
            response = self.llm.chat(messages, tools=[knowledge_search])
            ai_msg = AIMessage(content=response["content"],
                                tool_calls=response.get("tool_calls"))
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
