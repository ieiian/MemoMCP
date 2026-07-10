# Repository Overview — MemoMCP

> 基于 Model Context Protocol (MCP) 的通用长期记忆服务

本文档是 MemoMCP 的完整部署与使用手册，涵盖 Docker 部署、MCP Client 连接、参数配置和测试方法。

---

## 1. 项目简介

MemoMCP 是一个 **Memory Infrastructure**，为 AI Coding 工具提供长期记忆存储、Workspace 隔离、Hybrid Search（向量+全文+RRF）和可选的 AI 治理（自动分类/总结/合并）。

**两种运行模式**：

| 模式 | AI_MEMORY_MANAGER | LLM 调用 | 搜索策略 |
|------|-------------------|----------|----------|
| Passive（默认） | false | 零 LLM | 关键词 / 向量 |
| AI Manager | true | 按需调用 | Hybrid + AI 治理 |

**10 个 MCP 工具**：通用 7 个（save/search/update/delete/get/list/clear）+ AI 3 个（analyze/summarize/merge，需 AI 模式）

---

## 2. 镜像构建与获取

```bash
# 从 Docker Hub 拉取（推荐）
docker pull ieiian/memomcp-server:latest

# 或从源码构建
cd memory-server
docker build -t ieiian/memomcp-server:latest -f Dockerfile .

# 推送到仓库
docker push ieiian/memomcp-server:latest
```

- 基础镜像：`python:3.12-slim`
- 暴露端口：8000（REST API）
- 运行用户：非 root `memomcp`
- 默认启动：`uvicorn app.main:app`
- 内置 `init.sql`：镜像内 `/app/init.sql`，部署时自动提取供 PostgreSQL 初始化

---

## 3. 部署方式

### 3.1 Docker Compose 部署（推荐）

```bash
# 1. 配置环境变量
cp .env.example .env
vi .env

# 2. 启动
docker compose up -d

# 3. 验证
curl http://localhost:8000/api/v1/health
# {"status":"ok","database":"ok","version":"0.1.0"}

# 4. 查看日志
docker compose logs -f memory-server

# 5. 停止
docker compose down          # 保留数据
docker compose down -v       # 删除数据卷
```

`.env` 最小配置（Passive 模式）：

```env
AI_MEMORY_MANAGER=false
EMBEDDING_PROVIDER=gemini
GEMINI_API_KEY=your_gemini_api_key
EMBEDDING_DIMENSION=768
DATABASE_URL=postgresql+asyncpg://memomcp:memomcp@postgres:5432/memomcp
LOG_LEVEL=INFO
```

> `docker-compose.yml` 使用 `ieiian/memomcp-server:latest` 镜像，无需本地构建。
> `init.sql` 已打入镜像，部署时由 init 容器自动提取到共享卷，无需用户手动创建。

完整 `docker-compose.yml` 内容：

```yaml
services:
  # 从镜像中提取 init.sql 到共享卷，避免宿主机文件不存在被创建为目录
  init-db:
    image: ieiian/memomcp-server:latest
    container_name: memomcp-init-db
    volumes:
      - db-init:/init-scripts
    command: >
      sh -c "cp /app/init.sql /init-scripts/init.sql && echo 'init.sql copied'"

  postgres:
    image: pgvector/pgvector:pg17
    container_name: memomcp-postgres
    environment:
      POSTGRES_USER: memomcp
      POSTGRES_PASSWORD: memomcp
      POSTGRES_DB: memomcp
    ports:
      - "5432:5432"
    volumes:
      - pgdata:/var/lib/postgresql/data
      - db-init:/docker-entrypoint-initdb.d:ro
    depends_on:
      init-db:
        condition: service_completed_successfully
    healthcheck:
      test: ["CMD-SHELL", "pg_isready -U memomcp -d memomcp"]
      interval: 10s
      timeout: 5s
      retries: 5
      start_period: 10s
    restart: unless-stopped

  memory-server:
    image: ieiian/memomcp-server:latest
    container_name: memomcp-server
    env_file:
      - .env
    environment:
      # 覆盖 DATABASE_URL 指向 compose 内部网络
      DATABASE_URL: postgresql+asyncpg://memomcp:memomcp@postgres:5432/memomcp
    ports:
      - "8000:8000"
    depends_on:
      postgres:
        condition: service_healthy
    healthcheck:
      test: ["CMD-SHELL", "python -c \"import urllib.request; urllib.request.urlopen('http://localhost:8000/api/v1/health')\" || exit 1"]
      interval: 30s
      timeout: 5s
      retries: 3
      start_period: 15s
    restart: unless-stopped

volumes:
  pgdata:
    driver: local
  db-init:
    driver: local
```

完整 `.env` 配置模板：

```env
# ===== 运行模式 =====
# false = Passive Mode（默认，零 LLM 调用）
# true  = AI Memory Manager Mode（启用自动治理层）
AI_MEMORY_MANAGER=false

# ===== LLM Provider（仅 AI_MEMORY_MANAGER=true 时需要）=====
# 可选: gemini | openai | compatible
LLM_PROVIDER=gemini
LLM_MODEL=gemini-2.0-flash
GEMINI_API_KEY=your_gemini_api_key
OPENAI_API_KEY=
# compatible 模式必填，例如: https://api.deepseek.com/v1
OPENAI_BASE_URL=

# ===== Embedding Provider =====
# 可选: gemini | openai | compatible
EMBEDDING_PROVIDER=gemini
EMBEDDING_MODEL=text-embedding-3-small
# 维度必须与 init.sql 一致（改维度需重建数据库）
# OpenAI text-embedding-3-small=1536  text-embedding-3-large=3072
# Gemini text-embedding-004=768  Ollama nomic-embed-text=768
EMBEDDING_DIMENSION=768

# ===== 数据库 =====
DATABASE_URL=postgresql+asyncpg://memomcp:memomcp@postgres:5432/memomcp

# ===== MCP 传输 =====
# stdio = 本地连接（Cursor / Claude Code）
# sse   = 远程连接
MCP_TRANSPORT=stdio

# ===== REST API =====
REST_HOST=0.0.0.0
REST_PORT=8000

# ===== 日志 =====
LOG_LEVEL=INFO
```

### 3.2 Docker Run 部署

```bash
# 1. 创建网络
docker network create memomcp-net

# 2. 从镜像提取 init.sql 到临时卷
docker run --rm \
  -v memomcp-init:/init-scripts \
  ieiian/memomcp-server:latest \
  sh -c "cp /app/init.sql /init-scripts/init.sql"

# 3. 启动 PostgreSQL（使用共享卷中的 init.sql）
docker run -d \
  --name memomcp-postgres \
  --network memomcp-net \
  -e POSTGRES_USER=memomcp \
  -e POSTGRES_PASSWORD=memomcp \
  -e POSTGRES_DB=memomcp \
  -v memomcp-pgdata:/var/lib/postgresql/data \
  -v memomcp-init:/docker-entrypoint-initdb.d:ro \
  -p 5432:5432 \
  --health-cmd "pg_isready -U memomcp -d memomcp" \
  --health-interval 10s --health-retries 5 \
  --restart unless-stopped \
  pgvector/pgvector:pg17

# 4. 等待 PostgreSQL 就绪
until [ "$(docker inspect --format='{{.State.Health.Status}}' memomcp-postgres)" = "healthy" ]; do sleep 3; done

# 5A. 启动 REST API 服务（管理 + 调试）
docker run -d \
  --name memomcp-server \
  --network memomcp-net \
  -e DATABASE_URL=postgresql+asyncpg://memomcp:memomcp@memomcp-postgres:5432/memomcp \
  -e AI_MEMORY_MANAGER=false \
  -e EMBEDDING_PROVIDER=gemini \
  -e GEMINI_API_KEY=your_key \
  -e EMBEDDING_DIMENSION=768 \
  -p 8000:8000 \
  --restart unless-stopped \
  ieiian/memomcp-server:latest

# 5B. 启动 MCP HTTP 服务（远程 MCP 连接，可同时运行）
docker run -d \
  --name memomcp-mcp \
  --network memomcp-net \
  -e DATABASE_URL=postgresql+asyncpg://memomcp:memomcp@memomcp-postgres:5432/memomcp \
  -e AI_MEMORY_MANAGER=false \
  -p 9000:9000 \
  --restart unless-stopped \
  ieiian/memomcp-server:latest \
  python -m app.main --mcp --transport http --port 9000
```

> MCP HTTP 端点为 `http://<host>:9000/mcp`，与 REST API 可同时运行共享同一数据库。

### 3.3 本地运行（开发调试）

```bash
docker compose up -d postgres    # 仅启动数据库
python -m venv venv && source venv/bin/activate
pip install -r memory-server/requirements.txt
cd memory-server

# REST API
DATABASE_URL="postgresql+asyncpg://memomcp:memomcp@localhost:5432/memomcp" python -m app.main

# MCP stdio（本地连接）
DATABASE_URL="postgresql+asyncpg://memomcp:memomcp@localhost:5432/memomcp" python -m app.main --mcp

# MCP HTTP（远程连接）
DATABASE_URL="postgresql+asyncpg://memomcp:memomcp@localhost:5432/memomcp" python -m app.main --mcp --transport http --port 9000
```

---

## 4. Vibe Coding 工具连接 MCP

### 4.1 连接模式

| 模式 | 传输 | 适用场景 | 端口 |
|------|------|----------|------|
| **stdio** | 本地进程 stdin/stdout | 工具与 MemoMCP 同一台机器 | 无 |
| **HTTP** | 远程 HTTP | MemoMCP 部署在服务器，多客户端共享 | 9000 |

### 4.2 Cursor

**本地（stdio）**— 编辑 `~/.cursor/mcp.json`：

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
        "GEMINI_API_KEY": "your_key",
        "EMBEDDING_DIMENSION": "768"
      }
    }
  }
}
```

**远程（HTTP）**：

```json
{
  "mcpServers": {
    "memomcp": {
      "url": "http://your-server:9000/mcp"
    }
  }
}
```

### 4.3 VSCode + Cline

编辑 Cline MCP 设置（`~/Library/Application Support/Code/User/globalStorage/saoudrizwan.claude-dev/settings/cline_mcp_settings.json`）：

**本地**：同 Cursor 配置，额外添加 `"transportType": "stdio"`

**远程**：

```json
{
  "mcpServers": {
    "memomcp": {
      "url": "http://your-server:9000/mcp",
      "transportType": "sse"
    }
  }
}
```

### 4.4 Claude Code (Claude Desktop)

编辑 `~/.claude/claude_desktop_config.json`：

**本地**：同 Cursor 配置

**远程**：

```json
{
  "mcpServers": {
    "memomcp": {
      "type": "http",
      "url": "http://your-server:9000/mcp"
    }
  }
}
```

### 4.5 Roo Code / Windsurf

配置格式同 Cursor。Roo Code 额外支持 `"alwaysAllow"` 数组自动批准工具调用。Windsurf 配置文件在 `~/.codeium/windsurf/mcp_config.json`。

### 远程 MCP 安全建议

```nginx
# nginx 反向代理（关闭 buffering，支持 SSE 长连接）
location /mcp {
    proxy_pass http://127.0.0.1:9000/mcp;
    proxy_buffering off;
    proxy_read_timeout 86400s;
}
```

```bash
# 防火墙：仅放行需要的端口
ufw allow 9000/tcp    # MCP HTTP
ufw deny 5432/tcp     # PostgreSQL 不对外
```

> 生产环境建议 docker-compose.yml 中 PostgreSQL 不映射端口（仅 `expose`），只通过内部网络访问。

---

## 5. 参数设置

### 5.1 环境变量

| 变量 | 必填 | 默认值 | 说明 |
|------|------|--------|------|
| `AI_MEMORY_MANAGER` | 否 | `false` | `true` 启用 AI 治理层 |
| `LLM_PROVIDER` | 否 | `gemini` | `gemini`/`openai`/`compatible` |
| `LLM_MODEL` | 否 | `gemini-2.0-flash` | LLM 模型名 |
| `GEMINI_API_KEY` | 条件 | - | Gemini API Key |
| `OPENAI_API_KEY` | 条件 | - | OpenAI API Key |
| `OPENAI_BASE_URL` | 条件 | - | 兼容端点 URL（compatible 模式必填） |
| `EMBEDDING_PROVIDER` | 否 | `gemini` | `gemini`/`openai`/`compatible` |
| `EMBEDDING_MODEL` | 否 | `text-embedding-3-small` | Embedding 模型名 |
| `EMBEDDING_DIMENSION` | 否 | `1536` | 向量维度（**必须与 init.sql 一致**） |
| `DATABASE_URL` | **是** | - | PostgreSQL 异步连接字符串 |
| `MCP_TRANSPORT` | 否 | `stdio` | `stdio`/`sse` |
| `REST_HOST` / `REST_PORT` | 否 | `0.0.0.0` / `8000` | REST API 监听 |
| `LOG_LEVEL` | 否 | `INFO` | `DEBUG`/`INFO`/`WARNING`/`ERROR` |

### 5.2 Provider 配置示例

**Gemini**（768 维）：
```env
LLM_PROVIDER=gemini
LLM_MODEL=gemini-2.0-flash
GEMINI_API_KEY=your_key
EMBEDDING_PROVIDER=gemini
EMBEDDING_MODEL=text-embedding-004
EMBEDDING_DIMENSION=768
```

**OpenAI**（1536 维）：
```env
LLM_PROVIDER=openai
LLM_MODEL=gpt-4o-mini
OPENAI_API_KEY=sk-your_key
EMBEDDING_PROVIDER=openai
EMBEDDING_DIMENSION=1536
```

**DeepSeek**（LLM 用 DeepSeek，Embedding 用 OpenAI）：
```env
LLM_PROVIDER=compatible
LLM_MODEL=deepseek-chat
OPENAI_BASE_URL=https://api.deepseek.com/v1
OPENAI_API_KEY=your_deepseek_key
EMBEDDING_PROVIDER=openai
OPENAI_API_KEY=sk-your_openai_key
EMBEDDING_DIMENSION=1536
```

**Ollama 本地**（无需 API Key）：
```env
LLM_PROVIDER=compatible
LLM_MODEL=llama3.2
OPENAI_BASE_URL=http://localhost:11434/v1
OPENAI_API_KEY=dummy
EMBEDDING_PROVIDER=compatible
EMBEDDING_MODEL=nomic-embed-text
EMBEDDING_DIMENSION=768
```

> 维度对照：text-embedding-3-small=1536，text-embedding-3-large=3072，text-embedding-004/nomic-embed-text=768

---

## 6. 测试方式

### 6.1 单元测试

```bash
cd memory-server
pip install pytest pytest-asyncio
DATABASE_URL="postgresql+asyncpg://memomcp:memomcp@localhost:5432/memomcp" \
  AI_MEMORY_MANAGER=false GEMINI_API_KEY="" OPENAI_API_KEY="" \
  python -m pytest app/tests/ -v --asyncio-mode=auto
# 期望: 18 passed
```

| 文件 | 测试数 | 覆盖范围 |
|------|--------|----------|
| `test_repository.py` | 8 | CRUD、搜索、隔离、统计 |
| `test_service.py` | 6 | 创建、搜索、RRF、统计 |
| `test_tools.py` | 4 | 工具注册、调用、AI 回退 |

### 6.2 REST API 测试

```bash
curl http://localhost:8000/api/v1/health
curl -X POST http://localhost:8000/api/v1/memories -H "Content-Type: application/json" \
  -d '{"workspace_id":"test","memory_type":"rule","content":"Use pnpm","title":"Pkg Manager"}'
curl -X POST http://localhost:8000/api/v1/search -H "Content-Type: application/json" \
  -d '{"workspace_id":"test","query":"pnpm"}'
curl "http://localhost:8000/api/v1/memories?workspace_id=test"
curl http://localhost:8000/api/v1/stats
# Swagger UI: http://localhost:8000/docs
```

### 6.3 MCP 工具测试

```python
# 用 FastMCP Client 测试 HTTP 模式
import asyncio
from fastmcp import Client

async def test():
    async with Client("http://localhost:9000/mcp") as client:
        tools = await client.list_tools()
        print(f"Tools: {[t.name for t in tools]}")
        result = await client.call_tool("save_memory", {
            "workspace_id": "test", "memory_type": "rule",
            "content": "Always write tests", "importance": 0.8
        })
        print(f"Saved: {result.structured_content['id']}")

asyncio.run(test())
```

### 6.4 健康检查

```bash
curl -s http://localhost:8000/api/v1/health | python -m json.tool
docker inspect --format='{{.State.Health.Status}}' memomcp-server  # 期望: healthy
docker exec memomcp-postgres psql -U memomcp -d memomcp -c "SELECT extname FROM pg_extension;"  # 期望包含: vector
```

---

## 7. 故障排查

| 问题 | 原因 | 解决 |
|------|------|------|
| Docker 构建超时 | Colima 内存不足 | `colima start --cpu 4 --memory 8`；Dockerfile 已配置清华镜像加速 |
| MCP 连接失败 | cwd 非绝对路径 / python 不在 PATH / DB 未运行 | 检查路径、用 venv 绝对路径、确认 `docker compose ps` |
| 搜索返回空 | 关键词不匹配 / workspace 不匹配 / 数据库为空 | 用 `save_memory` 先创建数据，确保 workspace_id 一致 |
| embedding 失败 | API Key 无效 / 网络不通 / 维度不匹配 | 查看日志 `docker compose logs memory-server \| grep embedding` |
| 事件循环冲突 | 连接池绑定错误循环 | 已通过 NullPool 修复，确认 database.py 使用 `poolclass=NullPool` |
| 中文搜索效果差 | ts_rank 默认 english 配置 | 配置 Embedding Provider 启用向量搜索，对中文语义匹配效果更好 |