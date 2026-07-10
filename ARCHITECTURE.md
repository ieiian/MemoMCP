# MemoMCP 架构设计文档 (Phase 1)

> 定位：基于 MCP 的通用长期记忆基础设施，为 AI Coding 工具提供统一的记忆能力。

---

## 1. 设计原则

| 原则 | 说明 |
|------|------|
| **Memory Infrastructure** | 不是 Agent、不是聊天机器人，只做记忆存取与检索 |
| **严格分层** | MCP Tool 层禁止直接操作数据库，必须经 Service → Repository |
| **Provider 可插拔** | Embedding 与 LLM 各自抽象，切换厂商只改环境变量 |
| **两种模式** | Passive（默认零 LLM）与 AI Manager（可选自动治理） |
| **Workspace 隔离** | 所有数据按 workspace_id 隔离，互不污染 |
| **异步优先** | 全链路 async/await，IO 密集场景高吞吐 |

---

## 2. 两种运行模式

### 2.1 Passive Memory Mode（默认）

```
Cursor / Claude Code / Cline
        │  MCP protocol (stdio / sse)
        ▼
   MemoMCP Server
   ├─ MCP Tools (save_memory / search_memory / ...)
   ├─ MemoryService  ──► EmbeddingProvider
   ├─ MemoryRepository
   └─ PostgreSQL + pgvector
```

- Client 决定存什么、改什么、删什么
- 服务只负责：保存、生成 Embedding、向量搜索、数据管理
- **零 LLM 调用**，延迟最低，成本最低

### 2.2 AI Memory Manager Mode（可选，`AI_MEMORY_MANAGER=true`）

```
Cursor
   │
   ▼
MemoMCP Server
   ├─ MCP Tools
   ├─ MemoryService
   │    ├─► MemoryManager ──► LLMProvider ──► (Gemini / OpenAI / Compatible)
   │    └─► EmbeddingProvider
   ├─ MemoryRepository
   └─ PostgreSQL + pgvector
```

启用后，MemoryService 在写入/更新路径上调用 MemoryManager，自动完成：

| 能力 | 触发时机 |
|------|----------|
| 判断是否值得保存 | save_memory 调用时 |
| 自动总结 | 长文本写入时 |
| 自动合并重复 | save_memory 命中相似 Memory 时 |
| 自动生成标题 | 无 title 时 |
| 自动分类 | 写入时打 memory_type |
| 自动优化 | 定期/按需改写 |

---

## 3. 分层架构

```
┌─────────────────────────────────────────────────┐
│  接入层 ENTRY                                     │
│  ┌──────────────┐  ┌──────────────┐              │
│  │  MCP Tools   │  │  REST API    │              │
│  │  tools.py    │  │  api.py      │              │
│  └──────┬───────┘  └──────┬───────┘              │
├─────────┼─────────────────┼─────────────────────┤
│  服务层 SERVICE           │                       │
│  ┌────────────────────────▼──────────────────┐   │
│  │           MemoryService                    │   │
│  │  service.py — 业务逻辑编排                  │   │
│  └──────┬──────────────────────┬──────────────┘   │
│         │                      │                  │
├─────────┼──────────────────────┼─────────────────┤
│  仓储层 │ REPOSITORY            │ (依赖注入)        │
│  ┌──────▼─────────┐   ┌────────▼─────────┐       │
│  │MemoryRepository│   │  可插拔 PROVIDER   │       │
│  │ repository.py  │   │  ├ EmbeddingProvider│      │
│  └──────┬─────────┘   │  ├ LLMProvider     │      │
│         │             │  └ MemoryManager   │      │
├─────────┼─────────────┴────────────────────┤      │
│  数据层 │ DATA                              │      │
│  ┌──────▼─────────┐   ┌────────────────┐   │      │
│  │  models.py     │   │  PostgreSQL     │   │      │
│  │  SQLAlchemy 2.x│   │  pgvector+HNSW  │   │      │
│  └────────────────┘   └────────────────┘   │      │
└─────────────────────────────────────────────────┘
              config.py (Pydantic Settings, .env 驱动)
```

### 分层职责

| 层 | 文件 | 职责 | 禁止 |
|----|------|------|------|
| 接入层 | `tools.py` `api.py` | 参数校验、协议适配、调用 Service | 直接操作 DB |
| 服务层 | `service.py` | 业务编排、调用 Provider、事务管理 | 写 SQL |
| 仓储层 | `repository.py` | 数据访问、向量查询、全文检索 | 业务逻辑 |
| 数据层 | `models.py` `database.py` | ORM 模型、连接池、Session | — |
| Provider | `embedding/` `llm/` | 外部 API 调用封装 | 持有业务状态 |

---

## 4. 模块文件结构

```
MemoMCP/
├── docker-compose.yml          # 容器编排
├── .env.example                # 环境变量模板
├── README.md
├── ARCHITECTURE.md             # 本文档
│
└── memory-server/
    ├── Dockerfile
    ├── init.sql                # pgvector 扩展 + 初始 schema
    ├── requirements.txt
    └── app/
        ├── main.py             # FastMCP + FastAPI 启动入口
        ├── config.py           # Pydantic Settings 配置
        ├── database.py         # 异步引擎 + Session
        ├── models.py           # SQLAlchemy ORM 模型
        ├── schemas.py          # Pydantic 请求/响应模型
        ├── repository.py       # Repository Pattern
        ├── service.py          # Service Layer
        ├── tools.py            # MCP Tool 定义
        ├── api.py              # REST API 路由
        │
        ├── embedding/          # Embedding Provider 抽象
        │   ├── base.py         # EmbeddingProvider ABC
        │   ├── gemini.py
        │   ├── openai.py
        │   └── compatible.py
        │
        ├── llm/                # LLM Provider 抽象
        │   ├── base.py         # LLMProvider ABC
        │   ├── gemini.py
        │   ├── openai.py
        │   └── compatible.py
        │
        ├── memory_manager/     # AI 治理层（可选）
        │   ├── manager.py      # MemoryManager 编排
        │   └── prompts.py      # Prompt 模板
        │
        └── tests/
            ├── test_repository.py
            ├── test_service.py
            └── test_tools.py
```

---

## 5. Provider 抽象设计

### 5.1 EmbeddingProvider

```python
# app/embedding/base.py
class EmbeddingProvider(ABC):
    """Embedding 提供者抽象基类"""

    @property
    @abstractmethod
    def dimension(self) -> int:
        """向量维度"""

    @abstractmethod
    async def embed(self, text: str) -> list[float]:
        """单条文本转向量"""

    @abstractmethod
    async def embed_batch(self, texts: list[str]) -> list[list[float]]:
        """批量转向量"""

    async def health_check(self) -> bool:
        """健康检查"""
```

**三个实现：**

| 实现 | 文件 | 适用 |
|------|------|------|
| `GeminiEmbeddingProvider` | `embedding/gemini.py` | Google Gemini Embedding API |
| `OpenAIEmbeddingProvider` | `embedding/openai.py` | OpenAI 官方 text-embedding-3-* |
| `OpenAICompatibleEmbeddingProvider` | `embedding/compatible.py` | OpenRouter / DeepSeek / Ollama / vLLM / LocalAI 等任意兼容端点 |

### 5.2 LLMProvider（仅 AI Manager 模式）

```python
# app/llm/base.py
class LLMProvider(ABC):
    """LLM 提供者抽象基类"""

    @property
    @abstractmethod
    def model(self) -> str:
        """当前模型名"""

    @abstractmethod
    async def chat(self, messages: list[dict], **kwargs) -> str:
        """普通对话，返回文本"""

    @abstractmethod
    async def chat_json(
        self, messages: list[dict], schema: dict, **kwargs
    ) -> dict:
        """结构化输出，返回 JSON（带 schema 约束）"""
```

**三个实现：**

| 实现 | 文件 | 适用 |
|------|------|------|
| `GeminiLLMProvider` | `llm/gemini.py` | Gemini 2.x 系列 |
| `OpenAILLMProvider` | `llm/openai.py` | OpenAI 官方 API |
| `OpenAICompatibleLLMProvider` | `llm/compatible.py` | OpenRouter / DeepSeek / Moonshot / MiniMax / Ollama / vLLM / LocalAI |

### 5.3 工厂创建

`config.py` 根据 `.env` 自动实例化对应 Provider：

```
EMBEDDING_PROVIDER=gemini   → GeminiEmbeddingProvider
EMBEDDING_PROVIDER=openai   → OpenAIEmbeddingProvider
EMBEDDING_PROVIDER=compatible → OpenAICompatibleEmbeddingProvider

LLM_PROVIDER=gemini         → GeminiLLMProvider
LLM_PROVIDER=openai         → OpenAILLMProvider
LLM_PROVIDER=compatible     → OpenAICompatibleLLMProvider
```

未来扩展只需：新增一个实现文件 + 工厂分支加一行。

---

## 6. 数据库设计

### 6.1 memories 表

| 字段 | 类型 | 说明 |
|------|------|------|
| `id` | UUID PK | 主键 |
| `workspace_id` | VARCHAR(64) | 工作区隔离键，索引 |
| `memory_type` | VARCHAR(32) | 记忆类型枚举 |
| `title` | VARCHAR(256) | 标题 |
| `content` | TEXT | 完整内容 |
| `summary` | TEXT | 摘要（AI 生成或手填） |
| `tags` | VARCHAR[] | 标签数组 |
| `metadata` | JSONB | 扩展元数据 |
| `embedding` | vector(N) | 向量列 |
| `importance` | FLOAT | 重要度 0.0~1.0 |
| `source` | VARCHAR(64) | 来源（cursor / claude / manual） |
| `created_at` | TIMESTAMPTZ | 创建时间 |
| `updated_at` | TIMESTAMPTZ | 更新时间 |
| `last_access_at` | TIMESTAMPTZ | 最近访问时间 |
| `access_count` | INT | 访问计数 |

### 6.2 索引

```sql
-- HNSW 向量索引（核心，pgvector）
CREATE INDEX idx_memories_embedding ON memories
  USING hnsw (embedding vector_cosine_ops)
  WITH (m = 16, ef_construction = 64);

-- workspace 隔离查询
CREATE INDEX idx_memories_workspace ON memories (workspace_id);

-- 类型 + workspace 复合
CREATE INDEX idx_memories_ws_type ON memories (workspace_id, memory_type);

-- 全文检索（Hybrid Search 用）
CREATE INDEX idx_memories_content_fts ON memories
  USING gin (to_tsvector('english', content));

-- 时间排序
CREATE INDEX idx_memories_updated ON memories (updated_at DESC);
```

### 6.3 Memory 类型枚举

```
rule | preference | decision | architecture | knowledge
bug | solution | snippet | todo | api | command | experience
```

---

## 7. MCP Tools 设计

### 7.1 通用工具（两种模式都有）

| 工具 | 入参 | 出参 | 说明 |
|------|------|------|------|
| `save_memory` | workspace_id, memory_type, content, title?, tags?, importance?, source? | memory_id | 保存一条记忆 |
| `search_memory` | workspace_id, query, memory_type?, tags?, importance?, top_k? | list[memory] | 混合搜索 |
| `update_memory` | id, content?/title?/tags?/... | memory | 部分更新 |
| `delete_memory` | id | bool | 删除 |
| `get_memory` | id | memory | 单条详情 |
| `list_memory` | workspace_id, memory_type?, limit?, offset? | list[memory] | 分页列表 |
| `clear_workspace` | workspace_id, confirm | int(删除数) | 清空工作区 |

### 7.2 AI 模式额外工具

| 工具 | 说明 |
|------|------|
| `analyze_memory` | 分析单条记忆，给出重要度/分类建议 |
| `summarize_memory` | 批量总结指定 workspace 的记忆 |
| `merge_memory` | 合并多条相似记忆为一条 |

### 7.3 搜索策略

```
search_memory(query)
  │
  ├─ query 向量化 → EmbeddingProvider.embed(query)
  │
  ├─ 并行执行:
  │   ├─ Vector Search  (pgvector cosine, HNSW)
  │   └─ Full Text Search (ts_rank)
  │
  ├─ Hybrid 融合 (RRF - Reciprocal Rank Fusion)
  │
  └─ 综合排序:
      score = 0.6 * vector_sim
            + 0.2 * importance
            + 0.1 * recency_factor
            + 0.1 * access_factor
```

---

## 8. REST API 设计

| 方法 | 路径 | 说明 |
|------|------|------|
| GET | `/health` | 健康检查（DB + Provider 连通性） |
| GET | `/version` | 版本信息 |
| GET | `/stats` | 统计（各 workspace 记忆数、类型分布） |
| GET | `/memories` | 列表（?workspace_id=&type=&limit=） |
| POST | `/memories` | 创建 |
| GET | `/memories/{id}` | 详情 |
| PATCH | `/memories/{id}` | 更新 |
| DELETE | `/memories/{id}` | 删除 |
| POST | `/search` | 搜索（body: query + filters） |

用途：调试、管理、批量操作、监控集成。

---

## 9. 配置体系

```env
# ===== 运行模式 =====
AI_MEMORY_MANAGER=false          # true 启用 AI 治理层

# ===== LLM (仅 AI 模式需要) =====
LLM_PROVIDER=gemini              # gemini | openai | compatible
LLM_MODEL=gemini-2.0-flash       # 模型名
GEMINI_API_KEY=
OPENAI_API_KEY=
OPENAI_BASE_URL=                 # compatible 模式必填

# ===== Embedding =====
EMBEDDING_PROVIDER=gemini        # gemini | openai | compatible
EMBEDDING_MODEL=text-embedding-3-small
EMBEDDING_DIMENSION=1536

# ===== 数据库 =====
DATABASE_URL=postgresql+asyncpg://memomcp:memomcp@postgres:5432/memomcp

# ===== 服务 =====
MCP_TRANSPORT=stdio              # stdio | sse
REST_HOST=0.0.0.0
REST_PORT=8000
LOG_LEVEL=INFO
```

---

## 10. Docker 部署架构

```
docker-compose.yml
├── postgres        # PostgreSQL 17 + pgvector
│   ├─ volume: pgdata (持久化)
│   ├─ healthcheck: pg_isready
│   └─ init: 镜像内置 init.sql → 共享卷 → postgres 初始化
│
└── memory-server   # FastMCP + FastAPI
    ├─ depends_on: postgres (healthy)
    ├─ env_file: .env
    ├─ restart: unless-stopped
    └─ healthcheck: /health endpoint
```

启动：`docker compose up -d`

---

## 11. 关键技术选型理由

| 选型 | 理由 |
|------|------|
| **FastMCP** | MCP 官方 Python SDK，原生支持 stdio/sse 传输 |
| **FastAPI** | 与 FastMCP 共享 ASGI 生命周期，REST API 零额外成本 |
| **SQLAlchemy 2.x async** | 成熟的异步 ORM，配合 asyncpg 高性能 |
| **Alembic** | 数据库迁移，生产必备 |
| **pgvector + HNSW** | 向量检索在 PG 内完成，无需额外向量库；HNSW 近似最近邻，查询亚秒级 |
| **Pydantic Settings** | 类型安全配置，.env 驱动，校验开箱即用 |

---

## 12. 阶段实施计划

| 阶段 | 内容 | 交付物 |
|------|------|--------|
| **Phase 1** ✅ | 架构设计 | 本文档 |
| Phase 2 | 数据库 + Docker | memory-server/init.sql / Dockerfile / docker-compose.yml / models.py / database.py |
| Phase 3 | 基础 Memory API | repository.py / schemas.py / service.py / api.py |
| Phase 4 | MCP Server | tools.py / main.py |
| Phase 5 | Embedding Provider | embedding/* + 向量搜索集成 |
| Phase 6 | AI Memory Manager | llm/* + memory_manager/* |
| Phase 7 | 测试 + README | tests/* + README.md |

每个阶段完成后单独确认，确保代码可运行。
