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
│   ├── chunker.py          # Chunker + TokenCounter（结构感知分块）
│   └── storage.py          # ObjectStorage（原始文件持久化，MinIO/本地文件系统统一）
├── adapters/               # 接口实现（可替换）
│   ├── paddleocr_vl.py     # VLM 方案A：PaddleOCR-VL-0.9B（CPU 可运行）
│   ├── mineru_vlm.py       # VLM 方案B：MinerU 框架（vlm/pipeline 两后端）
│   ├── minicpm_vlm.py      # VLM 方案C：MiniCPM-V 4.5（需 GPU）
│   ├── bge_embedder.py     # Embedding 方案A：BGE-M3（三模态）
│   ├── qwen3_embedder.py   # Embedding 方案B：Qwen3-Embedding（纯 dense）
│   ├── qdrant_store.py     # Qdrant 向量存储实现（混合检索 + RRF 融合）
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
│   ├── chunker.py          # 结构感知分块器 + 字符 token 计数器
│   └── rrf_fusion.py       # RRF 倒数排名融合（混合检索 dense+sparse 融合）
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
├── repositories/           # 存储仓库层（封装 SQL 与对象存储）
│   ├── postgres_repository.py  # PostgreSQL 仓库（元数据/目录/补偿队列）
│   └── object_storage.py       # MinioRepository + LocalFSAdapter（原始文件存储）
└── tests/                  # 测试
    ├── test_encoding.py            # 编码服务测试
    ├── test_trace_service.py       # 溯源核心测试
    ├── test_interface_contracts.py # 接口契约测试
    ├── test_credentials.py         # 凭据解析测试
    ├── test_chunker.py             # 分块器测试（结构感知 + overlap + 尾块合并）
    ├── test_object_storage.py      # 对象存储测试（LocalFSAdapter 全覆盖 + MinIO 契约）
    └── test_rrf_fusion.py          # RRF 融合测试（多路排名融合 + QdrantStore 契约）
```

## 关键设计

- **chunk_id 格式统一**：DB 存 BIGINT，prompt/正则/集合统一 `chunk_<snowflake_id>` 字符串
- **结构感知分块**：以 Markdown 标题/段落为原子单元，目标 200-400 tokens + 10-20% 重叠，图片/表格/公式块原样保留；标题为硬语义边界，尾块过小合并
- **图片块向量化**：用 VLM 描述文本走文本 Embedding，无独立图片 Embedder
- **混合检索+RRF 融合**：dense（cosine）+ sparse（BM25/客户端 sparse）两路检索，RRF 倒数排名融合（k=60），基于排名而非向量值，dense/sparse 分属不同向量空间不影响正确性
- **系统级溯源**：自定义 tools 节点填充 `retrieved_chunks`，溯源过滤幻觉 ID
- **失败保留+状态机恢复**：parse_status 七态，失败不删除，重启从 fail_stage 恢复
- **补偿队列**：跨系统清理入 compensation_queue，reconciler 异步执行保证最终一致
- **凭据安全**：API Key 等走系统 keyring，config.yaml 仅留占位符

## 运行

### 一键启动（推荐）

启动脚本自动完成：Python 版本校验 → 创建 .venv → 安装依赖（镜像回退）→ 启动应用。

**Windows**
```cmd
start.bat
```

**Linux / macOS**
```bash
chmod +x start.sh && ./start.sh
```

首次运行会交互询问安装模式：

| 模式 | 体积 | 说明 |
|------|------|------|
| `core` | ~100MB | 仅 UI + 轻量依赖（PySide6/openai/qdrant-client 等），1-2 分钟 |
| `full` | ~2GB | 含 paddlepaddle/torch/FlagEmbedding，支持 VLM 解析 + BGE 向量化，5-15 分钟 |

选定模式后会被记录到 `.venv/.install_mode`，后续启动直接沿用、不再询问。

### 命令行参数

```cmd
start.bat --core       强制仅装核心依赖（快速）
start.bat --full       强制装完整依赖（含 ML 包）
start.bat --reinstall  强制重装当前模式依赖
start.bat --help       显示帮助
```

```bash
./start.sh --core
./start.sh --full
./start.sh --reinstall
./start.sh --help
```

### 镜像回退

依赖安装依次尝试：清华 → 阿里云 → 官方 PyPI，任一成功即停止。requirements 文件更新或模式切换时自动重装（增量检测）。

### 外部服务（需自备）

core/full 仅安装 Python 依赖，以下服务需自行启动：

- **Qdrant**（向量库）：`config.yaml` 中 `storage.qdrant`
- **PostgreSQL**（元数据）：`config.yaml` 中 `storage.postgres`
- **MinIO**（对象存储，可选）：未配置时自动回退 `LocalFSAdapter`

### 配置凭据（首次）

API Key 等走系统 keyring，`config.yaml` 仅留 `keyring:xxx` 占位符：

```bash
python -c "from utils.credentials import set_credential; set_credential('llm_api_key', 'sk-xxx')"
```

### 手动启动（不用脚本）

```bash
python -m venv .venv
.venv\Scripts\activate          # Windows
source .venv/bin/activate       # Linux/macOS
pip install -r requirements.txt
python main.py
```

## 测试

```bash
pytest tests/ -v
```

## 待实现（标注 TODO）

- 各 VLM adapter 的真实解析逻辑
- 向量库重建 Worker 完整流程
- FileService._resume_from_stage 幂等恢复逻辑
