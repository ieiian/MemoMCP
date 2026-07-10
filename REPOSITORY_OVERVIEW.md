# MemoMCP 部署与使用手册

> 基于 MCP 的通用长期记忆服务 — Docker 部署、环境配置、MCP 连接

---

## 1. 简介

MemoMCP 为 Cursor、Claude Code 等 AI 编码工具提供长期记忆存储，支持 Workspace 隔离、Hybrid Search（向量 + 全文 + RRF）及可选 AI 治理。

| 模式 | `AI_MEMORY_MANAGER` | 说明 |
|------|---------------------|------|
| Passive（默认） | `false` | 零 LLM 调用，关键词 / 向量搜索 |
| AI Manager | `true` | Hybrid 搜索 + 自动分类 / 总结 / 合并 |

**MCP 工具**：通用 7 个（save / search / update / delete / get / list / clear）+ AI 3 个（analyze / summarize / merge，需 AI 模式）

**Web 入口**（REST 模式启动后）：

| 路径 | 说明 |
|------|------|
| `/` | 服务首页 |
| `/admin` | 管理台（记忆 CRUD、备份迁移、活动监控） |
| `/docs` | Swagger API 文档 |
| `/api/v1` | REST API |

---

## 2. 镜像

```bash
# 拉取远程镜像（推荐）
docker pull ieiian/memomcp-server:latest

# 本地构建（打同 tag 可模拟远程部署）
cd memory-server
docker build -t ieiian/memomcp-server:latest -f Dockerfile .

# 推送
docker push ieiian/memomcp-server:latest
```

- 基础镜像：`python:3.12-slim`，运行用户 `memomcp`（非 root）
- 暴露端口：`8000`（REST API）
- 内置 `init.sql` 位于镜像 `/app/init.sql`，由 init 容器提取供 PostgreSQL 初始化

---

## 3. 部署

### 3.0 通用准备

```bash
cp .env.example .env    # 编辑 API Key 等配置
docker compose up -d    # 默认 Bridge 网桥模式，容器间直连（见 3.1）
curl http://localhost:8000/api/v1/health
```

**三种 Compose 网络方案**：

| 方式 | 配置文件 | 网络 | `DATABASE_URL` 主机 | 适用场景 |
|------|----------|------|---------------------|----------|
| **Bridge 容器直连**（推荐） | `docker-compose.yml`（默认） | `memomcp-net` bridge | `postgres` | 标准 Docker / 跨平台 |
| **宿主机绕行**（兼容） | `docker-compose.host-gateway.yml` | bridge + `host.docker.internal` | `host.docker.internal` | Colima 等容器名 DNS 异常时兜底 |
| **Host Network**（真 Host） | `docker-compose.host.yml` | `network_mode: host` | `127.0.0.1` | **Linux 服务器**，追求零 NAT、端口直绑宿主机 |

> `init-db` 容器需 `user: "0:0"` 写入命名卷，否则会 Permission denied。

**概念区分**：
- **Bridge（默认）**：容器在独立网桥内，通过服务名 `postgres` 互联；`ports` 映射供宿主机访问。
- **宿主机绕行**：仍是 bridge，但 DB 流量绕道 `host.docker.internal → 宿主机:5432 → postgres`，是兼容性妥协。
- **Host Network**：`network_mode: host`，容器与宿主机共享网络栈，无 `ports` 映射，**仅 Linux 完整支持**（Mac/Windows Docker Desktop 行为受限）。

---

### 3.1 Docker Compose — Bridge 网桥模式（推荐，默认）

`memory-server` 与 `postgres` 同在 `memomcp-net` 桥接网络，通过服务名 `postgres` 直连，延迟最低。`postgres` 仍映射 `5432:5432`，宿主机可用 DBeaver 等工具连接 `localhost:5432` 调试。

```bash
docker compose up -d
docker compose logs -f memory-server
docker compose down      # 保留数据
docker compose down -v   # 删除数据卷
```

`docker-compose.yml`：

```yaml
services:
  init-db:
    image: ${MEMOMCP_IMAGE:-ieiian/memomcp-server:latest}
    container_name: memomcp-init-db
    user: "0:0"
    volumes:
      - db-init:/init-scripts
    command: >
      sh -c "cp /app/init.sql /init-scripts/init.sql
      && chmod 644 /init-scripts/init.sql
      && echo 'init.sql copied to shared volume'"
    restart: "no"

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
    networks:
      - memomcp-net

  memory-server:
    image: ${MEMOMCP_IMAGE:-ieiian/memomcp-server:latest}
    container_name: memomcp-server
    env_file:
      - .env
    environment:
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
    networks:
      - memomcp-net

volumes:
  pgdata:
    driver: local
  db-init:
    driver: local

networks:
  memomcp-net:
    driver: bridge
```

**自定义镜像**：在 `.env` 中设置 `MEMOMCP_IMAGE=your-registry/memomcp-server:tag`

---

### 3.2 Docker Compose — 宿主机绕行模式（兼容兜底）

仅在默认 Bridge 模式下 `memory-server` 无法通过 `postgres` 服务名连接数据库时使用（常见于 Colima 等轻量虚拟机环境）。

```bash
docker compose -f docker-compose.host-gateway.yml up -d
```

`docker-compose.host-gateway.yml` 与默认配置的唯一差异在 `memory-server`：

```yaml
  memory-server:
    # ... 其余与 docker-compose.yml 相同 ...
    environment:
      DATABASE_URL: postgresql+asyncpg://memomcp:memomcp@host.docker.internal:5432/memomcp
    extra_hosts:
      - "host.docker.internal:host-gateway"
    networks:
      - memomcp-net
```

| | 容器直连（推荐） | 宿主机绕行（兼容） |
|--|----------------|-------------------|
| 性能 | 桥接网络内直达，开销最小 | 多两次 NAT 封装，高并发时延迟更高 |
| 宿主机 5432 | 可选映射，供外部工具调试 | **必须**映射且不能被本机 PostgreSQL 占用 |
| 可靠性 | 标准环境稳定 | 特定 VM 环境下容器 DNS 异常时可兜底 |

---

### 3.3 Docker Compose — Host Network（真 Host 模式）

`network_mode: host`，容器直接使用宿主机网络栈。`postgres` 监听宿主机 `5432`，`memory-server` 监听宿主机 `8000`，通过 `127.0.0.1` 互联，无 bridge、无端口映射。

```bash
docker compose -f docker-compose.host.yml up -d
docker compose -f docker-compose.host.yml logs -f memory-server
docker compose -f docker-compose.host.yml down
```

**限制**：
- **仅推荐 Linux 生产环境**；Mac/Windows Docker Desktop 的 `network_mode: host` 行为不完整
- 宿主机 `5432`、`8000` 不能被其他进程占用
- 无 `ports` 映射（host 模式下 `ports` 被忽略）

`docker-compose.host.yml`：

```yaml
services:
  init-db:
    image: ${MEMOMCP_IMAGE:-ieiian/memomcp-server:latest}
    container_name: memomcp-init-db
    user: "0:0"
    volumes:
      - db-init:/init-scripts
    command: >
      sh -c "cp /app/init.sql /init-scripts/init.sql
      && chmod 644 /init-scripts/init.sql
      && echo 'init.sql copied to shared volume'"
    restart: "no"

  postgres:
    image: pgvector/pgvector:pg17
    container_name: memomcp-postgres
    network_mode: host
    environment:
      POSTGRES_USER: memomcp
      POSTGRES_PASSWORD: memomcp
      POSTGRES_DB: memomcp
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
    image: ${MEMOMCP_IMAGE:-ieiian/memomcp-server:latest}
    container_name: memomcp-server
    network_mode: host
    env_file:
      - .env
    environment:
      DATABASE_URL: postgresql+asyncpg://memomcp:memomcp@127.0.0.1:5432/memomcp
    depends_on:
      postgres:
        condition: service_healthy
    healthcheck:
      test: ["CMD-SHELL", "python -c \"import urllib.request; urllib.request.urlopen('http://127.0.0.1:8000/api/v1/health')\" || exit 1"]
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

> 若偏好宿主机目录挂载 init 脚本，可将 postgres volumes 改为 `./init/:/docker-entrypoint-initdb.d/:ro`（需先将 `memory-server/init.sql` 复制到 `init/`），并去掉 `init-db` 服务。

---

### 3.4 Docker Run 部署

手动分步启动，等价于桥接模式：

```bash
docker network create memomcp-net

# 提取 init.sql
docker run --rm -v memomcp-init:/init-scripts \
  ieiian/memomcp-server:latest \
  sh -c "cp /app/init.sql /init-scripts/init.sql"

# PostgreSQL
docker run -d --name memomcp-postgres --network memomcp-net \
  -e POSTGRES_USER=memomcp -e POSTGRES_PASSWORD=memomcp -e POSTGRES_DB=memomcp \
  -v memomcp-pgdata:/var/lib/postgresql/data \
  -v memomcp-init:/docker-entrypoint-initdb.d:ro \
  -p 5432:5432 \
  --health-cmd "pg_isready -U memomcp -d memomcp" \
  --health-interval 10s --health-retries 5 \
  --restart unless-stopped \
  pgvector/pgvector:pg17

# 等待就绪
until [ "$(docker inspect --format='{{.State.Health.Status}}' memomcp-postgres)" = "healthy" ]; do sleep 3; done

# REST API（管理 + 调试）
docker run -d --name memomcp-server --network memomcp-net \
  -e DATABASE_URL=postgresql+asyncpg://memomcp:memomcp@memomcp-postgres:5432/memomcp \
  -e AI_MEMORY_MANAGER=false \
  -e EMBEDDING_PROVIDER=gemini \
  -e GEMINI_API_KEY=your_key \
  -e EMBEDDING_DIMENSION=768 \
  -p 8000:8000 \
  --restart unless-stopped \
  ieiian/memomcp-server:latest

# MCP HTTP（远程连接，可与 REST 并行）
docker run -d --name memomcp-mcp --network memomcp-net \
  -e DATABASE_URL=postgresql+asyncpg://memomcp:memomcp@memomcp-postgres:5432/memomcp \
  -e AI_MEMORY_MANAGER=false \
  -p 9000:9000 \
  --restart unless-stopped \
  ieiian/memomcp-server:latest \
  python -m app.main --mcp --transport http --port 9000
```

---

### 3.5 本地开发

```bash
docker compose up -d postgres          # 仅数据库
cd memory-server && uv venv venv && source venv/bin/activate
uv pip install -r requirements.txt

# REST API
DATABASE_URL="postgresql+asyncpg://memomcp:memomcp@localhost:5432/memomcp" \
  uv run python -m app.main

# MCP stdio
DATABASE_URL="postgresql+asyncpg://memomcp:memomcp@localhost:5432/memomcp" \
  uv run python -m app.main --mcp

# MCP HTTP
DATABASE_URL="postgresql+asyncpg://memomcp:memomcp@localhost:5432/memomcp" \
  uv run python -m app.main --mcp --transport http --port 9000
```

---

## 4. MCP 部署与连接

### 4.1 部署方式

| 方式 | 命令 / 配置 | 端口 | 场景 |
|------|-------------|------|------|
| **stdio** | `python -m app.main --mcp` | 无 | 本机 IDE 直连，进程 stdin/stdout |
| **HTTP** | `python -m app.main --mcp --transport http --port 9000` | 9000 | 服务器部署，多客户端共享 |
| **Docker HTTP** | 见 3.3 `memomcp-mcp` 容器 | 9000 | 容器化远程 MCP |

MCP HTTP 端点：`http://<host>:9000/mcp`，与 REST API（8000）可并行运行、共享数据库。

### 4.2 Client 配置

**Cursor / Cline / Claude Desktop — 本地 stdio**（`~/.cursor/mcp.json` 等）：

```json
{
  "mcpServers": {
    "memomcp": {
      "command": "python",
      "args": ["-m", "app.main", "--mcp"],
      "cwd": "/absolute/path/to/MemoMCP/memory-server",
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

> `cwd` 必须为绝对路径；推荐使用 venv 中 python 的绝对路径。

**远程 HTTP**：

```json
{
  "mcpServers": {
    "memomcp": {
      "url": "http://your-server:9000/mcp"
    }
  }
}
```

Cline 远程需加 `"transportType": "sse"`；Claude Desktop 用 `"type": "http"`。Roo Code / Windsurf 格式同 Cursor。

### 4.3 远程 MCP 安全

```nginx
# nginx 反向代理（关闭 buffering，支持 SSE）
location /mcp {
    proxy_pass http://127.0.0.1:9000/mcp;
    proxy_buffering off;
    proxy_read_timeout 86400s;
}
```

生产建议：PostgreSQL 不映射宿主机端口（去掉 `ports: 5432:5432`），仅容器内或 bridge 网络访问。

---

## 5. 环境变量

### 5.1 参数说明

| 变量 | 必填 | 默认值 | 说明 |
|------|------|--------|------|
| `AI_MEMORY_MANAGER` | 否 | `false` | `true` 启用 AI 治理 |
| `LLM_PROVIDER` | 否 | `gemini` | `gemini` / `openai` / `compatible` |
| `LLM_MODEL` | 否 | `gemini-2.0-flash` | LLM 模型名 |
| `GEMINI_API_KEY` | 条件 | - | Gemini API Key |
| `OPENAI_API_KEY` | 条件 | - | OpenAI / Compatible API Key |
| `OPENAI_BASE_URL` | 条件 | - | Compatible 端点（如 DeepSeek、Ollama） |
| `EMBEDDING_PROVIDER` | 否 | `gemini` | `gemini` / `openai` / `compatible` |
| `EMBEDDING_MODEL` | 否 | `text-embedding-3-small` | Embedding 模型 |
| `EMBEDDING_DIMENSION` | 否 | `1536` | **必须与 init.sql 一致**，改维度需重建库 |
| `DATABASE_URL` | **是** | - | 异步 PostgreSQL 连接串（Compose 会覆盖） |
| `MCP_TRANSPORT` | 否 | `stdio` | `stdio` / `sse` |
| `REST_HOST` / `REST_PORT` | 否 | `0.0.0.0` / `8000` | REST 监听地址 |
| `LOG_LEVEL` | 否 | `INFO` | `DEBUG` / `INFO` / `WARNING` / `ERROR` |
| `MEMOMCP_IMAGE` | 否 | `ieiian/memomcp-server:latest` | Compose 镜像 tag |

**`DATABASE_URL` 按部署方式**：

| 部署 | 主机部分 |
|------|----------|
| Compose Bridge（默认） | `@postgres:5432` |
| Compose 宿主机绕行 | `@host.docker.internal:5432` |
| Compose Host Network | `@127.0.0.1:5432` |
| Docker Run | `@memomcp-postgres:5432` |
| 本地开发 | `@localhost:5432` |

### 5.2 完整 `.env` 模板

```env
# ===== 运行模式 =====
# false = Passive Mode（默认，零 LLM 调用）
# true  = AI Memory Manager Mode（启用自动治理层）
AI_MEMORY_MANAGER=false

# ===== LLM Provider（仅 AI_MEMORY_MANAGER=true 时需要）=====
# 可选: gemini | openai | compatible
LLM_PROVIDER=gemini
LLM_MODEL=gemini-2.0-flash

# Gemini
GEMINI_API_KEY=

# OpenAI 官方
OPENAI_API_KEY=

# OpenAI Compatible（OpenRouter / DeepSeek / Moonshot / MiniMax / Ollama / vLLM / LocalAI）
# compatible 模式必填，例如: https://openrouter.ai/api/v1
OPENAI_BASE_URL=

# ===== Embedding Provider =====
# 可选: gemini | openai | compatible
EMBEDDING_PROVIDER=gemini
EMBEDDING_MODEL=text-embedding-3-small
# 向量维度（必须与 init.sql 一致；改维度需重建数据库）
# OpenAI text-embedding-3-small = 1536
# OpenAI text-embedding-3-large = 3072
# Gemini embedding-001 / text-embedding-004 = 768
EMBEDDING_DIMENSION=1536

# ===== 数据库 =====
# Compose Bridge: postgres | 宿主机绕行: host.docker.internal | Host Network: 127.0.0.1 | 本地: localhost
# 注意: docker-compose.yml 的 environment 会覆盖此项
DATABASE_URL=postgresql+asyncpg://memomcp:memomcp@postgres:5432/memomcp

# ===== MCP 传输 =====
# stdio = 标准输入输出（Cursor / Claude Code 本地连接）
# sse   = Server-Sent Events（远程连接）
MCP_TRANSPORT=stdio

# ===== REST API =====
REST_HOST=0.0.0.0
REST_PORT=8000

# ===== 日志 =====
LOG_LEVEL=INFO

# ===== Docker 镜像（可选）=====
# MEMOMCP_IMAGE=ieiian/memomcp-server:latest
```

### 5.3 Provider 配置示例

**Gemini**（768 维）：
```env
EMBEDDING_PROVIDER=gemini
EMBEDDING_MODEL=text-embedding-004
EMBEDDING_DIMENSION=768
GEMINI_API_KEY=your_key
```

**OpenAI**（1536 维）：
```env
LLM_PROVIDER=openai
OPENAI_API_KEY=sk-your_key
EMBEDDING_PROVIDER=openai
EMBEDDING_DIMENSION=1536
```

**DeepSeek LLM + OpenAI Embedding**：
```env
LLM_PROVIDER=compatible
LLM_MODEL=deepseek-chat
OPENAI_BASE_URL=https://api.deepseek.com/v1
OPENAI_API_KEY=your_deepseek_key
EMBEDDING_PROVIDER=openai
EMBEDDING_DIMENSION=1536
```

**Ollama 本地**：
```env
LLM_PROVIDER=compatible
OPENAI_BASE_URL=http://localhost:11434/v1
OPENAI_API_KEY=dummy
EMBEDDING_PROVIDER=compatible
EMBEDDING_MODEL=nomic-embed-text
EMBEDDING_DIMENSION=768
```

---

## 6. 验证与测试

```bash
# 健康检查
curl http://localhost:8000/api/v1/health

# 创建 & 搜索记忆
curl -X POST http://localhost:8000/api/v1/memories \
  -H "Content-Type: application/json" \
  -d '{"workspace_id":"test","memory_type":"rule","content":"Use pnpm","title":"Pkg Manager"}'
curl -X POST http://localhost:8000/api/v1/search \
  -H "Content-Type: application/json" \
  -d '{"workspace_id":"test","query":"pnpm"}'

# 单元测试
cd memory-server
DATABASE_URL="postgresql+asyncpg://memomcp:memomcp@localhost:5432/memomcp" \
  uv run pytest app/tests/ -v --asyncio-mode=auto

# MCP HTTP 测试
uv run python -c "
import asyncio
from fastmcp import Client
async def t():
    async with Client('http://localhost:9000/mcp') as c:
        print([x.name for x in await c.list_tools()])
asyncio.run(t())
"
```

---

## 7. 故障排查

| 问题 | 原因 | 解决 |
|------|------|------|
| `init-db` Permission denied | 非 root 无法写命名卷 | 确认 `user: "0:0"` |
| DB 连接失败（默认 Bridge） | postgres 服务未就绪 / 不同网 | `docker compose ps` 确认 postgres healthy |
| DB 连接失败（宿主机绕行） | `host.docker.internal` 不可用 | 确认 `extra_hosts: host-gateway`；或改回默认 Bridge |
| Host Network 端口冲突 | 宿主机 5432/8000 已被占用 | 释放端口或改用 Bridge 模式 |
| DB 连接失败（Host Network） | 非 Linux 环境 | Mac/Windows 请用默认 `docker-compose.yml` |
| MCP 连接失败 | cwd 非绝对路径 / DB 未运行 | 检查路径与数据库状态 |
| embedding 失败 | Key 无效 / 维度不匹配 | 查日志 `docker compose logs memory-server` |
| 中文搜索效果差 | 全文检索偏英文 | 配置 Embedding 启用向量搜索 |
| Colima 构建超时 | 内存不足 | `colima start --cpu 4 --memory 8` |
