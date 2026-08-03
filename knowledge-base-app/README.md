# 自主知识库桌面应用

基于技术设计文档 v1.1 构建的项目骨架。架构原则：**开源为轮、自研为车**——所有开源组件通过 Protocol 接口隔离，业务逻辑仅依赖接口，核心逻辑全部自研。

## 项目结构

```
knowledge-base-app/
├── main.py                 # 应用入口
├── config.yaml             # 用户配置（凭据走 keyring）
├── requirements.txt        # 依赖清单
├── interfaces/             # 接口隔离层（Protocol 定义）
│   ├── parser.py           # DocumentParser（统一文档/图片解析，含 VLM 职责）
│   ├── embedder.py         # Embedder（文本+图片描述统一）
│   ├── vectorstore.py      # VectorStore
│   ├── llm.py              # LLMClient
│   └── chunker.py          # Chunker + TokenCounter（结构感知分块）
├── adapters/               # 接口实现（可替换）
│   ├── paddleocr_vl.py     # VLM 方案A：PaddleOCR-VL-0.9B（CPU 可运行）
│   ├── mineru_vlm.py       # VLM 方案B：MinerU 框架（vlm/pipeline 两后端）
│   ├── minicpm_vlm.py      # VLM 方案C：MiniCPM-V 4.5（需 GPU）
│   ├── bge_embedder.py     # Embedding 方案A：BGE-M3（三模态）
│   ├── qwen3_embedder.py   # Embedding 方案B：Qwen3-Embedding（纯 dense）
│   ├── qdrant_store.py     # Qdrant 向量存储实现
│   └── openai_llm.py       # OpenAI 兼容 LLM 实现
├── services/               # 业务逻辑层（自研核心）
│   ├── file_service.py     # 文件导入全流程编排
│   ├── classify_service.py # AI 分类 + 多归属
│   ├── rag_service.py      # Agentic RAG 编排
│   ├── trace_service.py    # 溯源解析（非 AI）
│   ├── lifecycle_service.py# 删除/更新/分类变更
│   ├── concurrency.py      # 全局队列+GPU 信号量+LLM 令牌桶
│   ├── compensation.py     # 补偿队列 reconciler
│   ├── encoding.py         # Snowflake + SHA-256
│   └── chunker.py          # 结构感知分块器 + 字符 token 计数器
├── workers/                # QThread 后台工作线程
│   ├── parse_worker.py     # 文档解析
│   ├── embed_worker.py     # 向量化
│   ├── search_worker.py    # 检索
│   ├── llm_worker.py       # LLM 调用
│   └── rebuild_worker.py   # 向量库重建
├── ui/                     # PySide6 桌面 UI
│   ├── main_window.py      # 主窗口（三栏布局）
│   ├── chat_panel.py       # 聊天面板
│   ├── reference_panel.py  # 引用面板
│   ├── file_tree.py        # 文件目录树
│   └── category_tree.py    # 知识分类树
├── models/                 # 数据模型
│   ├── chunk.py            # 知识块（chunk_id_str 统一字符串形式）
│   ├── document.py         # 文档
│   └── category.py         # 分类
├── utils/                  # 工具模块
│   ├── exceptions.py       # 异常体系
│   └── credentials.py      # keyring 凭据存储
└── tests/                  # 测试
    ├── test_encoding.py            # 编码服务测试
    ├── test_trace_service.py       # 溯源核心测试
    ├── test_interface_contracts.py # 接口契约测试
    ├── test_credentials.py         # 凭据解析测试
    └── test_chunker.py             # 分块器测试（结构感知 + overlap + 尾块合并）
```

## 关键设计

- **chunk_id 格式统一**：DB 存 BIGINT，prompt/正则/集合统一 `chunk_<snowflake_id>` 字符串
- **结构感知分块**：以 Markdown 标题/段落为原子单元，目标 200-400 tokens + 10-20% 重叠，图片/表格/公式块原样保留；标题为硬语义边界，尾块过小合并
- **图片块向量化**：用 VLM 描述文本走文本 Embedding，无独立图片 Embedder
- **系统级溯源**：自定义 tools 节点填充 `retrieved_chunks`，溯源过滤幻觉 ID
- **失败保留+状态机恢复**：parse_status 七态，失败不删除，重启从 fail_stage 恢复
- **补偿队列**：跨系统清理入 compensation_queue，reconciler 异步执行保证最终一致
- **凭据安全**：API Key 等走系统 keyring，config.yaml 仅留占位符

## 运行

```bash
# 安装依赖
pip install -r requirements.txt

# 配置 keyring 凭据（首次）
python -c "from utils.credentials import set_credential; set_credential('llm_api_key', 'sk-xxx')"

# 启动应用
python main.py
```

## 测试

```bash
pytest tests/ -v
```

## 待实现（标注 TODO）

- 真实 PG/MinIO/Qdrant 仓库层（pg_repo / minio_repo）
- Qdrant 混合检索 + RRF 融合
- 各 VLM adapter 的真实解析逻辑
- 向量库重建 Worker 完整流程
