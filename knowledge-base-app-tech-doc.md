# 自主知识库桌面应用 — 技术设计文档

> **文档用途**：供工程师进行软件设计与构建的技术路线参考
> **版本**：1.0
> **日期**：2026-08-03

---

## 目录

- [1 项目概述](#1-项目概述)
  - [1.1 项目目标](#11-项目目标)
  - [1.2 核心需求](#12-核心需求)
  - [1.3 设计原则](#13-设计原则)
- [2 系统架构](#2-系统架构)
  - [2.1 整体架构](#21-整体架构)
  - [2.2 技术栈总览](#22-技术栈总览)
  - [2.3 架构主权与接口隔离](#23-架构主权与接口隔离)
- [3 文档处理与多模态理解](#3-文档处理与多模态理解)
  - [3.1 文档解析管线](#31-文档解析管线)
  - [3.2 本地 VLM 选型（用户可选）](#32-本地-vlm-选型用户可选)
  - [3.3 图文混合处理流程](#33-图文混合处理流程)
  - [3.4 结构化输出与分块策略](#34-结构化输出与分块策略)
- [4 存储架构与数据模型](#4-存储架构与数据模型)
  - [4.1 三层存储架构](#41-三层存储架构)
  - [4.2 数据库表设计](#42-数据库表设计)
  - [4.3 向量存储设计](#43-向量存储设计)
- [5 AI 分析与知识分类](#5-ai-分析与知识分类)
  - [5.1 AI 分工架构](#51-ai-分工架构)
  - [5.2 自动分析流程](#52-自动分析流程)
  - [5.3 多分类管理](#53-多分类管理)
- [6 RAG 检索与智能问答](#6-rag-检索与智能问答)
  - [6.1 Embedding 模型选型（用户可选）](#61-embedding-模型选型用户可选)
  - [6.2 混合检索方案](#62-混合检索方案)
  - [6.3 Agentic RAG 编排](#63-agentic-rag-编排)
- [7 唯一编码与系统级溯源](#7-唯一编码与系统级溯源)
  - [7.1 知识块双重编码方案](#71-知识块双重编码方案)
  - [7.2 系统级溯源四步机制](#72-系统级溯源四步机制)
  - [7.3 溯源实现代码](#73-溯源实现代码)
- [8 桌面应用架构](#8-桌面应用架构)
  - [8.1 PySide6 框架选型](#81-pyside6-框架选型)
  - [8.2 接口隔离层设计](#82-接口隔离层设计)
  - [8.3 项目结构](#83-项目结构)
  - [8.4 QThread 异步模式](#84-qthread-异步模式)
- [9 部署方案](#9-部署方案)
  - [9.1 全本地免费技术栈](#91-全本地免费技术栈)
  - [9.2 硬件配置要求](#92-硬件配置要求)
  - [9.3 部署清单](#93-部署清单)
- [10 开发计划](#10-开发计划)
  - [10.1 分阶段实施路线](#101-分阶段实施路线)
  - [10.2 技术风险与对策](#102-技术风险与对策)
- [11 配置系统设计](#11-配置系统设计)
  - [11.1 配置文件结构](#111-配置文件结构)
  - [11.2 模型选择与动态加载](#112-模型选择与动态加载)
  - [11.3 配置热更新机制](#113-配置热更新机制)
- [12 关键流程时序设计](#12-关键流程时序设计)
  - [12.1 文档写入链路时序](#121-文档写入链路时序)
  - [12.2 智能问答检索链路时序](#122-智能问答检索链路时序)
- [13 错误处理与容错策略](#13-错误处理与容错策略)
  - [13.1 分层错误处理模型](#131-分层错误处理模型)
  - [13.2 重试与降级策略](#132-重试与降级策略)
  - [13.3 数据一致性保障](#133-数据一致性保障)
- [14 测试策略与质量保障](#14-测试策略与质量保障)
  - [14.1 测试分层架构](#141-测试分层架构)
  - [14.2 关键模块测试要点](#142-关键模块测试要点)
  - [14.3 持续集成流水线](#143-持续集成流水线)

---

## 1 项目概述

### 1.1 项目目标

构建一个自主可控的知识库桌面应用，具备文档/图片接收、AI 自动分析分类、智能问答（带引用溯源）、多分类管理能力。系统以"开源为轮、自研为车"为核心原则，开源组件仅作为 Python 库通过 `pip install` 集成，业务逻辑、数据模型、UI 交互、溯源机制全部自研，不依赖 Dify/RAGFlow/FastGPT 等开源平台。

### 1.2 核心需求

| 编号 | 需求 | 说明 |
|------|------|------|
| ① | 接收各种文档和图片 | 包括图文混合内容，需解析版面、提取文字、理解图片 |
| ② | 存储接收内容 | 原始文件持久化存储，解析结果结构化入库 |
| ③ | AI 自动分析+分类+建立目录 | 接入文字 LLM API，自动分析内容并分类存储，建立两个目录：原始文件目录（文件→知识块映射）和知识分类目录 |
| ④ | 智能问答带引用溯源 | 用户提问后由 AI 决定调用知识库内容，输出结果并告知参考了哪些文章/图片 |
| ⑤ | 多分类存储 | 一个知识可属于多个分类，在每一个相关分类中都进行存储 |
| ⑥ | 系统级溯源（非 AI） | AI 分析存储的每个知识要有独特编码（系统自动完成），输出后由系统（非 AI）根据编码自动溯源 |

### 1.3 设计原则

- **开源为轮、自研为车**：所有开源组件通过 Protocol/ABC 接口隔离包裹，业务逻辑仅依赖接口而非具体实现，任何组件可替换且业务代码不感知底层变化。
- **桌面应用（非浏览器）**：使用 PySide6 原生控件，单进程运行，QThread 管理后台 AI 处理，PyMuPDF 原生渲染 PDF。
- **仅 LLM API 对外**：除文字 LLM API 外，全部组件本地部署、免费开源。多模态理解由本地 VLM 完成，避免多模态 API 高额费用。
- **用户可选关键模型**：Embedding 模型和本地 VLM 均支持用户在配置中自由切换，业务代码零修改。

---

## 2 系统架构

### 2.1 整体架构

系统采用 **PySide6 单进程 + QThread 异步** 设计。桌面 UI 与 Python AI 处理同进程运行，通过 Qt 的 Signal/Slot 机制实现线程安全的异步通信。

AI 能力分为两层：
- **本地 VLM 层**（用户可选）：PaddleOCR-VL-0.9B / MinerU 2.5 VLM / MiniCPM-V 4.5，负责多模态理解（图片描述、文档版面解析、OCR）。
- **文字 LLM API 层**：对接用户自有 API（OpenAI 兼容协议），负责纯文本推理（分类、摘要、关键词抽取、问答生成）。

两条核心链路：
- **写入链路**：文档导入 → 本地 VLM 解析 → 分块 → 系统生成编码 → 向量化 → AI 分类 → 存储入库
- **检索链路**：用户提问 → Agentic RAG 决策 → 混合检索 → AI 生成答案 → 系统溯源解析 → 返回带引用结果

### 2.2 技术栈总览

| 层级 | 推荐方案 | 引入方式 | 用户可选 |
|------|----------|----------|----------|
| 桌面前端 | PySide6（Qt for Python） | pip install PySide6 | — |
| PDF 渲染 | PyMuPDF（fitz） | pip install PyMuPDF | — |
| Markdown 渲染 | python-markdown + QTextEdit | pip install markdown | — |
| 本地 VLM（多模态） | 方案A: PaddleOCR-VL-0.9B / 方案B: MinerU 2.5 VLM / 方案C: MiniCPM-V 4.5 | pip install paddleocr / mineru / lmdeploy | 是 |
| OCR 引擎 | PaddleOCR PP-OCRv6 | pip install paddleocr | — |
| 原始文件存储 | MinIO（S3 兼容） | pip install minio | — |
| 元数据/目录 | PostgreSQL | pip install psycopg2 | — |
| 向量数据库 | Qdrant（单二进制） | pip install qdrant-client | — |
| 稀疏检索/BM25 | Qdrant 原生稀疏向量 | 同上 | — |
| Embedding 模型 | 方案A: BGE-M3（三模式）/ 方案B: Qwen3-Embedding（纯 dense） | pip install FlagEmbedding / transformers | 是 |
| Agent 编排 | LangGraph（StateGraph） | pip install langgraph | — |
| 文字 LLM API | OpenAI 兼容 SDK（仅纯文本） | pip install openai | — |
| 块唯一编码 | Snowflake + SHA-256（自研） | 自研代码 | — |
| 多分类管理 | 标签 + 元数据过滤（自研） | 自研代码 | — |
| 系统溯源 | 正则解析块ID + DB 映射（自研） | 自研代码 | — |
| 打包分发 | PyInstaller / Nuitka | pip install pyinstaller | — |

### 2.3 架构主权与接口隔离

所有开源组件被自定义的 Python `Protocol`（或 `ABC`）接口包裹，业务逻辑层仅依赖接口，不 import 任何第三方库。第三方库仅在实现类（adapter）中引入，通过依赖注入传入业务层。

这意味着：
- MinerU 可替换为 Docling
- Qdrant 可替换为 Milvus
- BGE-M3 可替换为 Qwen3-Embedding
- PaddleOCR-VL 可替换为 MiniCPM-V

以上替换用户在配置中指定即可，业务代码零修改。

---

## 3 文档处理与多模态理解

### 3.1 文档解析管线

文档解析采用"专用工具优先"策略：专用解析工具（MinerU/PaddleOCR）在保真度上优于通用 VLM，通用大模型易产生幻觉，输出可能含源文档不存在的虚假信息。

解析管线流程：
1. 文档导入后，系统调用本地 VLM 进行版面分析和内容提取
2. 文字区通过 OCR 提取文本，图片区由 VLM 输出结构化描述
3. 表格转为 HTML/Markdown，公式转为 LaTeX
4. 双格式输出：JSON（无损持久化）+ Markdown（可读中间表示）

### 3.2 本地 VLM 选型（用户可选）

用户不通过 API 接入多模态大模型，多模态理解全部由本地 VLM 完成。系统通过 `VisionLanguageModel` 接口层支持以下三种方案，用户在配置中选择：

| 方案 | 模型 | 参数量 | 显存/内存 | CPU 可行 | 核心能力 | 协议 |
|------|------|--------|-----------|----------|----------|------|
| A（无 GPU 首选） | PaddleOCR-VL-0.9B | 0.9B | 极低 | CPU 可运行 | OmniDocBench #1, 109语言, 表格/公式/图表/手写 | Apache 2.0 |
| B（版面精度首选） | MinerU 2.5 VLM | 1.2B | ≥8GB GPU | Pipeline 后端可 CPU | 版面检测 97.5% mAP, 粗到精两阶段 | AGPL-3.0 |
| C（通用图像理解） | MiniCPM-V 4.5 (AWQ) | 8B | 5GB 显存 | GGUF Q4 6GB 内存 | OCRBench 顶尖, 低幻觉, 通用图像理解 | Apache 2.0 |

**选型建议**：
- 无 GPU 或低配环境 → 方案A（PaddleOCR-VL-0.9B，CPU 可运行，OmniDocBench v1.5 全球第一）
- 有 GPU 且追求文档版面精度 → 方案B（MinerU 2.5 VLM，版面 97.5% mAP）
- 有 GPU 且需通用图像理解 → 方案C（MiniCPM-V 4.5，OCRBench 顶尖）

### 3.3 图文混合处理流程

```
图文混合文档
    │
    ▼
本地 VLM（用户可选）: 版面分析
    │
    ├── 文字区 → VLM OCR 提取（方案A 可 CPU 运行）
    ├── 图片区 → VLM 图片理解 → 输出结构化描述文本
    ├── 表格区 → 结构化表格（HTML/Markdown）
    └── 公式区 → LaTeX 转换
    │
    ▼
双格式输出: JSON 无损 + Markdown 可读
    │
    ▼
结构感知分块（200-400 tokens, 10-20% 重叠）
    │
    ▼
每个块携带元数据: doc_id, page, bbox, chunk_type
    │
    ▼
文字 LLM API: 分类/摘要/问答（仅纯文本, 低成本）
```

### 3.4 结构化输出与分块策略

解析阶段同时输出两种格式：
- **JSON（无损持久化）**：保留所有元数据（bbox、页码、来源、层级），存入数据库用于溯源。
- **Markdown（可读中间表示）**：保留标题层级、表格、列表，便于 LLM 理解，是分块的基础。

分块采用**结构感知（structure-aware）分块**，以 Markdown 标题/段落/表格为原子单元：
- 目标块大小：200-400 tokens
- 重叠比例：10-20%
- 每个 chunk 携带元数据：`doc_id`、文件路径、页码、`bbox`、`chunk_type`（text/image/table/formula）

---

## 4 存储架构与数据模型

### 4.1 三层存储架构

| 层 | 技术 | 存储内容 |
|----|------|----------|
| 原始文件层 | MinIO（S3 兼容） | 原始 PDF/Word/图片，按 bucket+路径组织 |
| 元数据索引层 | PostgreSQL | 文件目录、块索引、分类关系（即"两个目录"） |
| 向量索引层 | Qdrant | 向量嵌入 + 元数据过滤，支持语义检索与分类过滤 |

### 4.2 数据库表设计

#### 原始文件目录（document_index 表）

```sql
-- 文件级正向索引：文件元数据。块列表通过 chunk_index.doc_id 反向查询获取，
-- 不再冗余存储 chunk_ids JSONB（避免双索引不一致）。
CREATE TABLE document_index (
    doc_id          BIGINT PRIMARY KEY,      -- Snowflake 业务ID
    file_name       VARCHAR(500) NOT NULL,    -- 原始文件名
    file_path       VARCHAR(1000) NOT NULL,   -- 对象存储路径
    file_type       VARCHAR(20) NOT NULL,     -- pdf/docx/png...
    content_hash    VARCHAR(64) NOT NULL,     -- SHA-256 文件指纹
    page_count      INT,
    upload_time     TIMESTAMPTZ DEFAULT now(),
    parse_status    VARCHAR(20) DEFAULT 'pending',  -- 见 13.3 状态机
    fail_stage      VARCHAR(20),              -- 失败时记录阶段: parse/embed/classify/store
    fail_reason     TEXT                      -- 失败原因，供重启恢复诊断
);

-- 正向查询（文件→块列表）走此索引
CREATE INDEX idx_chunk_index_doc_id ON chunk_index(doc_id);
```

#### 知识块索引（chunk_index 表）

```sql
-- 块级反向索引：知识块 → 来源文件 + 精确位置
-- chunk_id 在 DB 中为 BIGINT；在 prompt/正则/集合中统一渲染为字符串 "chunk_<snowflake_id>"
-- （详见 7.1 编码格式约定），DB 查询时用 CAST 或字符串拼接处理。
CREATE TABLE chunk_index (
    chunk_id        BIGINT PRIMARY KEY,       -- Snowflake 业务ID（系统生成）
    content_hash    VARCHAR(64) NOT NULL,     -- SHA-256 内容指纹（完整性校验+去重）
    doc_id          BIGINT NOT NULL,          -- 来源文件ID（反向索引）
    doc_name        VARCHAR(500) NOT NULL,    -- 来源文件名（冗余存储便于溯源）
    page_number     INT,                       -- 所在页码
    char_start      INT,                       -- 字符起始偏移
    char_end        INT,                       -- 字符结束偏移
    bbox            JSONB,                     -- 页面坐标框 [x,y,w,h]
    chunk_type      VARCHAR(20),              -- text/table/image/formula
    content         TEXT NOT NULL,            -- 块文本内容（图片块为 VLM 描述文本）
    vector_id       VARCHAR(100),             -- 向量库中的对应ID
    created_at      TIMESTAMPTZ DEFAULT now(),
    FOREIGN KEY (doc_id) REFERENCES document_index(doc_id)
);

-- 去重键：同一文件内相同内容去重，跨文件不去重（保留独立来源）
CREATE UNIQUE INDEX idx_chunk_dedup ON chunk_index(content_hash, doc_id);
```

> **说明**：原 `categories` JSONB 字段已删除。多分类关系统一以 `chunk_category` 关联表为单一数据源，Qdrant payload 在写入时从关联表读取，避免双写不一致（详见 5.3）。

#### 知识库分类目录（category 表 + chunk_category 关联表）

```sql
-- 分类目录：支持层级结构
CREATE TABLE category (
    category_id     BIGINT PRIMARY KEY,
    name            VARCHAR(200) NOT NULL,
    parent_id       BIGINT,                   -- 父分类（层级结构）
    description     TEXT,
    created_at      TIMESTAMPTZ DEFAULT now()
);

-- 多对多关联：一个知识块可属于多个分类
CREATE TABLE chunk_category (
    chunk_id        BIGINT NOT NULL,
    category_id     BIGINT NOT NULL,
    assigned_by     VARCHAR(20) DEFAULT 'ai', -- ai/system
    confidence      FLOAT,                    -- AI分类置信度
    PRIMARY KEY (chunk_id, category_id)
);
```

**关键设计**：`chunk_index.doc_id` 提供反向索引（块→文件），并建有 `idx_chunk_index_doc_id` 索引，正向查询（文件→块列表）通过 `SELECT chunk_id FROM chunk_index WHERE doc_id=?` 高效完成。两个方向的查询都走单一数据源，避免冗余字段不一致风险。

### 4.3 向量存储设计

Qdrant 作为向量索引层，Collection 设计如下：

| 数据来源 | Embedding 模型 | 向量类型 | Qdrant Collection |
|----------|---------------|----------|-------------------|
| 文本块 + 图片块（VLM 描述文本） | BGE-M3（用户可选 Qwen3-Embedding） | dense(1024) + sparse + colbert | `text_chunks` |

**统一单 Collection 设计**：图片块不独立向量化，而是用本地 VLM 输出的描述文本走文本 Embedding 入 `text_chunks` collection，通过 payload 的 `chunk_type` 字段区分 `text`/`image`/`table`/`formula`。这样消除了独立的图片 Embedder 依赖（原 `Qwen3-VL-Embedding-2B` 已移除），避免了图文向量空间不一致问题，且图片块同样可被语义检索命中并在溯源时映射回原始图片位置。

**稀疏向量来源约定**（避免向量空间混淆）：
- **BGE-M3 模式**：sparse 向量由客户端 `BGEM3FlagModel` 计算 `lexical_weights` 后上传，与 dense 同源，向量空间一致。
- **Qwen3-Embedding 模式**：模型仅输出 dense，sparse 降级为 Qdrant 服务端 `qdrant/bm25` 模型转换。此时 dense 与 sparse 分属不同向量空间，但 Qdrant 会分别建立索引，RRF 融合基于排名而非向量值，不影响检索正确性。

若选 Qwen3-Embedding（仅 dense），系统自动降级为"dense + Qdrant 原生 BM25"双路检索，仍保留混合检索能力。

---

## 5 AI 分析与知识分类

### 5.1 AI 分工架构

| 层级 | 职责 | 模型 | 部署方式 | 费用 |
|------|------|------|----------|------|
| 本地 VLM 层 | 图片理解→文本描述、文档版面解析、OCR、表格/公式识别 | 用户可选：PaddleOCR-VL-0.9B / MinerU 2.5 VLM / MiniCPM-V 4.5 | 本地部署（方案A 可 CPU 运行） | 免费 |
| 文字 LLM API 层 | 知识摘要、关键词/实体抽取、自动分类判定、问答生成 | GPT-4o / Claude / DeepSeek 等文字模型 | 用户自有 API | 按 token 计费（低成本） |

成本对比：多模态 API 方案（如 GPT-4o Vision）每张图片约 0.0025-0.01 美元，1000 张图文混合文档约 2.5-10 美元。本地 VLM 方案完全零费用，文字 LLM API 仅处理 VLM 输出的纯文本，token 消耗降低 60-80%。

### 5.2 自动分析流程

分析流程的关键是**本地 VLM 输出结构化文本，文字 LLM API 据此进行推理，系统代码控制写入数据库**：

1. 本地 VLM 解析文档/图片，输出 Markdown/JSON 结构化文本
2. 系统代码分块并生成唯一编码（Snowflake + SHA-256）
3. 将纯文本块送入文字 LLM API，AI 输出 JSON 格式的分析结果（摘要、分类列表、置信度）
4. 系统代码解析后写入 `chunk_index` 和 `chunk_category` 表

编码生成和分类关联完全由系统控制，不依赖 AI。

### 5.3 多分类管理

需求⑤要求"一个知识可属于多个分类"。实现方案为**标签 + 元数据过滤**，块物理存一份，通过 `chunk_category` 多对多关联表实现逻辑多归属：

- `chunk_category` 关联表为**单一数据源**，存储完整分类关系，含 AI 分配置信度
- Qdrant payload 的 `categories` 字段在写入/更新时从 `chunk_category` 表读取并同步，不作为独立数据源
- 检索时可按分类过滤：Qdrant 的 `Filter` + `FieldCondition` 支持按 payload 的 `categories` 字段筛选
- 分类变更时（新增/删除关联）由系统代码同步更新 Qdrant payload，保证两端一致

---

## 6 RAG 检索与智能问答

### 6.1 Embedding 模型选型（用户可选）

系统通过 `Embedder` 接口层支持多种模型实现，用户在配置中自由切换：

| 方案 | 模型 | 参数 | 维度 | 检索模式 | 中文能力 | 显存需求 | 协议 |
|------|------|------|------|----------|----------|----------|------|
| A（三模态融合） | BGE-M3 | 568M | 1024 | dense+sparse+colbert | 优秀 | INT4 ~0.5GB | MIT |
| B（纯 dense 优化） | Qwen3-Embedding-0.6B | 0.6B | 1024 | 仅 dense | 更优（CMTEB 66.33） | INT4 ~0.5GB | Apache 2.0 |
| B（纯 dense 优化） | Qwen3-Embedding-4B | 4B | 2560 | 仅 dense | 最优（CMTEB 72.26） | INT4 ~3GB | Apache 2.0 |

**选型建议**：
- 含大量专有名词、代码、编号的技术文档库 → 方案A（BGE-M3，三路融合，关键词匹配更准）
- 以自然语言为主的通用知识库 → 方案B（Qwen3-Embedding，CMTEB 中文榜首，语义理解更强）

若选方案B（仅 dense），系统自动降级为"dense + Qdrant 原生 BM25"双路检索，仍保留混合检索能力。

### 6.2 混合检索方案

单一向量检索无法覆盖精确关键词匹配（如专有名词、代码），采用**混合检索**三级管道：

```
用户查询
    │
    ▼
Embedding 编码（dense + sparse + colbert）
    │
    ├── Dense 检索 → Qdrant cosine top 20
    ├── Sparse 检索 → Qdrant BM25 top 20
    │
    ▼
RRF 倒数排名融合 → 候选集 top 50
    │
    ▼
ColBERT 多向量重排 → 精确交互 top 5
    │
    ▼
检索结果（携带 chunk_id）
```

Qdrant 原生支持稀疏向量（BM25），通过配置 `sparse_vectors` 并设置 `modifier: "idf"` 启用，内置 `qdrant/bm25` 模型支持文本到稀疏向量的服务端转换。同一引擎内完成稠密+稀疏混合检索 + RRF 融合，无需 Elasticsearch。

### 6.3 Agentic RAG 编排

Agent 编排层使用 LangGraph 的 `StateGraph`，将检索器封装为 Tool，LLM 动态决策是否检索。LangGraph 仅作脚手架，检索逻辑全部自研。

**关键技术决策**：不使用 LangGraph prebuilt `ToolNode`（它只把 tool 结果包成 `ToolMessage` 放回 `messages`，不会更新自定义状态字段）。改为**自定义 tools 节点**，在调用检索后显式写入 `state["retrieved_chunks"]`，确保系统级溯源兜底通道可用。

```python
# services/rag_service.py — 自研 Agentic RAG
from langgraph.graph import StateGraph, START, END
from typing import TypedDict, Annotated, Literal
from langchain_core.tools import tool
from langchain_core.messages import ToolMessage

# retrieved_chunks 用 add 防止多轮检索覆盖
def _append_list(left: list, right: list) -> list:
    return (left or []) + (right or [])

class AgentState(TypedDict):
    messages: list
    retrieved_chunks: Annotated[list[str], _append_list]  # 系统追踪命中 chunk_id（字符串形式）

@tool
def knowledge_search(query: str) -> str:
    """搜索知识库相关内容"""
    results = rag_service.hybrid_search(query, top_k=20)
    formatted = []
    for chunk in results:
        # chunk_id 统一渲染为 "chunk_<snowflake_id>" 字符串（见 7.1）
        formatted.append(f"【chunk_{chunk.chunk_id}】{chunk.content}")
    return "\n\n".join(formatted)

def chatbot_node(state: AgentState) -> AgentState:
    system = (
        "你是知识库助手。需要查询知识库时使用 knowledge_search 工具。"
        "回答时在引用处标注【chunk_<id>】。"
    )
    messages = [{"role": "system", "content": system}, *state["messages"]]
    response = llm_client.chat(messages, tools=[knowledge_search])
    return {"messages": [response]}

def tools_node(state: AgentState) -> AgentState:
    """自定义 tools 节点：执行检索并填充 retrieved_chunks（替代 prebuilt ToolNode）"""
    last_msg = state["messages"][-1]
    tool_messages = []
    hit_chunk_ids: list[str] = []

    for call in getattr(last_msg, "tool_calls", []) or []:
        if call["name"] == "knowledge_search":
            # 在执行检索时同步记录命中 ID（系统级兜底通道）
            hits = rag_service.last_hit_chunk_ids  # knowledge_search 内部缓存的命中 ID
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
```

> **架构决策**：统一采用 LangGraph 作为 Agent 编排脚手架，不再保留"自研有限状态机替代"的备选方案，避免实现分歧。如未来需剥离 LangGraph 依赖，`tools_node` 的状态填充逻辑可直接迁移到自研 FSM。

---

## 7 唯一编码与系统级溯源

### 7.1 知识块双重编码方案

这是整个系统最核心的需求。其本质是建立一条"系统生成编码 → AI 引用编码 → 系统解析编码 → 映射回原文"的确定性链路，其中编码生成和溯源映射两个环节完全由系统代码完成，不依赖 AI。

采用**双重编码**：Snowflake 作业务主键 + SHA-256 内容指纹作去重与完整性校验。

| 编码 | 生成原理 | 有序性 | 去重能力 | 分布式友好 | 溯源可靠性 |
|------|----------|--------|----------|------------|------------|
| Snowflake | 时间戳+机器ID+序列号 | 趋势递增 | 无 | 需分配 workerId | 高（性能最优） |
| SHA-256 指纹 | 内容加密哈希 | 无 | 天然去重 | 是 | 极高（内容即身份） |

- Snowflake 提供时间排序、数据库索引友好（64 位长整型），是每个块的**独特编码**（即使两块内容相同，Snowflake ID 也不同）
- SHA-256 提供"内容即身份"的**内容指纹**——相同内容必生成相同哈希，用于去重（按 `content_hash` 唯一约束）与完整性校验（重算哈希验证块未被篡改）。注意：SHA-256 不是"独特编码"，相同内容共享同一指纹
- 两者均在分块时由系统代码生成，完全不依赖 AI

**Snowflake workerId 配置**（单机桌面场景）：桌面应用为单机单进程，无需分布式 workerId 协调。在 `config.yaml` 中配置固定 `worker_id`（默认 1），序列号位足够单机使用。若未来支持多实例，可通过本地文件锁分配 workerId。

**编码格式约定（贯穿全系统）**：

| 场景 | chunk_id 表示 | 示例 |
|------|--------------|------|
| 数据库存储 | BIGINT | `1751234567890` |
| Prompt 注入 / AI 输出标注 | 字符串 `chunk_<snowflake_id>` | `chunk_1751234567890` |
| 正则提取 | `r'【(chunk_\d+)】'` | 匹配 `【chunk_1751234567890】` |
| `retrieved_chunks` 集合 | 字符串集合 `set[str]` | `{"chunk_1751234567890", ...}` |
| DB 查询映射 | 字符串去前缀转 BIGINT | `int(cid.removeprefix("chunk_"))` |

此约定确保 AI 输出标注、正则解析、集合校验、DB 查询四个环节格式一致，不会因类型不匹配导致溯源失效。

### 7.2 系统级溯源四步机制

需求⑥的核心是"告知参考了哪些文章或图片应该由系统完成，而不是由 AI 搜索"。实现路径分为四步，其中第 1、2、4 步由系统完成，仅第 3 步依赖 AI：

| 步骤 | 执行者 | 操作 |
|------|--------|------|
| ① 检索阶段 | 系统 | 向量+BM25 混合检索，返回 Top-K 块（每个块携带 chunk_id + 元数据） |
| ② 上下文组装 | 系统 | 将块 ID 与块内容同时注入提示词，指令模型引用时标注 `【chunk_<id>】` |
| ③ AI 生成 | AI | AI 输出带引用标记的答案（例：某知识来自 `【chunk_1751234567890】`） |
| ④ 系统后处理 | 系统（非 AI） | 正则提取答案中的块 ID → **过滤幻觉 ID**（仅保留 `retrieved_chunks` 集合内的）→ 查询 `chunk_index` 表获取来源文件名/页码/坐标 → 返回结构化引用列表 |

> **顺序说明**：第④步先过滤后查询 DB，减少无效 DB 调用；与 7.3 实现代码顺序一致。

**提示词模板示例**：

```
请严格根据以下上下文回答问题。每个片段有唯一ID，格式为【chunk_<id>】。

<上下文>
【chunk_1751234567890】知识库采用 Agentic RAG 架构...
【chunk_1751234567891】Qdrant 向量数据库支持元数据过滤...
【chunk_1751234567892】PaddleOCR 中文识别准确率达 96%...
</上下文>

要求：每个事实后用【chunk_<id>】注明来源片段ID。
若信息不足以回答，请说明而非编造。
```

### 7.3 溯源实现代码

```python
# services/trace_service.py — 系统后处理溯源（完全不依赖AI）
import re

def trace_references(answer: str, retrieved_chunk_ids: set) -> list:
    """从AI输出中解析块ID，映射回原始文件"""
    # 1. 正则提取答案中的所有块ID
    cited_ids = set(re.findall(r'【(chunk_\d+)】', answer))

    # 2. 过滤幻觉ID——仅采纳检索结果集内的ID
    valid_ids = cited_ids & retrieved_chunk_ids

    # 3. 查询数据库，映射回原始文件与位置
    references = []
    for chunk_id in valid_ids:
        chunk = db.query(
            "SELECT chunk_id, doc_name, page_number, "
            "bbox, content, chunk_type "
            "FROM chunk_index WHERE chunk_id = %s",
            chunk_id
        )
        references.append({
            "chunk_id": chunk.chunk_id,
            "source_file": chunk.doc_name,      # 参考了哪篇文章
            "page": chunk.page_number,           # 第几页
            "position": chunk.bbox,              # 页面坐标
            "type": chunk.chunk_type,            # text/image/table
            "excerpt": chunk.content[:200]       # 内容摘要
        })

    return references  # → 前端渲染为可点击引用脚注
```

**双重保障**：即使 AI 未在答案中标注引用，系统的检索记录机制会在每次调用 `knowledge_search` 工具时，将实际检索命中的块 ID 列表写入 Agent 状态（`retrieved_chunks`），提供不依赖模型标注的独立溯源通道。系统还会校验 AI 输出中解析出的 ID 是否在检索结果集内，过滤 AI 幻觉 ID。

---

## 8 桌面应用架构

### 8.1 PySide6 框架选型

选择 PySide6（Qt for Python）作为前端框架的理由：
- **原生桌面控件**（非浏览器），用户要求的"正常软件界面"
- **LGPL v3 许可**，可闭源商用
- **Python 同进程调用 AI 库**，无 IPC 开销
- **QThread 管理后台 AI 处理**，Signal/Slot 线程安全
- **PyMuPDF 原生渲染 PDF**，无需 QtWebEngine（剥离后节省 ~120MB）
- PyInstaller/Nuitka 打包为独立安装包（.exe/.dmg）

### 8.2 接口隔离层设计

所有开源组件通过 Protocol 接口隔离，业务逻辑仅依赖接口：

```python
# interfaces.py — 接口隔离层（自研）
from typing import Protocol, List, Dict
from dataclasses import dataclass

@dataclass
class ParsedDocument:
    chunks: list["Chunk"]
    images: list["ImageBlock"]
    metadata: dict

@dataclass
class EmbeddingResult:
    """向量化结果 — 支持三模态（dense/sparse/colbert）"""
    dense: list[float]           # 稠密向量（必有）
    sparse: dict[str, float] = None    # 稀疏向量（BGE-M3 有，Qwen3 无）
    colbert: list[list[float]] = None  # 多向量（仅 BGE-M3 ColBERT 模式）

class DocumentParser(Protocol):
    """文档解析接口 — MinerU/Docling 均可实现"""
    def parse(self, file_path: str) -> ParsedDocument: ...

class Embedder(Protocol):
    """向量化接口 — 用户可选 BGE-M3 或 Qwen3-Embedding 实现"""
    def encode(self, texts: list[str]) -> list[EmbeddingResult]: ...
    def encode_query(self, query: str) -> EmbeddingResult: ...
    @property
    def supports_sparse(self) -> bool: ...   # BGE-M3=True, Qwen3=False
    @property
    def supports_colbert(self) -> bool: ...  # BGE-M3=True, Qwen3=False

class VectorStore(Protocol):
    """向量存储接口 — Qdrant/Milvus 均可实现"""
    def upsert(self, chunks: list["Chunk"]) -> None: ...
    def search(self, query_vec: list[float], top_k: int) -> list: ...

class LLMClient(Protocol):
    """文字 LLM API 接口 — 仅纯文本，对接用户自有 API"""
    def chat(self, messages: list[dict], tools: list = None) -> dict: ...
    def stream_chat(self, messages: list[dict]) -> str: ...

class VisionLanguageModel(Protocol):
    """本地 VLM 接口 — 多模态理解（图片→文本），本地部署零 API 费用。
    用户可选方案A/B/C，在配置中指定。"""
    def understand_image(self, image_path: str, prompt: str) -> str: ...
    def parse_document(self, file_path: str) -> ParsedDocument: ...
    @property
    def requires_gpu(self) -> bool: ...  # 方案A=False, 方案B/C=True
```

**VLM 实现示例（用户在配置中选择其一）**：

```python
# adapters/paddleocr_vl.py — 方案A：PaddleOCR-VL-0.9B（CPU 可运行·无 GPU 首选）
class PaddleOCRVLModel:
    def understand_image(self, image_path: str, prompt: str) -> str:
        from paddleocr import PaddleOCRVL
        model = PaddleOCRVL()
        result = model.predict(image_path)
        return result.markdown

    @property
    def requires_gpu(self) -> bool: return False

# adapters/mineru_vlm.py — 方案B：MinerU 2.5 VLM 后端（版面精度首选·需 GPU）
class MinerUVLMModel:
    def __init__(self):
        from mineru.cli.common import do_parse, read_fn
        self.backend = "vlm"  # 或 "pipeline" 降级为 CPU

    def parse_document(self, file_path: str) -> ParsedDocument:
        pdf_bytes = read_fn(file_path)
        do_parse(output_dir="./tmp", pdf_bytes_list=[pdf_bytes], ...)
        ...

    @property
    def requires_gpu(self) -> bool: return True

# adapters/minicpm_vlm.py — 方案C：MiniCPM-V 4.5（通用图像理解·需 GPU）
class MiniCPMVModel:
    def understand_image(self, image_path: str, prompt: str) -> str:
        from lmdeploy import pipeline
        from lmdeploy.vl import load_image
        pipe = pipeline('openbmb/MiniCPM-V-4_5')
        image = load_image(image_path)
        response = pipe((prompt, image))
        return response.text

    @property
    def requires_gpu(self) -> bool: return True
```

**Embedding 实现示例（用户在配置中选择其一）**：

```python
# adapters/bge_embedder.py — 方案A：BGE-M3（三模态：dense+sparse+colbert）
class BgeM3Embedder:
    def __init__(self):
        from FlagEmbedding import BGEM3FlagModel
        self.model = BGEM3FlagModel('BAAI/bge-m3', use_fp16=True)

    def encode(self, texts: list[str]) -> list[EmbeddingResult]:
        results = self.model.encode(texts, return_dense=True,
                                     return_sparse=True, return_colbert_vecs=True)
        return [EmbeddingResult(
            dense=r['dense_vec'], sparse=r['lexical_weights'],
            colbert=r['colbert_vecs']
        ) for r in results]

    def encode_query(self, query: str) -> EmbeddingResult:
        return self.encode([query])[0]

    @property
    def supports_sparse(self) -> bool: return True
    @property
    def supports_colbert(self) -> bool: return True

# adapters/qwen3_embedder.py — 方案B：Qwen3-Embedding（纯 dense，CMTEB 中文榜首）
class Qwen3Embedder:
    def __init__(self, model_name: str = 'Qwen/Qwen3-Embedding-0.6B'):
        from transformers import AutoModel, AutoTokenizer
        self.tokenizer = AutoTokenizer.from_pretrained(model_name)
        self.model = AutoModel.from_pretrained(model_name, trust_remote_code=True)

    def encode(self, texts: list[str]) -> list[EmbeddingResult]:
        import torch
        inputs = self.tokenizer(texts, padding=True, truncation=True,
                                 max_length=8192, return_tensors='pt')
        with torch.no_grad():
            outputs = self.model(**inputs)
        dense_vecs = self._last_token_pool(outputs.last_hidden_state, inputs['attention_mask'])
        dense_vecs = torch.nn.functional.normalize(dense_vecs, p=2, dim=1)
        return [EmbeddingResult(dense=v.tolist()) for v in dense_vecs]

    def encode_query(self, query: str) -> EmbeddingResult:
        return self.encode([query])[0]

    @property
    def supports_sparse(self) -> bool: return False
    @property
    def supports_colbert(self) -> bool: return False

    def _last_token_pool(self, last_hidden_state, attention_mask):
        import torch
        left_padding = (attention_mask[:, -1].sum() == attention_mask.shape[0])
        if left_padding:
            return last_hidden_state[:, -1]
        sequence_lengths = attention_mask.sum(dim=1) - 1
        return last_hidden_state[torch.arange(last_hidden_state.size(0)), sequence_lengths]
```

### 8.3 项目结构

```
knowledge-base-app/
├── main.py                    # PySide6 入口
├── interfaces/                # 接口隔离层（自研）
│   ├── parser.py              # DocumentParser Protocol
│   ├── embedder.py            # Embedder Protocol
│   ├── vectorstore.py         # VectorStore Protocol
│   ├── llm.py                 # LLMClient Protocol（文字 LLM API）
│   └── vlm.py                 # VisionLanguageModel Protocol（本地 VLM）
├── adapters/                  # 接口实现（可替换）
│   ├── mineru_parser.py       # MinerU DocumentParser 实现
│   ├── paddle_ocr.py          # PaddleOCR 实现
│   ├── paddleocr_vl.py        # VLM 方案A：PaddleOCR-VL-0.9B（CPU 可运行）
│   ├── mineru_vlm.py          # VLM 方案B：MinerU 2.5 VLM 后端（需 GPU）
│   ├── minicpm_vlm.py         # VLM 方案C：MiniCPM-V 4.5（需 GPU）
│   ├── bge_embedder.py        # Embedding 方案A：BGE-M3（三模态）
│   ├── qwen3_embedder.py      # Embedding 方案B：Qwen3-Embedding（纯 dense）
│   ├── qdrant_store.py        # Qdrant 实现
│   └── openai_llm.py          # OpenAI 兼容文字 LLM 实现
├── services/                  # 业务逻辑层（自研核心）
│   ├── file_service.py        # 文件管理 + 导入
│   ├── classify_service.py    # AI 分类 + 多归属
│   ├── rag_service.py         # Agentic RAG 编排
│   ├── trace_service.py       # 溯源解析（非AI）
│   └── encoding.py            # Snowflake + SHA-256
├── ui/                        # PySide6 桌面 UI
│   ├── main_window.py         # 主窗口（三栏布局）
│   ├── chat_panel.py          # 聊天面板
│   ├── reference_panel.py     # 引用面板
│   ├── file_tree.py           # 文件目录树
│   └── category_tree.py       # 知识分类树
├── workers/                   # QThread 后台工作线程
│   ├── parse_worker.py        # 文档解析 Worker
│   ├── embed_worker.py        # 向量化 Worker
│   ├── search_worker.py       # 检索 Worker
│   └── llm_worker.py          # AI 调用 Worker
├── models/                    # 数据模型
│   ├── chunk.py               # 知识块模型
│   ├── document.py            # 文档模型
│   └── category.py            # 分类模型
└── config.py                  # 配置（API Key、模型选择、路径等）
```

### 8.4 QThread 异步模式

AI 密集任务（文档解析、向量化、LLM 调用）在 QThread 中执行，通过 Signal/Slot 线程安全地回传结果到 UI 线程：

```python
# workers/parse_worker.py — QThread 后台解析
from PySide6.QtCore import QThread, Signal

class ParseWorker(QThread):
    progress = Signal(int, str)       # (百分比, 消息)
    finished = Signal(list)           # 解析结果
    error = Signal(str)               # 错误信息

    def __init__(self, parser, file_paths):
        super().__init__()
        self.parser = parser           # DocumentParser 接口
        self.file_paths = file_paths

    def run(self):
        results = []
        for i, path in enumerate(self.file_paths):
            try:
                self.progress.emit(
                    int(i / len(self.file_paths) * 100),
                    f"正在解析: {path}"
                )
                doc = self.parser.parse(path)  # 调用接口，不感知底层实现
                results.append(doc)
            except Exception as e:
                self.error.emit(str(e))
                return
        self.finished.emit(results)

# ui/main_window.py — UI 线程接收
class MainWindow(QMainWindow):
    def on_import_files(self, paths):
        self.worker = ParseWorker(self.parser, paths)
        self.worker.progress.connect(self.update_progress)
        self.worker.finished.connect(self.on_parse_done)
        self.worker.error.connect(self.show_error)
        self.worker.start()  # 不阻塞 UI

    def on_parse_done(self, results):
        for doc in results:
            self.file_tree.add_document(doc)
        self.statusBar().showMessage(f"已导入 {len(results)} 个文档")
```

---

## 9 部署方案

### 9.1 全本地免费技术栈

除文字 LLM API 外，全部组件开源免费、可本地部署。不使用 Dify/FastGPT/RAGFlow 等平台。

| 组件 | 技术选型 | 协议 | 本地部署 | 硬件需求 |
|------|----------|------|----------|----------|
| 桌面应用 | PySide6 | LGPL v3 | 是 | 普通 PC |
| PDF 渲染 | PyMuPDF | AGPL-3.0 | 是 | 纯 CPU |
| 本地 VLM（用户可选） | PaddleOCR-VL-0.9B / MinerU 2.5 VLM / MiniCPM-V 4.5 | Apache 2.0 / AGPL-3.0 | 是 | 方案A CPU 可运行；方案B 需 GPU ≥8GB；方案C AWQ 5GB 显存 |
| OCR 引擎 | PaddleOCR PP-OCRv6 | Apache 2.0 | 是 | 纯 CPU 可行 |
| 原始文件存储 | MinIO | AGPLv3 | 是 | 普通服务器 |
| 元数据/目录 | PostgreSQL | PostgreSQL License | 是 | 普通服务器 |
| 向量库 + 稀疏检索 | Qdrant | Apache 2.0 | 是 | 单二进制，普通服务器 |
| Embedding 模型（用户可选） | BGE-M3 / Qwen3-Embedding | MIT / Apache 2.0 | 是 | BGE-M3 CPU 可行(ONNX INT8~0.3GB)；Qwen3-0.6B 同等轻量 |
| Agent 编排 | LangGraph | MIT | 是 | 纯 Python 库 |
| LLM API | 用户自有 API（OpenAI 兼容） | — | 云端（唯一外部依赖） | — |
| 打包分发 | PyInstaller / Nuitka | GPL/商业 | 是 | 生成 .exe/.dmg |

### 9.2 硬件配置要求

| 配置档位 | CPU | GPU | 内存 | 磁盘 | 能力说明 |
|----------|-----|-----|------|------|----------|
| 最低可用 | 4核 | 无 | 8GB | 50GB | VLM 方案A: PaddleOCR-VL-0.9B (CPU) + MinerU Pipeline(CPU) + Embedding(CPU: BGE-M3 ONNX 或 Qwen3-0.6B) + Qdrant |
| 推荐配置 | 8核 | RTX 3060/4060 8GB | 16GB | 200GB SSD | VLM 方案B/C: MinerU VLM 或 MiniCPM-V 4.5 (GPU) + Embedding(GPU: BGE-M3 或 Qwen3-4B) |
| 生产配置 | 16核 | RTX 4090 24GB | 32GB | 500GB NVMe | 支持大规模文档批量解析+多模态理解+推理+检索 |

### 9.3 部署清单

```bash
# ===== 自研桌面应用部署（不使用任何平台）=====

# 1. 基础设施（Docker 仅用于存储组件，非应用平台）
docker run -d --name minio -p 9000:9000 -p 9001:9001 \
  -e MINIO_ROOT_USER=admin -e MINIO_ROOT_PASSWORD=yourpass \
  minio/minio server /data --console-address ":9001"

docker run -d --name postgres -p 5432:5432 \
  -e POSTGRES_DB=knowledge_base \
  -e POSTGRES_USER=admin \
  -e POSTGRES_PASSWORD=yourpass \
  postgres:16

docker run -d --name qdrant -p 6333:6333 \
  -v $(pwd)/qdrant_data:/qdrant/storage \
  qdrant/qdrant

# 2. Python 环境与自研应用依赖
python -m venv .venv && source .venv/bin/activate
pip install PySide6          # 桌面 UI（原生非浏览器）
pip install PyMuPDF          # PDF 原生渲染
pip install paddlepaddle paddleocr  # VLM 方案A：PaddleOCR-VL-0.9B（CPU可运行）+ OCR 引擎
pip install mineru           # VLM 方案B：MinerU 2.5 VLM 后端（需GPU；Pipeline后端可CPU）
# 或 pip install lmdeploy     # VLM 方案C：MiniCPM-V 4.5 部署（AWQ 量化仅 5GB 显存）
pip install FlagEmbedding    # Embedding 方案A：BGE-M3 直接加载（三模式，无需独立服务）
# 或 pip install transformers  # Embedding 方案B：Qwen3-Embedding 直接加载（纯 dense，CMTEB 中文榜首）
pip install qdrant-client    # 向量数据库客户端
pip install minio            # 对象存储客户端
pip install psycopg2-binary  # PostgreSQL 客户端
pip install langgraph        # Agent 编排脚手架
pip install openai           # 文字 LLM API（OpenAI 兼容协议·仅纯文本）

# 3. 配置文字 LLM API（唯一外部依赖·仅纯文本·低成本）
# 在桌面应用设置界面填入：
#   - API Base URL（如 https://api.openai.com/v1）
#   - API Key
#   - 模型名称（如 gpt-4o / claude-3.5-sonnet / deepseek-chat）

# 4. 配置用户可选模型（在 config.py 或设置界面中指定）
#   - VLM 方案：A (PaddleOCR-VL) / B (MinerU VLM) / C (MiniCPM-V)
#   - Embedding 方案：A (BGE-M3) / B (Qwen3-Embedding)

# 5. 初始化数据库（执行建表 SQL）
psql -h localhost -U admin -d knowledge_base -f schema.sql

# 6. 启动桌面应用
python main.py
```

---

## 10 开发计划

### 10.1 分阶段实施路线

| 阶段 | 目标 | 核心任务 | 预估周期 |
|------|------|----------|----------|
| 一：桌面骨架 + 文档管线 | PySide6 应用可运行，文档可导入解析 | 三栏 UI 骨架、Protocol 接口层、VLM（用户可选）+PaddleOCR 解析、MinIO+PG 存储、Snowflake 编码 | 3-4 周 |
| 二：检索问答 + 交互 | 可提问，AI 回答带引用溯源 | Qdrant+Embedding（用户可选 BGE-M3/Qwen3）向量化、自研混合检索、四步溯源、聊天面板、引用面板 | 3-4 周 |
| 三：Agentic + 文档预览 | AI 自主决策检索，PDF 原生预览 | LangGraph Agent、多分类管理、PyMuPDF 预览+高亮、幻觉ID过滤 | 2-3 周 |
| 四：打包 + 进阶 | 可分发安装包，多模态增强 | PyInstaller/Nuitka 打包、Qwen3-VL 多模态、增量更新 | 2-3 周 |

### 10.2 技术风险与对策

| 风险 | 影响 | 对策 |
|------|------|------|
| MinerU VLM 后端需 GPU | 无 GPU 环境无法使用方案B | 默认方案A (PaddleOCR-VL-0.9B CPU 可运行)，MinerU 降级为 Pipeline 后端 |
| 打包体积过大 | 安装包超 200MB | 剥离 QtWebEngine（节省 ~120MB）+ UPX 压缩 + Nuitka 编译 |
| AI 幻觉引用 ID | 答案中出现不存在的块 ID | 系统后处理校验：仅采纳检索结果集内的 ID，过滤幻觉 ID |
| LLM API 调用延迟 | 用户等待时间长 | QThread 异步流式渲染、Token 流式输出、UI 实时更新 |
| Embedding 模型切换 | 不同模型向量维度不同 | Protocol 接口抽象 + Qdrant Collection 动态创建，配置指定维度 |
| VLM 模型切换 | 不同 VLM 接口差异 | Protocol 接口统一 `understand_image` / `parse_document` 方法签名 |

---

## 11 配置系统设计

### 11.1 配置文件结构

配置系统是用户选择 VLM 方案、Embedding 模型、LLM API 的入口。采用 YAML + Python dataclass 双层设计：YAML 文件供用户编辑，dataclass 供代码消费，二者通过 `load_config()` 函数桥接。

```yaml
# config.yaml — 用户可编辑配置文件
llm:
  api_base: "https://api.openai.com/v1"
  api_key: "sk-xxxxx"              # 用户自有 API Key
  model: "gpt-4o"                  # 文字 LLM 模型名称
  temperature: 0.3
  max_tokens: 4096
  timeout: 60                      # 秒

vlm:
  # 用户可选：A / B / C
  provider: "A"                    # A=PaddleOCR-VL, B=MinerU VLM, C=MiniCPM-V
  # 方案A 专属配置
  paddleocr_vl:
    model_dir: null                # null=自动下载，或指定本地路径
    lang: "ch"                     # OCR 语言
  # 方案B 专属配置
  mineru_vlm:
    backend: "vlm"                 # vlm(需GPU) / pipeline(CPU可降级)
    device: "cuda"
  # 方案C 专属配置
  minicpm_v:
    model_path: "openbmb/MiniCPM-V-4_5"
    quantization: "awq"            # awq(5GB显存) / gguf_q4(6GB内存CPU)

embedding:
  # 用户可选：A / B
  provider: "A"                    # A=BGE-M3, B=Qwen3-Embedding
  # 方案A 专属配置
  bge_m3:
    model_name: "BAAI/bge-m3"
    use_fp16: true
  # 方案B 专属配置
  qwen3:
    model_name: "Qwen/Qwen3-Embedding-0.6B"  # 或 4B / 8B
    max_length: 8192

storage:
  minio:
    endpoint: "localhost:9000"
    access_key: "admin"
    secret_key: "yourpass"
    bucket: "knowledge-base"
  postgres:
    host: "localhost"
    port: 5432
    database: "knowledge_base"
    user: "admin"
    password: "yourpass"
  qdrant:
    host: "localhost"
    port: 6333
    collection_text: "text_chunks"
    collection_image: "image_chunks"

chunking:
  target_tokens: 300               # 目标块大小
  overlap_ratio: 0.15              # 重叠比例
  min_chunk_tokens: 50             # 最小块大小

retrieval:
  top_k_dense: 20                  # 稠密检索召回数
  top_k_sparse: 20                 # 稀疏检索召回数
  rrf_k: 60                        # RRF 融合参数
  final_top_k: 5                   # 最终返回数

ui:
  window_width: 1400
  window_height: 900
  theme: "dark"                    # dark / light
```

### 11.2 模型选择与动态加载

配置加载后，系统通过工厂模式根据 `provider` 字段动态实例化对应的 adapter，业务层始终操作接口，不感知具体实现：

```python
# config.py — 配置加载与工厂注册
from dataclasses import dataclass, field
from typing import Any
import yaml

@dataclass
class AppConfig:
    llm: dict
    vlm: dict
    embedding: dict
    storage: dict
    chunking: dict
    retrieval: dict
    ui: dict

def load_config(path: str = "config.yaml") -> AppConfig:
    with open(path, 'r', encoding='utf-8') as f:
        data = yaml.safe_load(f)
    return AppConfig(**data)

# factories.py — 依赖注入工厂
class ComponentFactory:
    """根据配置动态创建组件实例，业务层仅接收接口"""

    def __init__(self, config: AppConfig):
        self.config = config

    def create_vlm(self) -> "VisionLanguageModel":
        provider = self.config.vlm["provider"]
        if provider == "A":
            from adapters.paddleocr_vl import PaddleOCRVLModel
            return PaddleOCRVLModel(**self.config.vlm["paddleocr_vl"])
        elif provider == "B":
            from adapters.mineru_vlm import MinerUVLMModel
            return MinerUVLMModel(**self.config.vlm["mineru_vlm"])
        elif provider == "C":
            from adapters.minicpm_vlm import MiniCPMVModel
            return MiniCPMVModel(**self.config.vlm["minicpm_v"])
        raise ValueError(f"未知 VLM 方案: {provider}")

    def create_embedder(self) -> "Embedder":
        provider = self.config.embedding["provider"]
        if provider == "A":
            from adapters.bge_embedder import BgeM3Embedder
            return BgeM3Embedder(**self.config.embedding["bge_m3"])
        elif provider == "B":
            from adapters.qwen3_embedder import Qwen3Embedder
            return Qwen3Embedder(**self.config.embedding["qwen3"])
        raise ValueError(f"未知 Embedding 方案: {provider}")

    def create_llm(self) -> "LLMClient":
        from adapters.openai_llm import OpenAILLMClient
        return OpenAILLMClient(**self.config.llm)
```

业务层注入方式：

```python
# main.py — 应用入口
config = load_config("config.yaml")
factory = ComponentFactory(config)

# 业务层仅依赖接口，不 import 任何 adapter
vlm = factory.create_vlm()           # → VisionLanguageModel
embedder = factory.create_embedder()  # → Embedder
llm = factory.create_llm()            # → LLMClient

# 传入业务服务
file_service = FileService(vlm=vlm, embedder=embedder, llm=llm, config=config)
rag_service = RagService(embedder=embedder, llm=llm, config=config)

# 启动 UI
app = QApplication(sys.argv)
window = MainWindow(file_service=file_service, rag_service=rag_service)
window.show()
sys.exit(app.exec())
```

### 11.3 配置热更新机制

用户在桌面应用设置界面修改模型方案后，系统通过 Signal 通知各服务重建组件实例，无需重启应用：

```python
# services/config_manager.py — 配置热更新
from PySide6.QtCore import QObject, Signal

class ConfigManager(QObject):
    config_changed = Signal(str, object)  # (字段名, 新值)

    def __init__(self, config: AppConfig, factory: ComponentFactory):
        super().__init__()
        self.config = config
        self.factory = factory

    def update_vlm_provider(self, provider: str):
        """用户在设置界面切换 VLM 方案"""
        self.config.vlm["provider"] = provider
        new_vlm = self.factory.create_vlm()
        self.config_changed.emit("vlm", new_vlm)

    def update_embedding_provider(self, provider: str):
        """用户在设置界面切换 Embedding 模型"""
        self.config.embedding["provider"] = provider
        new_embedder = self.factory.create_embedder()
        self.config_changed.emit("embedding", new_embedder)
        # 注意：切换 Embedding 后需重建 Qdrant Collection（维度可能变化）

    def update_llm_config(self, **kwargs):
        """用户修改 LLM API 配置"""
        self.config.llm.update(kwargs)
        new_llm = self.factory.create_llm()
        self.config_changed.emit("llm", new_llm)
```

**Embedding 切换注意事项**：BGE-M3 输出 1024 维 + 稀疏 + ColBERT，Qwen3-Embedding-0.6B 输出 1024 维（纯 dense），Qwen3-4B 输出 2560 维。切换模型后向量维度不同，需重建 Qdrant Collection 并重新向量化全部已有知识块。系统在切换时弹出确认对话框，提示用户此操作的影响。

---

## 12 关键流程时序设计

### 12.1 文档写入链路时序

文档从导入到入库的完整时序，涉及 UI 线程、QThread 工作线程、本地 VLM、LLM API、三个存储系统：

```
用户          UI线程         ParseWorker     VLM          LLM API       MinIO      PostgreSQL    Qdrant
 │              │               │             │              │            │            │           │
 │─ 拖入文件 ──→│               │             │              │            │            │           │
 │              │─ 创建Worker ─→│             │              │            │            │           │
 │              │               │─ 解析文档 ─→│              │            │            │           │
 │              │               │             │─ 版面分析    │            │            │           │
 │              │               │             │─ OCR提取     │            │            │           │
 │              │               │             │─ 图片理解    │            │            │           │
 │              │               │← ParsedDoc ─│              │            │            │           │
 │              │               │                          │            │            │           │
 │              │               │─ 分块+Snowflake编码       │            │            │           │
 │              │               │  (系统生成chunk_id)       │            │            │           │
 │              │               │                          │            │            │           │
 │              │               │─ 上传原始文件 ──────────────────────────→│            │           │
 │              │               │← 上传成功 ──────────────────────────────│            │           │
 │              │               │                          │            │            │           │
 │              │               │─ 写document_index ───────────────────────────────→│           │
 │              │               │← 写入成功 ────────────────────────────────────────│           │
 │              │               │                          │            │            │           │
 │              │               │─ 向量编码(Embedder)      │            │            │           │
 │              │               │                          │            │            │           │
 │              │               │─ 分类请求(纯文本) ──────→│            │            │           │
 │              │               │             LLM API ────→│            │            │           │
 │              │               │← 分类JSON ←──────────────│            │            │           │
 │              │               │                          │            │            │           │
 │              │               │─ 写chunk_index ──────────────────────────────────→│           │
 │              │               │─ 写chunk_category ────────────────────────────────→│          │
 │              │               │                          │            │            │           │
 │              │               │─ upsert向量+元数据 ──────────────────────────────────────────→│
 │              │               │← upsert成功 ──────────────────────────────────────────────────│
 │              │               │                          │            │            │           │
 │              │← finished ────│             │              │            │            │           │
 │← 更新文件树 ─│               │             │              │            │            │           │
```

关键设计点：
- VLM 解析和 LLM 分类分属不同阶段，VLM 输出纯文本后才调用 LLM API，避免多模态 API 费用
- `chunk_id` 在分块阶段由 Snowflake 生成，贯穿整个链路，入库、向量化、分类关联均使用同一 ID
- 原始文件先上传 MinIO 获得 `file_path`，再写入 PostgreSQL，保证外键引用有效
- 向量 upsert 最后执行，此时 chunk_id 和元数据已就绪，向量库可建立完整索引

### 12.2 智能问答检索链路时序

用户提问到获得带引用答案的完整时序：

```
用户          UI线程         LLMWorker      LLM API       Embedder     Qdrant        PostgreSQL
 │              │               │             │              │            │            │
 │─ 输入问题 ──→│               │             │              │            │           │
 │              │─ 启动Agent ──→│             │              │            │           │
 │              │               │             │              │            │           │
 │              │               │  ┌─ Agent 循环 (LangGraph StateGraph) ──────────────────┐
 │              │               │  │                                                        │
 │              │               │  │ chatbot_node:                                         │
 │              │               │  │─ 组装system prompt ─→│                                │
 │              │               │  │─ LLM决策是否检索 ──→│                                │
 │              │               │  │  (返回tool_calls)   │                                │
 │              │               │  │                      │                                │
 │              │               │  │ tools_node:                                           │
 │              │               │  │─ knowledge_search(query)                              │
 │              │               │  │  ┌─ 混合检索 ─────────────────────────────────────┐  │
 │              │               │  │  │ Embedder编码查询 ─→│                            │  │
 │              │               │  │  │ Dense检索 ──────────────────────────→│        │  │
 │              │               │  │  │ Sparse(BM25)检索 ───────────────────→│        │  │
 │              │               │  │  │ RRF融合 → ColBERT重排               │        │  │
 │              │               │  │  │← Top-K chunks (携带chunk_id) ─────────────────┘  │
 │              │               │  │  └─────────────────────────────────────────────────┘  │
 │              │               │  │                      │                                │
 │              │               │  │  系统记录: retrieved_chunks.add(命中chunk_ids)         │
 │              │               │  │                      │                                │
 │              │               │  │ chatbot_node (第2轮):                                  │
 │              │               │  │─ 注入检索结果为context                                │
 │              │               │  │─ LLM生成带【chunk_id】引用的答案 ─→│                  │
 │              │               │  │  (无tool_calls → 结束循环)                             │
 │              │               │  └────────────────────────────────────────────────────────┘
 │              │               │                          │                │           │
 │              │               │  ┌─ 系统后处理溯源 (非AI) ────────────────────────────┐ │
 │              │               │  │ 正则提取答案中的【chunk_id】                         │ │
 │              │               │  │ 过滤幻觉ID (仅保留retrieved_chunks中的)             │ │
 │              │               │  │ 查询chunk_index映射回文件名/页码/坐标 ─────────────→│ │
 │              │               │  │← 结构化引用列表 ←──────────────────────────────────│ │
 │              │               │  └──────────────────────────────────────────────────────┘ │
 │              │               │             │              │            │            │
 │              │← 答案+引用 ───│             │              │            │           │
 │← 渲染答案   ─│               │             │              │            │           │
 │  +引用脚注   │               │             │              │            │           │
```

关键设计点：
- Agent 循环中 `retrieved_chunks` 在系统侧记录所有命中的 chunk_id，不依赖 AI 标注
- 系统后处理溯源是独立于 Agent 的后置步骤，正则解析 + 数据库映射 + 幻觉过滤三重保障
- 引用脚注渲染为可点击链接，点击后跳转到原始文件的对应页面和坐标位置

---

## 13 错误处理与容错策略

### 13.1 分层错误处理模型

错误处理分三层：Adapter 层捕获第三方库异常并转换为统一异常类型，Service 层处理业务逻辑错误并决定重试/降级，UI 层负责用户友好的错误展示。

```python
# exceptions.py — 统一异常体系
class KnowledgeBaseError(Exception):
    """所有自定义异常的基类"""
    pass

class ParseError(KnowledgeBaseError):
    """文档解析失败"""
    pass

class EmbedError(KnowledgeBaseError):
    """向量化失败"""
    pass

class RetrievalError(KnowledgeBaseError):
    """检索失败"""
    pass

class LLMError(KnowledgeBaseError):
    """LLM API 调用失败"""
    pass

class StorageError(KnowledgeBaseError):
    """存储操作失败"""
    pass

class TraceError(KnowledgeBaseError):
    """溯源解析失败"""
    pass
```

### 13.2 重试与降级策略

| 错误场景 | 策略 | 实现方式 |
|----------|------|----------|
| LLM API 超时/429 | 指数退避重试 3 次 | `tenacity` 库 `@retry(wait=wait_exponential, stop=stop_after_attempt(3))` |
| LLM API 返回格式异常 | 重新请求并附加格式约束提示词 | 在 system prompt 追加 "请严格返回 JSON 格式" |
| VLM 解析 OOM | 降级到 Pipeline 后端（方案B）或跳过图片（方案A/C） | 捕获 `torch.cuda.OutOfMemoryError`，切换 backend |
| Embedding 编码失败 | 跳过当前块，标记为 `embed_failed`，后续补偿 | `chunk_index.parse_status = 'embed_failed'` |
| Qdrant 连接失败 | 本地缓存待写入队列，恢复后批量补写 | 内存队列 + 定时 flush |
| PostgreSQL 写入冲突 | 按 content_hash 去重，跳过已存在记录 | `INSERT ... ON CONFLICT (content_hash) DO NOTHING` |
| 正则未匹配到任何 chunk_id | 回退到 `retrieved_chunks` 记录作为引用来源 | 优先使用 AI 标注，回退到系统记录 |

重试装饰器示例：

```python
# utils/retry.py
from tenacity import retry, stop_after_attempt, wait_exponential, retry_if_exception_type

def with_llm_retry(func):
    """LLM API 调用重试装饰器"""
    return retry(
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=1, min=2, max=10),
        retry=retry_if_exception_type((TimeoutError, ConnectionError)),
        reraise=True
    )(func)

# adapters/openai_llm.py
class OpenAILLMClient:
    @with_llm_retry
    def chat(self, messages, tools=None):
        try:
            response = self.client.chat.completions.create(
                model=self.model, messages=messages, tools=tools
            )
            return response
        except Exception as e:
            raise LLMError(f"LLM API 调用失败: {e}") from e
```

### 13.3 数据一致性保障

写入链路涉及三个存储系统（MinIO + PostgreSQL + Qdrant），需保障跨系统数据一致性：

```python
# services/file_service.py — 写入链路事务编排
class FileService:
    def import_document(self, file_path: str) -> str:
        """文档导入全流程，带补偿回滚"""
        doc_id = None
        chunk_ids = []

        try:
            # 1. 上传原始文件到 MinIO
            file_path_stored = self.minio.upload(file_path)

            # 2. 写入 PostgreSQL document_index
            doc_id = self.snowflake.next_id()
            self.pg.insert_document(doc_id, file_path, file_path_stored, ...)

            # 3. VLM 解析 + 分块 + 编码
            parsed = self.vlm.parse_document(file_path)
            chunks = self.chunker.split(parsed)
            for chunk in chunks:
                chunk.chunk_id = self.snowflake.next_id()
                chunk_ids.append(chunk.chunk_id)

            # 4. 向量化
            embeddings = self.embedder.encode([c.content for c in chunks])

            # 5. LLM 分类
            classifications = self.classify_with_llm(chunks)

            # 6. 写入 PostgreSQL chunk_index + chunk_category
            self.pg.insert_chunks(chunks, classifications)

            # 7. 写入 Qdrant（最后一步，失败时可补偿）
            self.qdrant.upsert(chunks, embeddings)

            # 8. 更新 document_index.parse_status = 'completed'
            self.pg.update_parse_status(doc_id, 'completed')

            return doc_id

        except Exception as e:
            # 补偿回滚：按逆序清理
            logger.error(f"文档导入失败: {e}, 开始回滚")
            if chunk_ids:
                self.qdrant.delete(chunk_ids)          # 删向量
            if doc_id:
                self.pg.delete_chunks_by_doc(doc_id)   # 删块索引
                self.pg.delete_document(doc_id)         # 删文件记录
                self.minio.delete(file_path_stored)    # 删原始文件
            raise StorageError(f"文档导入失败已回滚: {e}") from e
```

一致性设计原则：
- **原始文件优先上传**：MinIO 上传成功后才写 PostgreSQL，保证 `file_path` 引用有效
- **Qdrant 最后写入**：向量数据依赖 chunk_id 和元数据，最后写入可保证引用完整
- **补偿逆序回滚**：失败时按 Qdrant → PostgreSQL → MinIO 逆序删除已写入数据
- **状态标记追踪**：`document_index.parse_status` 字段标记 `pending`/`completed`/`failed`，应用启动时扫描 `pending` 状态记录并尝试恢复或清理

---

## 14 测试策略与质量保障

### 14.1 测试分层架构

| 层级 | 范围 | 工具 | 覆盖目标 |
|------|------|------|----------|
| 单元测试 | 接口实现、工具函数、数据模型 | pytest | 核心逻辑 ≥ 80% 行覆盖 |
| 接口测试 | Protocol 契约一致性 | pytest + Mock | 所有 adapter 通过接口测试 |
| 集成测试 | 跨模块数据流（解析→存储→检索） | pytest + testcontainers | 写入→检索→溯源全链路 |
| UI 测试 | PySide6 交互流程 | pytest-qt | 关键交互路径 |
| 端到端测试 | 完整用户场景 | 手动 + 自动化脚本 | 文档导入到问答全流程 |

### 14.2 关键模块测试要点

**溯源模块测试**（最高优先级，需求⑥的核心保障）：

```python
# tests/test_trace_service.py
class TestTraceService:

    def test_normal_citation(self):
        """正常引用：AI 标注的 chunk_id 在检索结果集内"""
        answer = "知识库采用 Agentic RAG【chunk_101】，Qdrant 支持元数据过滤【chunk_102】"
        retrieved = {"chunk_101", "chunk_102", "chunk_103"}
        refs = trace_references(answer, retrieved)
        assert len(refs) == 2
        assert {r["chunk_id"] for r in refs} == {"chunk_101", "chunk_102"}

    def test_hallucination_filtering(self):
        """幻觉过滤：AI 编造的 chunk_id 不在检索结果集内，应被过滤"""
        answer = "某知识来自【chunk_999】"  # chunk_999 不在检索结果中
        retrieved = {"chunk_101", "chunk_102"}
        refs = trace_references(answer, retrieved)
        assert len(refs) == 0  # 幻觉 ID 被过滤

    def test_no_citation_fallback(self):
        """回退机制：AI 未标注任何引用时，使用 retrieved_chunks 作为引用来源"""
        answer = "知识库采用 Agentic RAG 架构"  # 无引用标记
        retrieved = {"chunk_101", "chunk_102"}
        refs = trace_references_fallback(answer, retrieved)
        assert len(refs) == 2  # 回退到系统记录

    def test_mixed_citation(self):
        """混合场景：部分引用有效，部分为幻觉"""
        answer = "来自【chunk_101】和【chunk_999】"
        retrieved = {"chunk_101", "chunk_102"}
        refs = trace_references(answer, retrieved)
        assert len(refs) == 1
        assert refs[0]["chunk_id"] == "chunk_101"
```

**接口契约测试**（验证所有 adapter 符合 Protocol 定义）：

```python
# tests/test_interface_contracts.py
class TestEmbedderContract:
    """所有 Embedder 实现必须通过此测试"""

    @pytest.fixture(params=[
        BgeM3Embedder(),
        Qwen3Embedder(model_name="Qwen/Qwen3-Embedding-0.6B"),
    ])
    def embedder(self, request):
        return request.param

    def test_encode_returns_embedding_result(self, embedder):
        results = embedder.encode(["测试文本"])
        assert len(results) == 1
        assert isinstance(results[0], EmbeddingResult)
        assert len(results[0].dense) > 0  # dense 向量必有

    def test_encode_query_returns_single_result(self, embedder):
        result = embedder.encode_query("查询文本")
        assert isinstance(result, EmbeddingResult)
        assert len(result.dense) > 0

    def test_supports_sparse_consistency(self, embedder):
        """supports_sparse 属性必须与实际输出一致"""
        result = embedder.encode(["测试"])
        if embedder.supports_sparse:
            assert result.sparse is not None
        else:
            assert result.sparse is None
```

**集成测试**（使用 testcontainers 启动真实存储）：

```python
# tests/test_integration.py
@pytest.fixture(scope="module")
def storage_stack():
    """启动 PostgreSQL + Qdrant + MinIO 容器"""
    with postgres_container() as pg, qdrant_container() as qd, minio_container() as mn:
        yield StorageStack(pg, qd, mn)

class TestWriteRetrieveCycle:
    """写入→检索→溯源全链路集成测试"""

    def test_document_roundtrip(self, storage_stack):
        # 1. 导入文档
        doc_id = file_service.import_document("test_data/sample.pdf")
        assert doc_id is not None

        # 2. 验证 PostgreSQL 记录
        doc = storage_stack.pg.get_document(doc_id)
        assert doc.parse_status == 'completed'
        assert len(doc.chunk_ids) > 0

        # 3. 验证 Qdrant 向量
        for chunk_id in doc.chunk_ids:
            assert storage_stack.qdrant.exists(chunk_id)

        # 4. 检索验证
        results = rag_service.hybrid_search("样本内容", top_k=5)
        assert len(results) > 0
        assert any(r.chunk_id in doc.chunk_ids for r in results)

        # 5. 溯源验证
        answer = f"参考内容【{results[0].chunk_id}】"
        refs = trace_references(answer, {r.chunk_id for r in results})
        assert len(refs) == 1
        assert refs[0]["source_file"] == "sample.pdf"
```

### 14.3 持续集成流水线

```yaml
# .github/workflows/ci.yml — GitHub Actions CI 流水线
name: CI
on: [push, pull_request]

jobs:
  lint:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - run: pip install ruff mypy
      - run: ruff check .
      - run: mypy interfaces/ services/ --strict

  unit-test:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - run: pip install -e ".[test]"
      - run: pytest tests/unit/ --cov=services --cov=interfaces --cov-report=xml
      - run: pytest tests/test_interface_contracts.py

  integration-test:
    runs-on: ubuntu-latest
    services:
      postgres:
        image: postgres:16
        env: { POSTGRES_PASSWORD: test }
        ports: ['5432:5432']
      qdrant:
        image: qdrant/qdrant
        ports: ['6333:6333']
      minio:
        image: minio/minio
        ports: ['9000:9000']
        env: { MINIO_ROOT_USER: test, MINIO_ROOT_PASSWORD: testpass }
    steps:
      - uses: actions/checkout@v4
      - run: pip install -e ".[test]"
      - run: pytest tests/test_integration.py --tb=short

  ui-test:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - run: pip install -e ".[test]" pytest-qt
      - run: xvfb-run pytest tests/ui/ --tb=short
```

CI 流水线在每次提交时自动执行：代码规范检查（ruff + mypy）、单元测试（含覆盖率报告）、接口契约测试、集成测试（真实存储容器）、UI 测试。溯源模块测试作为独立 stage 单独报告结果，确保需求⑥的核心保障不被回归破坏。

---

> **文档说明**：本文档基于全面技术调研编制，所有技术选型均经过验证。开源组件以 Python 库形式集成，通过 Protocol/ABC 接口隔离，核心业务逻辑全部自研。Embedding 模型（BGE-M3 / Qwen3-Embedding）和本地 VLM（PaddleOCR-VL-0.9B / MinerU 2.5 VLM / MiniCPM-V 4.5）均支持用户在配置中自由切换，业务代码零修改。系统不依赖任何开源平台（Dify/RAGFlow/FastGPT），保持完全的架构主权。全文覆盖项目概述、系统架构、文档处理、存储设计、AI 分析、RAG 检索、编码溯源、桌面架构、部署方案、开发计划、配置系统、时序设计、错误处理、测试策略共 14 个章节，可直接作为工程师软件设计与构建的技术路线参考。
