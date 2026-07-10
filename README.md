# MemoMCP

> 基于 Model Context Protocol (MCP) 的通用长期记忆服务

为 Cursor、VSCode、Claude Code、Cline、Roo Code 等 AI Coding 工具提供统一的长期记忆能力。

**它不是聊天机器人。它不是完整 AI Agent。它是一个 Memory Infrastructure。**

---

## 目录

- [特性](#特性)
- [架构](#架构)
- [快速开始](#快速开始)
- [配置说明](#配置说明)
- [MCP Client 配置](#mcp-client-配置)
  - [Cursor](#cursor-配置)
  - [VSCode (Cline)](#vscode-cline-配置)
  - [Claude Code](#claude-code-配置)
- [运行模式](#运行模式)
  - [Passive Mode](#passive-mode默认模式)
  - [AI Memory Manager Mode](#ai-memory-manager-mode可选)
- [Provider 切换](#provider-切换)
- [REST API](#rest-api)
- [MCP Tools](#mcp-tools)
- [开发指南](#开发指南)
- [项目结构](#项目结构)

---

## 特性

- **两种运行模式**：Passive（零 LLM）/ AI Memory Manager（自动治理）
- **Provider 可插拔**：Embedding 与 LLM 各自抽象，支持 Gemini / OpenAI / 任意 OpenAI 兼容端点
- **Hybrid Search**：向量搜索 + 全文检索 + RRF 融合排序
- **Workspace 隔离**：不同项目/工作区的记忆互不污染
- **MCP + REST 双协议**：MCP 供 AI 工具调用，REST 供调试管理
- **生产就绪**：Docker Compose、健康检查、数据持久化、自动重启

---

## 架构

```
┌──────────────────────────────────────────────┐
│  接入层                                       │
│  ┌────────────┐  ┌────────────┐              │
│  │ MCP Tools  │  │ REST API   │              │
│  │ (10 tools) │  │ (/api/v1)  │              │
│  └─────┬──────┘  └─────┬──────┘              │
├────────┼────────────────┼────────────────────┤
│  服务层 │                │                     │
│  ┌──────▼────────────────▼──────┐             │
│  │       MemoryService          │             │
│  └──┬──────────┬──────────┬─────┘             │
│     │          │          │                   │
│  ┌──▼──┐  ┌───▼────┐  ┌──▼────────┐          │
│  │Repo │  │Embedding│  │AI Manager │          │
│  │     │  │Provider │  │(optional) │          │
│  └──┬──┘  └────────┘  └─────┬─────┘          │
├─────┼──────────────────────┼─────────────────┤
│  ┌──▼──────────────────────▼─────┐           │
│  │    PostgreSQL + pgvector      │           │
│  │    (HNSW + GIN 全文索引)       │           │
│  └───────────────────────────────┘           │
└──────────────────────────────────────────────┘
```

**严格分层**：MCP Tool 层不碰数据库，必须经 Service → Repository。

---

## 快速开始

### 前置要求

- Docker + Docker Compose（或 Colima）
- 1GB+ 可用内存

### 1. 克隆项目

```bash
git clone https://github.com/ieiian/MemoMCP.git
cd MemoMCP
```

### 2. 配置环境变量

```bash
cp .env.example .env
# 按需编辑 .env（至少配置数据库连接）
```

### 3. 启动服务

```bash
docker compose up -d
```

这会启动：
- **PostgreSQL 17 + pgvector**（端口 5432，数据持久化）
- **MemoMCP Server**（端口 8000，REST API）

### 4. 验证

```bash
curl http://localhost:8000/api/v1/health
# {"status":"ok","database":"ok","version":"0.1.0"}
```

### 5. 查看日志

```bash
docker compose logs -f memory-server
```

### 6. 停止

```bash
docker compose down
# 停止并删除数据
docker compose down -v
```

---

## 配置说明

所有配置通过 `.env` 文件管理（参考 `.env.example`）：

```env
# ===== 运行模式 =====
AI_MEMORY_MANAGER=false          # true 启用 AI 治理层

# ===== LLM Provider（仅 AI 模式需要）=====
LLM_PROVIDER=gemini              # gemini | openai | compatible
LLM_MODEL=gemini-2.0-flash
GEMINI_API_KEY=
OPENAI_API_KEY=
OPENAI_BASE_URL=                 # compatible 模式必填

# ===== Embedding Provider =====
EMBEDDING_PROVIDER=gemini        # gemini | openai | compatible
EMBEDDING_MODEL=text-embedding-3-small
EMBEDDING_DIMENSION=1536         # 必须与 init.sql 一致

# ===== 数据库 =====
DATABASE_URL=postgresql+asyncpg://memomcp:memomcp@postgres:5432/memomcp

# ===== MCP 传输 =====
MCP_TRANSPORT=stdio              # stdio | sse

# ===== REST API =====
REST_HOST=0.0.0.0
REST_PORT=8000

# ===== 日志 =====
LOG_LEVEL=INFO
```

### 维度对照表

| Provider | 模型 | 维度 | EMBEDDING_DIMENSION |
|----------|------|------|---------------------|
| OpenAI | text-embedding-3-small | 1536 | 1536 |
| OpenAI | text-embedding-3-large | 3072 | 3072 |
| Gemini | text-embedding-004 | 768 | 768 |
| Ollama | nomic-embed-text | 768 | 768 |

> **注意**：更改维度需要修改 `memory-server/init.sql` 中的 `vector(N)` 并重建数据库。

---

## MCP Client 配置

### Cursor 配置

编辑 `~/.cursor/mcp.json`（或项目根目录 `.cursor/mcp.json`）：

```json
{
  "mcpServers": {
    "memomcp": {
      "command": "python",
      "args": ["-m", "app.main", "--mcp"],
      "cwd": "/path/to/MemoMCP/memory-server",
      "env": {
        "DATABASE_URL": "postgresql+asyncpg://memomcp:memomcp@localhost:5432/memomcp",
        "AI_MEMORY_MANAGER": "false",
        "LOG_LEVEL": "INFO"
      }
    }
  }
}
```

重启 Cursor 后，在 Settings → MCP 中确认 `memomcp` 已连接。

### VSCode (Cline) 配置

编辑 Cline 的 MCP 设置（`~/Library/Application Support/Code/User/globalStorage/saoudrizwan.claude-dev/settings/cline_mcp_settings.json`）：

```json
{
  "mcpServers": {
    "memomcp": {
      "command": "python",
      "args": ["-m", "app.main", "--mcp"],
      "cwd": "/path/to/MemoMCP/memory-server",
      "env": {
        "DATABASE_URL": "postgresql+asyncpg://memomcp:memomcp@localhost:5432/memomcp"
      }
    }
  }
}
```

### Claude Code 配置

编辑 `~/.claude/claude_desktop_config.json`：

```json
{
  "mcpServers": {
    "memomcp": {
      "command": "python",
      "args": ["-m", "app.main", "--mcp"],
      "cwd": "/path/to/MemoMCP/memory-server",
      "env": {
        "DATABASE_URL": "postgresql+asyncpg://memomcp:memomcp@localhost:5432/memomcp"
      }
    }
  }
}
```

> **提示**：`python` 需要在 PATH 中，且已安装所有依赖（`pip install -r requirements.txt`）。
> 也可以直接用 venv 的 python 绝对路径。

---

## 运行模式

### Passive Mode（默认模式）

**零 LLM 调用，延迟最低。**

```env
AI_MEMORY_MANAGER=false
```

- AI Coding 工具（Cursor）决定存什么、改什么
- MemoMCP 只负责：保存、生成 Embedding（如果配置了）、向量搜索、数据管理
- 如果 Embedding Provider 也未配置，回退到关键词搜索

**使用示例**（在 Cursor 中对话）：

```
用户: 以后所有项目使用 pnpm
Cursor: [调用 save_memory] 已保存偏好
用户: 我之前说过用什么包管理器？
Cursor: [调用 search_memory] 你之前设定了使用 pnpm
```

### AI Memory Manager Mode（可选）

**自动判断、总结、合并、分类。**

```env
AI_MEMORY_MANAGER=true
LLM_PROVIDER=gemini
GEMINI_API_KEY=your_api_key
```

启用后额外获得 3 个 AI 工具：

| 工具 | 功能 |
|------|------|
| `analyze_memory` | 分析单条记忆，给出重要度/分类/改进建议 |
| `summarize_memory` | 批量总结整个工作区的记忆 |
| `merge_memory` | 合并多条相似记忆为一条 |

同时 `save_memory` 自动增强：
- 无标题时自动生成
- 长内容自动生成摘要

---

## Provider 切换

### Embedding Provider

```env
# Gemini (768 维)
EMBEDDING_PROVIDER=gemini
GEMINI_API_KEY=your_key
EMBEDDING_DIMENSION=768

# OpenAI (1536 维)
EMBEDDING_PROVIDER=openai
OPENAI_API_KEY=your_key
EMBEDDING_DIMENSION=1536

# Ollama 本地 (无需 API Key)
EMBEDDING_PROVIDER=compatible
OPENAI_BASE_URL=http://localhost:11434/v1
EMBEDDING_MODEL=nomic-embed-text
EMBEDDING_DIMENSION=768

# vLLM / LocalAI
EMBEDDING_PROVIDER=compatible
OPENAI_BASE_URL=http://localhost:8080/v1
EMBEDDING_MODEL=your-model
```

### LLM Provider（仅 AI Manager 模式）

```env
# Gemini
LLM_PROVIDER=gemini
LLM_MODEL=gemini-2.0-flash
GEMINI_API_KEY=your_key

# OpenAI
LLM_PROVIDER=openai
LLM_MODEL=gpt-4o-mini
OPENAI_API_KEY=your_key

# DeepSeek
LLM_PROVIDER=compatible
LLM_MODEL=deepseek-chat
OPENAI_BASE_URL=https://api.deepseek.com/v1
OPENAI_API_KEY=your_key

# Ollama 本地
LLM_PROVIDER=compatible
LLM_MODEL=llama3.2
OPENAI_BASE_URL=http://localhost:11434/v1
```

---

## REST API

REST API 用于调试、管理和监控。默认端口 `8000`。

| 方法 | 路径 | 说明 |
|------|------|------|
| GET | `/api/v1/health` | 健康检查 |
| GET | `/api/v1/version` | 版本信息 |
| GET | `/api/v1/stats` | 全局统计 |
| GET | `/api/v1/stats/{workspace_id}` | 工作区统计 |
| GET | `/api/v1/memories?workspace_id=` | 列表查询 |
| POST | `/api/v1/memories` | 创建 |
| GET | `/api/v1/memories/{id}` | 获取单条 |
| PATCH | `/api/v1/memories/{id}` | 更新 |
| DELETE | `/api/v1/memories/{id}` | 删除 |
| POST | `/api/v1/search` | 搜索 |
| DELETE | `/api/v1/workspaces/{workspace_id}?confirm=true` | 清空工作区 |

**Swagger 文档**：`http://localhost:8000/docs`

---

## MCP Tools

### 通用工具（7 个，两种模式都可用）

| 工具 | 参数 | 说明 |
|------|------|------|
| `save_memory` | workspace_id, memory_type, content, title?, tags?, importance?, source? | 保存记忆 |
| `search_memory` | workspace_id, query, memory_type?, tags?, importance_min?, top_k? | 搜索记忆 |
| `update_memory` | memory_id, title?, content?, summary?, tags?, metadata?, importance?, memory_type? | 更新记忆 |
| `delete_memory` | memory_id | 删除记忆 |
| `get_memory` | memory_id | 获取单条（自动访问计数） |
| `list_memory` | workspace_id, memory_type?, tags?, importance_min?, limit?, offset? | 列表查询 |
| `clear_workspace` | workspace_id, confirm | 清空工作区 |

### AI 工具（3 个，需 AI_MEMORY_MANAGER=true）

| 工具 | 参数 | 说明 |
|------|------|------|
| `analyze_memory` | memory_id | AI 分析记忆，给出建议 |
| `summarize_memory` | workspace_id, limit? | AI 总结工作区 |
| `merge_memory` | memory_ids (list) | AI 合并多条记忆 |

### Memory 类型

```
rule | preference | decision | architecture | knowledge
bug | solution | snippet | todo | api | command | experience
```

### 搜索策略

```
有 Embedding Provider?
  ├─ 是 → Hybrid Search
  │       向量搜索 (cosine + HNSW) ∪ 关键词搜索 (ILIKE + ts_rank)
  │       → RRF 融合排序 → 截断 top_k
  │
  └─ 否 → 关键词搜索
          ILIKE 多词 OR 匹配 + ts_rank 排序
```

---

## 开发指南

### 本地开发（不使用 Docker）

```bash
# 1. 启动 PostgreSQL（仍用 Docker）
docker compose up -d postgres

# 2. 创建虚拟环境
python -m venv venv
source venv/bin/activate

# 3. 安装依赖
pip install -r memory-server/requirements.txt

# 4. 运行 REST API
cd memory-server
DATABASE_URL="postgresql+asyncpg://memomcp:memomcp@localhost:5432/memomcp" \
  python -m app.main

# 5. 运行 MCP Server（stdio）
cd memory-server
DATABASE_URL="postgresql+asyncpg://memomcp:memomcp@localhost:5432/memomcp" \
  python -m app.main --mcp

# 6. 运行 MCP Server（HTTP）
python -m app.main --mcp --transport http --port 9000
```

### 运行测试

```bash
cd memory-server
pip install pytest pytest-asyncio

DATABASE_URL="postgresql+asyncpg://memomcp:memomcp@localhost:5432/memomcp" \
  python -m pytest app/tests/ -v
```

### 技术栈

| 组件 | 技术 |
|------|------|
| 语言 | Python 3.12 |
| MCP | FastMCP 3.x |
| Web | FastAPI + Uvicorn |
| ORM | SQLAlchemy 2.x (async) |
| 数据库 | PostgreSQL 17 + pgvector |
| 向量索引 | HNSW (pgvector) |
| 全文检索 | PostgreSQL ts_rank + GIN |
| 配置 | Pydantic Settings |
| 迁移 | Alembic（预留） |
| 部署 | Docker Compose |

---

## 项目结构

```
MemoMCP/
├── docker-compose.yml          # 容器编排
├── .env.example                # 环境变量模板
├── mcp-config.example.json     # MCP Client 配置模板
├── ARCHITECTURE.md             # 架构设计文档
├── README.md                   # 本文档
│
└── memory-server/
    ├── Dockerfile
    ├── init.sql                # pgvector 扩展 + 表 + 索引
    ├── requirements.txt
    └── app/
        ├── main.py             # 入口（REST API / MCP 双模式）
        ├── config.py           # Pydantic Settings
        ├── database.py         # 异步引擎 + Session + NullPool
        ├── models.py           # SQLAlchemy ORM (memories 表)
        ├── schemas.py          # Pydantic 请求/响应模型
        ├── repository.py       # Repository Pattern (CRUD + 搜索)
        ├── service.py          # Service Layer (业务逻辑 + RRF)
        ├── tools.py            # MCP Tools (10 个)
        ├── api.py              # REST API 路由
        │
        ├── embedding/          # Embedding Provider
        │   ├── base.py         # 抽象基类
        │   ├── gemini.py
        │   ├── openai.py
        │   ├── compatible.py
        │   └── __init__.py     # 工厂函数
        │
        ├── llm/                # LLM Provider
        │   ├── base.py         # 抽象基类
        │   ├── gemini.py
        │   ├── openai.py
        │   ├── compatible.py
        │   └── __init__.py     # 工厂函数
        │
        ├── memory_manager/     # AI Memory Manager
        │   ├── manager.py      # MemoryManager
        │   ├── prompts.py      # Prompt 模板
        │   └── __init__.py
        │
        └── tests/              # 测试
            ├── conftest.py     # pytest fixture
            ├── test_repository.py
            ├── test_service.py
            └── test_tools.py
```

---

## License

MIT
