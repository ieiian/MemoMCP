# MemoMCP 项目记忆

## 项目定位
- 基于 MCP 的通用长期记忆基础设施（Memory Infrastructure）
- 服务对象：Cursor / VSCode / Claude Code / Cline / Roo Code 等 AI Coding 工具
- 不是 Agent、不是聊天机器人

## 核心设计
- 两种模式：Passive（默认零 LLM）/ AI Memory Manager（可选自动治理）
- 严格分层：MCP Tool → Service → Repository → DB（工具层禁止直接碰 DB）
- Provider 可插拔：Embedding 与 LLM 各自抽象（gemini / openai / compatible）
- Workspace 隔离：workspace_id 贯穿所有数据
- 三层优雅降级：AI Manager → Embedding → 关键词搜索

## 技术栈
Python 3.12 / FastMCP 3.x / FastAPI / SQLAlchemy 2.x async / PostgreSQL 17 + pgvector / Pydantic Settings / Docker Compose / NullPool（事件循环兼容）

## 关键设计决策
- NullPool 替代默认连接池（MCP HTTP 模式事件循环兼容）
- search_keyword 多词 OR ILIKE 匹配（中文搜索友好）
- Hybrid Search: 向量 + 关键词 RRF 融合 (k=60, top_k*2 扩大召回)
- metadata_ -> metadata 映射在 service 层 _to_response() 处理
- _get_memory_manager() 延迟导入避免循环依赖
- FastMCP 3.x: @mcp.tool + async def + mcp.run(transport="stdio"/"http")

## 项目状态：已完成（7 Phase 全部通过）
1. 架构设计 ✅ 2. 数据库+Docker ✅ 3. 基础 API ✅
4. MCP Server ✅ 5. Embedding Provider ✅ 6. AI Manager ✅ 7. 测试+README ✅
- 18 个测试全部通过
- 10 个 MCP 工具（7 通用 + 3 AI）
- REST API 完整（CRUD + 搜索 + 统计）
